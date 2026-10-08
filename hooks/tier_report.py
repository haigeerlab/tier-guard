#!/usr/bin/env python3
"""/tier-report：把 hook 攒下的 decisions.jsonl（+ 人工标注 labels.jsonl）汇总成一份 markdown。

只读。口径（2026-09-12 定）：
  - 欠配（判定）：起点已知且低于 T2 的 raise。起点未知（继承主会话）被钉 T2 的单列 ——
    主会话本身是 opus 时那只是把隐式写成显式，算进欠配会把违规数虚高。
  - 建议 vs 实际：PreToolUse 记录按 tool_use_id（退而求其次：prompt sha256）关联 SubagentStop
    记录；实际档低于建议档 = **实际欠配**，这是守卫真正要防的那件事。
  - 打回（疑似）：同一会话里，实际跑在 T1 的子代理之后，主会话又派了 subagent_type + description
    都相同的一次。/tier-label reject|accept 可覆写。
  - 误报率：R-IRREVERSIBLE 命中里人工标 fp 的比例（只算已标注的）。未标注的列出来，片段当场
    从主会话 transcript 读，长 token 打码 —— 日志本身不存 prompt 原文。
  - auto 门槛：误报率（已标注 ≥ N 且 < 阈值）+ 打回率（T1 ≥ N，后半段不高于前半段）。阈值在
    config 的 auto_gate。变异测试那条是发版前的仓库检查，运行时查不到，不在这里。

用法: python3 hooks/tier_report.py [--data DIR] [--config PATH] [--recent N] [--share [天数]] [--projects DIR]
"""
import glob
import json
import os
import re
import sys
import time
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import claude_hook  # noqa: E402  只借 transcript 读取，不借判据
import route_decide as rd  # noqa: E402
import tier_state  # noqa: E402

TOKEN = re.compile(r"[A-Za-z0-9_\-+/=.]{20,}")    # 像密钥 / 长 token 的串，片段里一律打码


def _load_jsonl(path):
    recs, broken = [], 0
    try:
        fh = open(path, encoding="utf-8")
    except OSError:
        return None, 0
    with fh:
        for line in fh:
            if not line.strip():
                continue
            try:
                r = json.loads(line)
                if not isinstance(r, dict):
                    raise ValueError
                recs.append(r)
            except ValueError:
                broken += 1
    return recs, broken


def load(path):
    return _load_jsonl(path)


def load_labels(ddir):
    recs, _ = _load_jsonl(os.path.join(ddir, "labels.jsonl"))
    return {r["tool_use_id"]: r["label"] for r in recs or [] if r.get("tool_use_id") and r.get("label")}


def _agents(recs):
    return [r for r in recs if r.get("event") == "agent" and not (r.get("decision") or {}).get("fallback")]


def _desc_key(r):
    """同一 description 的比较键：新记录只有 sha256（Phase 9），更早的记录是原文。"""
    return r.get("description_sha256") or r.get("description")


def _host_internal_stops(recs):
    """不带 agent_type、也关联不到任何派活的 SubagentStop：宿主内部子代理，不是派活（spec Observability）。

    本机实测 2900 / 2900 条如此，带 agent_type 的 473 / 473 条都能关联到派活。返回这些记录的 id() 集合。"""
    dispatched = {r.get("tool_use_id") for r in recs if r.get("event") == "agent" and r.get("tool_use_id")}
    return {id(r) for r in recs if r.get("event") == "subagent-stop"
            and not r.get("agent_type") and r.get("tool_use_id") not in dispatched}


def _v2_routes(recs):
    """v2 审计记录与旧 raise/floor 记录分开统计，避免把两种口径混成“欠配”。"""
    return [r for r in recs if r.get("routing_version") == 2 and isinstance(r.get("decision"), dict)]


def _pair(value):
    if not isinstance(value, dict):
        return "—"
    model = value.get("model") or "继承/未知"
    effort = value.get("reasoning_effort")
    return f"{model} / {effort}" if effort else model


def _host_apply(value):
    if value is True:
        return "是"
    if value is False:
        return "否"
    return "未知"


def _late_read(stop):
    """SubagentStop 触发时子代理唯一的 assistant 行可能还没落盘（2026-09-13 真实宿主实测）；报告时回读同一 transcript。

    → (实际执行, token 用量)。用量一并回读：漏掉这一路会让落盘慢的派活在用量表里整条缺席，
    而那往往正是跑得久、最值得看的那些。"""
    path = stop.get("agent_transcript_path")
    if not isinstance(path, str) or not path:
        return None, None
    try:
        _, _, model, usage = claude_hook.subagent_facts(path)
    except (OSError, ValueError):
        return None, None
    return ({"model": model, "reasoning_effort": None} if model else None), usage


def _late_actual(stop):
    return _late_read(stop)[0]


def _v2_stops(recs):
    """→ {tool_use_id: 实际执行}。实际执行只认 SubagentStop 从子代理 transcript 读到的值，
    严格按 tool_use_id 关联，不按时间或 prompt 猜。"""
    stops = {}
    for r in recs:
        if r.get("event") == "subagent-stop" and r.get("tool_use_id"):
            execution = r["actual_execution"] if isinstance(r.get("actual_execution"), dict) else _late_actual(r)
            if execution:
                stops[r["tool_use_id"]] = execution
    return stops


def _usage_groups(all_stops):
    """→ ([(实际执行, 用量)] 每个子代理一项, 只有修复前用量的子代理数)。

    恢复运行的子代理会往同一份 transcript 追加并再触发一次 SubagentStop，每条 stop 记录存的都是
    整份文件的累计用量 —— 按记录加会把同一个子代理算上好几遍。所以按 agent_transcript_path 分组
    （没有路径的记录自成一组），每组只取一个用量来源：
      a) transcript 还在：回读整份文件（累计且已按 message.id 去重），最权威；
      b) 文件没了、组里有 usage_basis 标记的记录：取其中 ts 最晚的那条；
      c) 文件没了、只有没标记的旧记录：用量被重复计算过（约 2×），不可信，单独计数、不入平均。"""
    groups = {}
    for i, r in enumerate(all_stops):
        path = r.get("agent_transcript_path")
        groups.setdefault(path if isinstance(path, str) and path else ("", i), []).append((i, r))
    used, untrusted = [], 0
    for key, members in groups.items():
        recs = [r for _, r in members]
        latest_exec = next((r["actual_execution"] for r in reversed(recs)
                            if isinstance(r.get("actual_execution"), dict)), None)
        execution = usage = None
        if isinstance(key, str):
            try:
                _, _, model, usage = claude_hook.subagent_facts(key)
            except (OSError, ValueError):
                usage = None
            if isinstance(usage, dict):
                execution = {"model": model, "reasoning_effort": None} if model else latest_exec
        if not isinstance(usage, dict):
            marked = [(r.get("ts") or "", i, r) for i, r in members
                      if r.get("usage_basis") == "message-id-dedup" and isinstance(r.get("usage"), dict)]
            if marked:
                best = max(marked, key=lambda t: t[:2])[2]
                usage = best["usage"]
                execution = best["actual_execution"] if isinstance(best.get("actual_execution"), dict) else latest_exec
            elif any(isinstance(r.get("usage"), dict) for r in recs):
                untrusted += 1
        if isinstance(execution, dict) and isinstance(usage, dict):
            used.append((execution, usage))
    return used, untrusted


def _v2_audit(out, recs, recent):
    routes = _v2_routes(recs)
    out += ["", "### v2 路由审计", ""]
    if not routes:
        out.append("没有 v2 路由记录。")
        return
    profiles = Counter((r.get("decision") or {}).get("profile") or "unknown" for r in routes)
    actions = Counter((r.get("decision") or {}).get("action") or "unknown" for r in routes)
    pinned = sum(bool(((r.get("decision") or {}).get("requested") or {}).get("pinned")) for r in routes)
    emitted = sum(bool(r.get("applied")) for r in routes)
    out.append(f"共 {len(routes)} 次：audit：{profiles['audit']} / guard：{profiles['guard']} / auto：{profiles['auto']} / off：{profiles['off']}；"
               f"hook 已输出改写 {emitted}；pin {pinned}；fallback {actions['pass'] + actions['unsupported']}。")
    # 宿主对某些子代理种类不写 transcript。那不是守卫异常，但它直接决定「实际执行」这一列
    # 有多少是真的未知 —— 不单列出来，读者会以为是 tier-guard 没观测到。
    internal = _host_internal_stops(recs)
    all_stops = [r for r in recs if r.get("event") == "subagent-stop" and id(r) not in internal]
    # 新记录带 transcript_status；更早的记录把同一件事记成了 FileNotFoundError 兜底，两种都要算，
    # 否则在旧日志上这一行会报 0%，而日志里恰恰躺着成千上万条同类事件。
    no_transcript = sum(1 for r in all_stops
                        if r.get("transcript_status") == "missing"
                        or "FileNotFoundError" in (r.get("fallback") or ""))
    if all_stops:
        share = no_transcript / len(all_stops) * 100
        out.append(f"SubagentStop（派活）{len(all_stops)} 次，其中宿主未写 transcript {no_transcript} 次（{share:.1f}%）；"
                   "这部分的实际执行无从观测，与守卫异常无关。")
    if internal:
        out.append(f"另有宿主内部子代理的 SubagentStop {len(internal)} 次（不带 agent_type、关联不到派活），"
                   "不是派活，不计入上面的比例与守卫兜底。")
    # 只报 token，不报成本：价格随模型和账号变动，把价格表写进插件等于埋一个会过期的「事实」。
    # 每任务 token 是宿主给出的硬事实，换算成钱由看报告的人按当时价格自己做。
    # 用量表仍看全部 stop：宿主内部子代理本就没有 transcript，不会进表；这里不重复做归类
    used, untrusted = _usage_groups([r for r in recs if r.get("event") == "subagent-stop"])
    if used:
        by_model = {}
        for execution, usage in used:
            m = execution.get("model") or "（未知）"
            acc = by_model.setdefault(m, {"n": 0, **dict.fromkeys(
                ("input_tokens", "cache_creation_input_tokens",
                 "cache_read_input_tokens", "output_tokens"), 0)})
            acc["n"] += 1
            for k, v in usage.items():
                if k in acc and isinstance(v, int):
                    acc[k] += v
        out += ["", "| 实际执行模型 | 子代理数 | 平均输入 | 平均缓存写 | 平均缓存读 | 平均输出 |",
                "|---|---|---|---|---|---|"]
        for m, a in sorted(by_model.items(), key=lambda kv: -kv[1]["n"]):
            n = a["n"]
            out.append(f"| {m} | {n} | {a['input_tokens']//n:,} | {a['cache_creation_input_tokens']//n:,} "
                       f"| {a['cache_read_input_tokens']//n:,} | {a['output_tokens']//n:,} |")
        out.append("")
        out.append("只统计宿主回报了用量的子代理；不换算成本（价格随模型与账号变动，不写进插件）。")
    if untrusted:
        out.append(f"另有 {untrusted} 个子代理只有修复前记下的用量（输入与缓存约重复计算一倍），未计入上表。")
    stops = _v2_stops(recs)
    out +=["", "| 时间 | 宿主 | 宿主可改写 | 请求 | 选择 / 建议 | hook 改写输出 | 实际执行 | 动作 |",
            "|---|---|---|---|---|---|---|---|"]
    for r in routes[-recent:]:
        d = r["decision"]
        selected = d.get("target") or d.get("recommended")
        emitted_target = d.get("target") if r.get("applied") else None
        # `applied` 是兼容字段：仅表示 adapter 输出了 updatedInput，绝非宿主实际执行回执。
        execution = stops.get(r.get("tool_use_id"))
        out.append(f"| {r.get('ts', '?')} | {d.get('host') or '—'} | {_host_apply(r.get('host_pre_dispatch_apply'))} "
                   f"| {_pair(d.get('requested'))} | {_pair(selected)} | {_pair(emitted_target) if emitted_target else '未输出'} "
                   f"| {_pair(execution) if execution else '未观测'} | {d.get('action') or '—'} |")


def _v2_nudge(out, recs):
    """主代理预路由提醒统计（Task 12）。判据全在 route_decide.nudge_decision / 各薄壳，
    这里只数已记录的 `nudge` 字段，不重新判断谁该被提醒或拦截。"""
    routes = [r for r in recs
              if r.get("routing_version") == 2 and r.get("event") in ("agent", "codex-spawn")
              and "nudge" in r]
    out += ["", "### 主代理预路由提醒", ""]
    if not routes:
        out.append("没有提醒记录（宿主 dispatch_nudge 未开启或尚未派活）。")
        return
    counts = Counter(r.get("nudge") for r in routes)
    reminded, denied, none_ = counts.get("reminded", 0), counts.get("denied", 0), counts.get("none", 0)
    out.append(f"提醒 {reminded} 次 / 拦截 {denied} 次 / 未触发 {none_} 次（共 {len(routes)} 次派活）。")

    # 按 session_id 分组（缺失或空的会话号不参与「同会话后续派活」这项指标），
    # 组内按 ts 再按原始日志顺序排序，找第一条被提醒或拦截的记录，之后的都是「后续派活」。
    groups = {}
    for i, r in enumerate(routes):
        sid = r.get("session_id")
        if sid:
            groups.setdefault(sid, []).append((i, r))
    followups = pinned_followups = 0
    for items in groups.values():
        items.sort(key=lambda pair: (pair[1].get("ts") or "", pair[0]))
        first = next((i for i, (_, r) in enumerate(items) if r.get("nudge") in ("reminded", "denied")), None)
        if first is None:
            continue
        for _, r in items[first + 1:]:
            followups += 1
            if ((r.get("decision") or {}).get("requested") or {}).get("pinned") is True:
                pinned_followups += 1
    if followups:
        out.append(f"提醒或拦截之后同会话派活 {followups} 次，其中显式传参 {pinned_followups} 次"
                   f"（{pinned_followups}/{followups}）。")
    else:
        out.append("提醒或拦截之后同会话派活：暂无样本。")

    k = sum(1 for r in routes
            if ((r.get("decision") or {}).get("requested") or {}).get("pinned") is True
            and r.get("nudge") in ("reminded", "denied"))
    out.append(f"pin 的派活被提醒或拦截 {k} 次（应为 0）。")
    out.append("取舍类任务是否降档需结合真实宿主评估人工判定；报告不推算 token。")


def _irr(a):
    return next((w for w in (a.get("decision") or {}).get("why") or [] if w.get("rule") == "R-IRREVERSIBLE"), {})


def join(recs):
    """→ [(agent 记录, subagent-stop 记录或 None)]，保持 agent 记录的先后顺序。"""
    stops = [r for r in recs if r.get("event") == "subagent-stop"]
    by_id = {s["tool_use_id"]: s for s in stops if s.get("tool_use_id")}
    by_sha = {s["prompt_sha256"]: s for s in stops if s.get("prompt_sha256")}
    return [(a, by_id.get(a.get("tool_use_id")) or by_sha.get(a.get("prompt_sha256"))) for a in _agents(recs)]


def t1_runs(pairs, labels):
    """实际跑在 T1 的子代理，按先后 → [(agent, stop, 是否打回, 来源)]。"""
    out = []
    for i, (a, s) in enumerate(pairs):
        if not s or s.get("actual_tier") != "T1":
            continue
        label = labels.get(a.get("tool_use_id"))
        if label in ("reject", "accept"):
            out.append((a, s, label == "reject", "人工"))
            continue
        again = any(b.get("session_id") == a.get("session_id") and a.get("session_id")
                    and b.get("subagent_type") == a.get("subagent_type")
                    and _desc_key(b) == _desc_key(a)
                    for b, _ in pairs[i + 1:])
        out.append((a, s, again, "重派" if again else ""))
    return out


def fp_stats(recs, labels):
    hits = [a for a in _agents(recs) if _irr(a).get("hit")]
    labeled = [a for a in hits if labels.get(a.get("tool_use_id")) in ("fp", "tp")]
    fp = [a for a in labeled if labels[a["tool_use_id"]] == "fp"]
    return hits, labeled, fp


def gate(recs, labels, cfg):
    """→ (是否放行 auto, [未满足的门槛])。"""
    g = cfg["auto_gate"]
    reasons = []
    _, labeled, fp = fp_stats(recs, labels)
    if len(labeled) < g["min_labeled_irreversible"]:
        reasons.append(f"误报率样本不足：已标注的 R-IRREVERSIBLE 命中 {len(labeled)} 条，要 ≥ {g['min_labeled_irreversible']}")
    elif len(fp) / len(labeled) >= g["max_false_positive_rate"]:
        reasons.append(f"误报率 {len(fp)}/{len(labeled)} = {len(fp) / len(labeled):.0%}，要 < {g['max_false_positive_rate']:.0%}")
    runs = t1_runs(join(recs), labels)
    if len(runs) < g["min_t1_runs"]:
        reasons.append(f"打回率样本不足：T1 子代理 {len(runs)} 次，要 ≥ {g['min_t1_runs']}")
    else:
        half = len(runs) // 2
        first = sum(r[2] for r in runs[:half]) / half
        second = sum(r[2] for r in runs[half:]) / (len(runs) - half)
        if second > first:
            reasons.append(f"打回率在上升：前半段 {first:.0%} → 后半段 {second:.0%}")
    return not reasons, reasons


def snippet(transcript_path, tool_use_id, words, width=40):
    """从主会话 transcript 现读命中词前后的片段；长 token 整段打码。读不到 → None。"""
    prompt = None
    try:
        with open(transcript_path, encoding="utf-8") as fh:
            for line in fh:
                if tool_use_id not in line:
                    continue
                msg = json.loads(line).get("message") or {}
                for b in msg.get("content") or [] if isinstance(msg.get("content"), list) else []:
                    if isinstance(b, dict) and b.get("type") == "tool_use" and b.get("id") == tool_use_id:
                        prompt = (b.get("input") or {}).get("prompt")
                if prompt:
                    break
    except (OSError, TypeError, ValueError):
        return None
    if not isinstance(prompt, str):
        return None
    low = prompt.lower()
    idx = min([i for i in (low.find(w.lower()) for w in words) if i >= 0] or [0])
    lo, hi = max(0, idx - width), min(len(prompt), idx + width + max((len(w) for w in words), default=0))
    for m in TOKEN.finditer(prompt):           # 窗口扩到覆盖所有沾边的 token，再整段打码 —— 不留半截密钥
        if m.end() > lo and m.start() < hi:
            lo, hi = min(lo, m.start()), max(hi, m.end())
    return TOKEN.sub("[已打码]", prompt[lo:hi]).replace("\n", " ")


def share(projects_dir, days):
    """子代理 output token 占比。按 (文件, message.id) 取 usage 最大值去重（流式会重复写同一条）。"""
    t0, cutoff = time.time(), time.time() - days * 86400
    best, files = {}, 0
    for f in glob.glob(os.path.join(projects_dir, "**", "*.jsonl"), recursive=True):
        try:
            if os.path.getmtime(f) < cutoff:
                continue
            files += 1
            is_sub_file = os.sep + "subagents" + os.sep in f
            with open(f, encoding="utf-8", errors="replace") as fh:
                for line in fh:
                    if '"assistant"' not in line:
                        continue
                    try:
                        m = json.loads(line)
                    except ValueError:
                        continue
                    msg = m.get("message") or {}
                    if msg.get("role") != "assistant":
                        continue
                    out = (msg.get("usage") or {}).get("output_tokens") or 0
                    key = (f, msg.get("id") or m.get("uuid"))
                    sub = is_sub_file or bool(m.get("isSidechain"))
                    best[key] = (max(out, best.get(key, (0, sub))[0]), sub)
        except OSError:
            continue
    sub_out = sum(v for v, s in best.values() if s)
    main_out = sum(v for v, s in best.values() if not s)
    return {"files": files, "main": main_out, "sub": sub_out, "seconds": time.time() - t0,
            "share": sub_out / (sub_out + main_out) if sub_out + main_out else None}


def _config(path=None):
    try:
        return rd.load_catalog(path if path is not None else rd.DEFAULT_CATALOG)
    except Exception:
        return None


def _legacy_config():
    try:
        return rd.load_config(rd.DEFAULT_CONFIG)
    except Exception:
        return None


def render(ddir, recs, broken, recent, share_days=None, projects=None, config_path=None):
    cfg = _config(config_path)
    if config_path is not None and cfg is None:
        raise rd.ConfigError("指定的 v2 路由配置不可用；请检查路径、JSON 与目录契约。")
    # 当前模式始终用当前配置；旧配置只解释 v1 历史数据门槛。
    report_cfg = cfg if _v2_routes(recs or []) else _legacy_config()
    mode, src = tier_state.read_mode(ddir, (cfg or {}).get("mode"),
                                     tier_state._profiles(cfg))
    out = ["## tier-guard 路由摘要", "",
           f"- 当前 mode：**{mode}**（来源：{src}）",
           f"- 数据：`{os.path.join(ddir, 'decisions.jsonl')}`"]
    if recs is None:
        out += ["", "还没有任何记录（文件不存在）。出厂默认 off 不记录；用 `/tier-mode guard` 或 `audit` 打开后，hook 每判一次子代理创建就会记一条。"]
        recs = []
    else:
        ts = [r["ts"] for r in recs if r.get("ts")]
        out[-1] += f"，{len(recs)} 条" + (f"（{min(ts)} ~ {max(ts)}）" if ts else "")
        if broken:
            out.append(f"- ⚠️ 有 {broken} 行不是合法 JSON，已跳过")
    labels = load_labels(ddir)
    agents = _agents(recs)

    _v2_audit(out, recs, recent)
    _v2_nudge(out, recs)

    s, rules, fallbacks = Counter(), Counter(), Counter()
    internal = _host_internal_stops(recs)
    for r in recs:
        if id(r) in internal:
            continue
        d = r.get("decision") or {}
        if r.get("fallback") or d.get("fallback"):
            fallbacks[(r.get("fallback") or d.get("fallback")).split(":")[0]] += 1
    for a in agents:
        d = a["decision"]
        for w in d.get("why") or []:
            if w.get("hit") and w.get("rule", "").startswith("R-"):
                rules[w["rule"]] += 1
            if w.get("rule") == "R2" and w.get("hit"):
                s["r2"] += 1
        act = d.get("action")
        if act == "raise" and d.get("start_tier") is not None:
            s["under"] += 1
            if _irr(a).get("suspected_false_positive"):
                s["under_suspect"] += 1
            if a.get("applied"):
                s["under_applied"] += 1
        elif act == "raise":
            s["pinned"] += 1
        elif act in ("local", "defer"):
            s[act] += 1
    out += ["", "### 派子代理（Agent）", "", "| | 条数 |", "|---|---|",
            f"| 判定总数 | {len(agents)} |",
            f"| **欠配**（起点已知且低于 T2，被判 raise） | {s['under']} |",
            f"| 　其中疑似误报（只是提到动作词） | {s['under_suspect']} |",
            f"| 　其中 auto 下 hook 已输出改写 | {s['under_applied']} |",
            f"| 起点未知被钉 T2（继承主会话，不计入欠配） | {s['pinned']} |",
            f"| 建议 local / defer | {s['local']} / {s['defer']} |",
            f"| R2 零节省提示 | {s['r2']} |",
            f"| 守卫放行兜底（fallback） | {sum(fallbacks.values())} |", ""]
    out.append("命中规则：" + ("、".join(f"{k} {v}" for k, v in sorted(rules.items())) or "无"))
    if fallbacks:
        out.append("兜底来源：" + "、".join(f"{k} {v}" for k, v in sorted(fallbacks.items())))

    # 建议 vs 实际。v1 按 tier 比高低；v2 记录没有 tier，只报按 tool_use_id 已观测的实际执行次数
    # （逐条见「v2 路由审计」表）——实际模型与候选档的高低比较是判据，不在报告里推算。
    pairs = join(recs)
    v2_routes = _v2_routes(recs)
    legacy_agents = [a for a in agents if a.get("routing_version") != 2]
    linked = [(a, st) for a, st in pairs if st and st.get("actual_tier") and a["decision"].get("tier")]
    under_actual = [(a, st) for a, st in linked
                    if rd.rank(st["actual_tier"]) < rd.rank(a["decision"]["tier"])]
    esc = sum(1 for r in recs if r.get("event") == "subagent-stop" and r.get("escalated"))
    out += ["", "### 建议档 vs 实际执行档（SubagentStop）", ""]
    if v2_routes:
        v2_stops = _v2_stops(recs)
        seen = sum(1 for r in v2_routes if r.get("tool_use_id") in v2_stops)
        out.append(f"v2：已观测实际执行 {seen} / {len(v2_routes)} 次（逐条见「v2 路由审计」表；报告不比较实际档高低）")
    if legacy_agents or not v2_routes:
        out.append(f"{'v1 旧记录：' if v2_routes else ''}已关联 {len(linked)} / {len(legacy_agents)} 次；"
                   f"**实际欠配**（实际档低于建议档）{len(under_actual)} 次；"
                   f"疑似升级触发（子代理照合同交回）{esc} 次")
    for a, st in under_actual[-recent:]:
        out.append(f"- `{a.get('tool_use_id')}`：建议 {a['decision']['tier']}，实际 {st['actual_tier']}（{st.get('actual_model')}）")

    # 打回率
    runs = t1_runs(pairs, labels)
    rej = [r for r in runs if r[2]]
    out += ["", "### 打回率（T1 产出）", ""]
    if runs:
        out.append(f"T1 子代理 {len(runs)} 次，打回 {len(rej)} 次（{len(rej) / len(runs):.0%}；"
                   f"重派推断 {sum(1 for r in rej if r[3] == '重派')}，人工标注 {sum(1 for r in rej if r[3] == '人工')}）")
    else:
        out.append("还没有实际跑在 T1 的子代理。")

    # 误报率
    hits, labeled, fp = fp_stats(recs, labels)
    out += ["", "### 误报率（R-IRREVERSIBLE，人工判定）", ""]
    out.append(f"命中 {len(hits)} 条，已标注 {len(labeled)} 条，其中误报 {len(fp)} 条"
               + (f"（{len(fp) / len(labeled):.0%}）" if labeled else ""))
    todo = [a for a in hits if labels.get(a.get("tool_use_id")) not in ("fp", "tp")]
    if todo:
        out += ["", "待标注（`/tier-label <id> fp|tp`，只能由人判）：", ""]
        for a in todo[-recent:]:
            irr = _irr(a)
            snip = snippet(a.get("transcript_path") or "", a.get("tool_use_id") or "", irr.get("matches") or [])
            out.append(f"- `{a.get('tool_use_id')}` 命中 {'、'.join(irr.get('matches') or [])}"
                       + ("（疑似误报）" if irr.get("suspected_false_positive") else "")
                       + (f"：…{snip}…" if snip else "：（transcript 读不到，无法给片段）"))

    # Codex
    codex = [r for r in recs if r.get("event") == "codex-dispatch"]
    out += ["", "### 派 Codex（建议 vs 实际）", ""]
    if not codex:
        out.append("没有记录。")
    else:
        c = Counter(str(r.get("consistent")) for r in codex)
        out.append(f"共 {len(codex)} 次：一致 {c['True']} / 不一致 {c['False']} / 起点不认识、无从比较 {c['None']}")
        out += ["", "| 时间 | 实际 `--model` / `--effort` | 建议 | 一致 |", "|---|---|---|---|"]
        for r in codex[-recent:]:
            a, g = r.get("actual") or {}, r.get("suggested") or {}
            mark = {True: "✅", False: "❌", None: "—"}[r.get("consistent")]
            out.append(f"| {r.get('ts', '?')} | {a.get('model') or '默认'} / {a.get('effort') or '默认'} "
                       f"| {g.get('model') or '—'} / {g.get('effort') or '—'} | {mark} |")

    # auto 门槛
    out += ["", "### 切 auto 的门槛", ""]
    if cfg is None:
        out.append("配置读不到，无法判断。")
    elif cfg.get("schema_version") == 2:
        out.append("v2 出厂默认 profile 为 off（可用 `/tier-mode` 持久设为 guard / audit，均不改写参数）；持久 auto 要等真实宿主质量校准与端到端证据后才会开放。")
    if report_cfg is not None and report_cfg.get("schema_version") != 2:
        out += ["", "#### v1 历史数据门槛", "", "以下仅解释历史 v1 数据，不代表当前 v2 可开启 auto。"]
        ok, reasons = gate(recs, labels, report_cfg)
        out.append("✅ 数据门槛已满足（仅反映历史 v1 数据）" if ok
                   else "❌ 未满足：\n" + "\n".join(f"- {x}" for x in reasons))

    if share_days is not None:
        sh = share(projects, share_days)
        out += ["", f"### subagent 占比（近 {share_days} 天，按 output token）", ""]
        out.append(f"扫了 {sh['files']} 个 transcript，耗时 {sh['seconds']:.1f}s；主会话 {sh['main']} / 子代理 {sh['sub']}"
                   + (f"，占比 **{sh['share']:.1%}**（基线 0.0%）" if sh["share"] is not None else "，没有数据"))
    return "\n".join(out)


def main(argv):
    explicit, recent, share_days = None, 10, None
    config_path = None
    if "--config" in argv:
        i = argv.index("--config")
        if argv.count("--config") != 1 or i + 1 >= len(argv) or argv[i + 1].startswith("--"):
            print("❌ --config 需要唯一且完整的路径。")
            return 1
        config_path = argv[i + 1]
    projects = os.path.join(os.path.expanduser("~"), ".claude", "projects")
    if "--data" in argv:
        i = argv.index("--data")
        explicit = argv[i + 1] if i + 1 < len(argv) else None
    if "--recent" in argv:
        recent = int(argv[argv.index("--recent") + 1])
    if "--projects" in argv:
        projects = argv[argv.index("--projects") + 1]
    if "--share" in argv:
        i = argv.index("--share")
        share_days = int(argv[i + 1]) if i + 1 < len(argv) and argv[i + 1].isdigit() else 7
    ddir = tier_state.data_dir(explicit or None)
    recs, broken = load(os.path.join(ddir, "decisions.jsonl"))
    try:
        output = render(ddir, recs, broken, recent, share_days, projects, config_path)
    except rd.ConfigError as exc:
        print(f"❌ {exc}")
        return 1
    print(output)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
