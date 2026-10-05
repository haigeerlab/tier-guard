#!/usr/bin/env python3
"""把判据改坏，看断言套件抓不抓得住。

「全绿」不等于「有断言」：一条要验的变量为空时也照样通过的断言，和没有断言
一样绿。活下来的变异体 = 一个没人拦得住的改动方向 —— 不一定是 bug，但一定
说明那条路径上没有断言。

与 spec-guard 那份的关键区别：**不在工作区就地改文件**。整个仓库先复制到
临时目录，变异和跑套件都在副本里。就地改 + `git checkout` 还原那套踩过两次坑
（另一边跑测试读到被注入变异的文件；变异差点被 commit），而且文件还没进 HEAD
时 `git checkout` 根本还原不了。在副本里做，锁文件和「目标必须干净」两道闸
要防的事故一起不存在了。

不进 validate.sh：每个变异体要跑一遍整套。
用法: python3 scripts/mutation-check.py [--only <说明里的关键词>]
退出码: 0 全部符合预期；1 有活下来的 / 锚点失效 / 基线不绿 / 一个都没选中
"""
import os
import re
import shutil
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# 套件 = 在仓库副本根目录下执行的一条命令；两套都打「总计 N 通过 / M 失败」
TC = ("/bin/bash", "scripts/test-checkers.sh")
RDT = ("python3", "-B", "hooks/route_decide.py", "--selftest")
B32, GP, MF = "scripts/check-bash32.py", "scripts/check-grep-pipe.py", "scripts/check-manifests.py"
RD = "hooks/route_decide.py"
TTG = ("/bin/bash", "hooks/test-tier-guard.sh")
CH, TG = "hooks/claude_hook.py", "hooks/tier-guard.sh"
TTC = ("/bin/bash", "hooks/test-tier-commands.sh")
TS, TR, TL = "hooks/tier_state.py", "hooks/tier_report.py", "hooks/tier_label.py"
TTO = ("/bin/bash", "hooks/test-tier-observe.sh")
SS, PP = "scripts/check-skill-sync.py", "scripts/check-plugin-paths.py"
MA = "scripts/check-mutation-anchors.py"
TGC = ("/bin/bash", "hooks/test-tier-guard-codex.sh")
CX, TGX = "hooks/codex_hook.py", "hooks/tier-guard-codex.sh"
RTC = ("python3", "-B", "hooks/test-route-contract.py")

# 每条: (说明, 被改的文件, 跑哪套, old, new, 预期)
#   预期 "killed"     = 必须被抓到
#   预期 "equivalent" = 行为等价，**活下来才对**
# 标 equivalent 必须写清楚为什么 —— 否则它就是给漏测发的免死金牌。
# old 必须在文件里恰好出现一次，否则算锚点失效（改错地方比不改更糟）。
M = [
    ("bash32: 只认 CJK 标点区（全角括号 U+FF08 漏网）", B32, TC,
     r'''[^\x00-\x7F]")''', r'''[\u3000-\u303F]")''', "killed"),
    ("bash32: 命中了不计数", B32, TC,
     '''                    bad += 1''', '''                    pass''', "killed"),
    ("bash32: 零个文件当通过", B32, TC,
     '''不等于「没问题」")\n        return 1''', '''不等于「没问题」")\n        return 0''', "killed"),
    ("grep-pipe: `||` 也当管道（逻辑或挨假警报）", GP, TC,
     '''(?<!\\|)\\|(?!\\|)''', '''\\|''', "killed"),
    ("grep-pipe: 只认紧跟 grep 的第一个选项（-E -q 漏网）", GP, TC,
     '''grep\\b[^|;&]*?\\s(?:''', '''grep\\s+(?:''', "killed"),
    ("grep-pipe: 不认 --quiet", GP, TC,
     '''|--quiet)''', ''')''', "killed"),
    ("grep-pipe: 注释行也报（讲这个坑的注释挨假警报）", GP, TC,
     '''                if line.lstrip().startswith("#"):\n                    continue\n''', '', "killed"),
    ("grep-pipe: 零个文件当通过", GP, TC,
     '''不等于「没问题」")\n        return 1''', '''不等于「没问题」")\n        return 0''', "killed"),
    ("manifests: 不比版本号（只升一份没人知道）", MF, TC,
     '''    if claude.get("version") != codex.get("version"):''', '''    if False:''', "killed"),
    ("manifests: 不比名称", MF, TC,
     '''    if claude.get("name") != codex.get("name"):''', '''    if False:''', "killed"),
    ("manifests: 不查版本或 Codex cachebuster（两边都缺 version 被当成一致）", MF, TC,
     '''not isinstance(version, str) or not SEMVER.match(version)''', '''False''', "killed"),
    # 裁决为行为等价：缺的那份变成 {} 之后，「缺 name」「version 不是 X.Y.Z」
    # 两道检查照样打 ❌ 并非零退出 —— 缺清单这件事有两层兜底，不靠这一行承重。
    ("manifests: 缺清单当成空清单", MF, TC,
     '''        return None, f"{rel} 不存在"''', '''        return {}, None''', "equivalent"),
    # ── route_decide：判据的唯一实现。每条都对应一个「会悄悄欠配或误报」的方向 ──
    ("route: floor 命中也不抬档", RD, RDT,
     '''    if locked:\n        d["tier"] = "T2"''', '''    if locked:\n        d["tier"] = start''', "killed"),
    ("route: 起点已是 T2 也算升档（opus 挨假违规）", RD, RDT,
     '''rank(start) < rank("T2")''', '''rank(start) <= rank("T2")''', "killed"),
    ("route: 防抖撤回了升档", RD, RDT,
     '''    elif int(ctx.get("consecutive_failures")''', '''    if int(ctx.get("consecutive_failures")''', "killed"),
    ("route: 收益门槛撤回了升档", RD, RDT,
     '''    elif len(prompt.strip()) < cfg''', '''    if len(prompt.strip()) < cfg''', "killed"),
    ("route: 防抖阈值 >= 改成 >", RD, RDT,
     '''>= cfg["debounce"]''', '''> cfg["debounce"]''', "killed"),
    ("route: 动作词大小写敏感（drop table 漏网）", RD, RDT,
     '''        wl = w.lower()''', '''        wl = w''', "killed"),
    ("route: 疑似误报恒为 False", RD, RDT,
     '''"suspected_false_positive": hit and all(mentions)''', '''"suspected_false_positive": False''', "killed"),
    ("route: 疑似误报看整段不看同一句", RD, RDT,
     '''    start = max(low.rfind(c, 0, idx) for c in SENTENCE_ENDS) + 1''', '''    start = 0''', "killed"),
    ("route: 验收行不剥 markdown 前缀", RD, RDT,
     '''    markers = [m.lower() for m in rule["ac_markers"]]\n    has_ac = any(line.lstrip(" \\t-*#>").lower().startswith(tuple(markers))\n                 for line in prompt.splitlines())''',
     '''    markers = [m.lower() for m in rule["ac_markers"]]\n    has_ac = any(line.lstrip().lower().startswith(tuple(markers))\n                 for line in prompt.splitlines())''', "killed"),
    ("route: 验收词出现在任意位置就算（合同文本冒充验收行）", RD, RDT,
     '''    has_ac = any(line.lstrip(" \\t-*#>").lower().startswith(tuple(markers))''',
     '''    has_ac = any(any(m in line.lower() for m in markers)''', "killed"),
    ("route: 只读豁免失效（只读 Review 又被锁 T2）", RD, RDT,
     '''    hit = not has_ac and not readonly''', '''    hit = not has_ac''', "killed"),
    ("route: 取舍词永不命中", RD, RDT,
     '''    matches = [w for w in rule["words"] if w.lower() in low]''', '''    matches = []''', "killed"),
    ("route: fork 不放行", RD, RDT,
     '''    if ti.get("subagent_type") == "fork":''', '''    if False:''', "killed"),
    ("route: mode=off 照样判", RD, RDT,
     '''    if d["mode"] == "off":''', '''    if False:''', "killed"),
    ("route: 异常不放行（守卫崩了挡住干活）", RD, RDT,
     '''        d.update(tier=None, action="pass", target_model=None,''',
     '''        raise\n        d.update(tier=None, action="pass", target_model=None,''', "killed"),
    ("route: 不认识的 model 当继承处理（可能反向降档）", RD, RDT,
     '''        return (tier, "model") if tier else (None, "unknown-model")''',
     '''        return (tier, "model") if tier else (None, "inherit")''', "killed"),
    ("route: 不看 agent frontmatter 的 model", RD, RDT,
     '''    if agent_model and agent_model != "inherit":''', '''    if False:''', "killed"),
    ("route: R2 在 agent 钉了 model 时也提示", RD, RDT,
     '''            and ctx["agent_model"] in (None, "inherit")):''', '''            and True):''', "killed"),
    ("route: Codex 实际 flags 认不出起点档", RD, RDT,
     '''            if flags == (cx["model"], cx["effort"]):''', '''            if False:''', "killed"),
    ("route: Codex 表外组合当继承（sol 会被建议改成 terra）", RD, RDT,
     '''        return None, "unknown-model"        # 表外组合''', '''        return None, "inherit"        # 表外组合''', "killed"),
    ("route: 配置不查 never_auto（gpt-6-astra 可被自动选中）", RD, RDT,
     '''        if cx["model"] in never["codex_models"]:''', '''        if False:''', "killed"),
    ("route: 配置不查 T1/T2 同 slug（升档会换 slug）", RD, RDT,
     '''    if tiers["T1"]["codex"]["model"] != tiers["T2"]["codex"]["model"]:''', '''    if False:''', "killed"),
    ("route: 配置不查 effort 单调", RD, RDT,
     '''    if efforts != sorted(efforts):''', '''    if False:''', "killed"),
    # ── v2 动态路由：任务需求决定候选，pin 和未知不能被旧的起点档语义替代 ──
    ("route v2: 只读机械任务不再选择低成本候选", RD, RTC,
     '''return ["mechanical", "read_only"], "high"''',
     '''return ["tradeoff", "cross_cutting"], "high"''', "killed"),
    ("route v2: pin 被自动路由覆盖", RD, RTC,
     '''if requested.get("pinned", False):''', '''if False:''', "killed"),
    ("route v2: 缺 host pre-dispatch 能力声明也放行", RD, RTC,
     '''if not isinstance(host_capabilities, dict) or set(host_capabilities) != hosts:''',
     '''if False:''', "killed"),
    ("route v2: 请求档重新充当路由起点", RD, RTC,
     '''recommended = eligible[0]''',
     '''recommended = _requested_candidate(candidates, requested) or eligible[0]''', "killed"),
    ("route v2: 信息不足被低成本路由", RD, RTC,
     '''return ["tradeoff", "cross_cutting"], "low"''',
     '''return ["mechanical", "read_only"], "low"''', "killed"),
    ("route v2: 不可逆文本不再导出高风险信号", RD, RTC,
     '''irreversible = any(word.lower() in low for word in rules["irreversible_words"])''',
     '''irreversible = False''', "killed"),
    ("route v2: 文本只读信号不再导出小范围", RD, RTC,
     '''("small" if readonly else ("bounded" if bounded else "unknown"))''',
     '''("unknown" if readonly else ("bounded" if bounded else "unknown"))''', "killed"),
    ("route v2: 验收行不再剥 markdown 前缀", RD, RTC,
     '''    acceptance = any(line.lstrip(" \\t-*#>").lower().startswith(\n        tuple(marker.lower() for marker in rules["acceptance_markers"]))\n        for line in task.splitlines())''',
     '''    acceptance = any(line.lstrip().lower().startswith(\n        tuple(marker.lower() for marker in rules["acceptance_markers"]))\n        for line in task.splitlines())''', "killed"),
    # ── Task 9：主代理预路由提醒 nudge_decision / dispatch_nudge 目录字段 ──
    ("nudge: pinned=None 不再当 none 处理（插件 agent 判不出也被提醒）", RD, RDT,
     '''    if pinned is not False:''', '''    if pinned is True:''', "killed"),
    ("nudge: auto deny 忽略 already_denied（每次都拦）", RD, RDT,
     '''    if isinstance(session_id, str) and session_id and already_denied is not True:''',
     '''    if isinstance(session_id, str) and session_id:''', "killed"),
    ("nudge: auto 没 session_id 也 deny", RD, RDT,
     '''    if isinstance(session_id, str) and session_id and''',
     '''    if True and''', "killed"),
    ("nudge: 非布尔 dispatch_nudge 被接受", RD, RTC,
     '''        if "dispatch_nudge" in capabilities and not isinstance(capabilities["dispatch_nudge"], bool):''',
     '''        if False:''', "killed"),
    ("nudge: audit 也返回 deny", RD, RDT,
     '''    if profile == "audit":\n        return {"action": "remind", "text": nudge_text("remind", summary)}''',
     '''    if profile == "audit":\n        return {"action": "deny", "text": nudge_text("deny", summary)}''', "killed"),
    # ── 主代理预路由提醒附带候选目录摘要：deny/remind 文本不再是没有候选信息的空洞常量 ──
    ("nudge summary: 摘要丢了最后一个候选", RD, RDT,
     '''    for c in candidates:\n        target = c["model"]''',
     '''    for c in candidates[:-1]:\n        target = c["model"]''', "killed"),
    ("nudge summary: 摘要不带 reasoning_effort", RD, RDT,
     '''        if c["reasoning_effort"] is not None:\n            target += f" / {c['reasoning_effort']}"''',
     '''        if False:\n            target += f" / {c['reasoning_effort']}"''', "killed"),
    ("nudge summary: 保守兜底句被删掉", RD, RDT,
     '''    return (f"候选目录（{host}，按成本从低到高）：" + "；".join(parts) +\n            "。信息不足、取舍、跨模块或不可逆动作一律选高能力候选，不要自行降档或使用目录外的组合。")''',
     '''    return (f"候选目录（{host}，按成本从低到高）：" + "；".join(parts))''', "killed"),
    ("nudge summary: claude 适配层不传 summary（提醒文案变回空洞常量）", CH, TTG,
     '''    n = rd.nudge_decision(mode, nudge_pin, host_nudge_gate, session_id, already_denied, nudge_summary)''',
     '''    n = rd.nudge_decision(mode, nudge_pin, host_nudge_gate, session_id, already_denied)''', "killed"),
    ("nudge summary: codex 适配层不传 summary（提醒文案变回空洞常量）", CX, TGC,
     '''    n = rd.nudge_decision(mode, nudge_pin, host_nudge_gate, session_id, already_denied, nudge_summary)''',
     '''    n = rd.nudge_decision(mode, nudge_pin, host_nudge_gate, session_id, already_denied)''', "killed"),
    ("nudge summary: 抢标记降级路径丢了摘要", CH, TTG,
     '''            nudge_status, reminder_text = "reminded", rd.nudge_text("remind", nudge_summary)''',
     '''            nudge_status, reminder_text = "reminded", rd.NUDGE_REMIND_TEXT''', "killed"),
    # ── Task 10：Claude 薄壳的主代理预路由提醒编码（deny 标记 / pin 判定 / 宿主编码）──
    # 裁决为行为等价：「每会话至多 deny 一次」由 claim_nudge_deny 的 O_EXCL 原子抢占保证
    # （并发 hook 本来就会都读到「没 deny 过」）。预读恒为 False 时，第二次会拿到 "exists" →
    # 降级为提醒，stdout / nudge 字段与预读命中完全相同；标记路径被占成普通文件时两边都是
    # "failed" → 提醒。预读只省一次写尝试，不承担正确性。
    ("nudge claude: 去掉「已 deny 过」的预读（只靠 O_EXCL 抢标记）", TS, TTG,
     '''    ddir, digest = _nudge_marker_dir_and_digest(session_id)\n    return os.path.isfile(os.path.join(ddir, digest))''',
     '''    ddir, digest = _nudge_marker_dir_and_digest(session_id)\n    return False''', "equivalent"),
    ("nudge claude: 标记写失败也算成功（会真 deny 但没有持久化的标记）", TS, TTG,
     '''    try:\n        os.makedirs(ddir, mode=0o700, exist_ok=True)\n    except OSError:\n        return "failed"''',
     '''    try:\n        os.makedirs(ddir, mode=0o700, exist_ok=True)\n    except OSError:\n        return "created"''', "killed"),
    ("nudge claude: 并发抢输（标记已存在）也 deny（同一会话被拦多次）", TS, TTG,
     '''    except FileExistsError:\n        return "exists"''', '''    except FileExistsError:\n        return "created"''', "killed"),
    ("nudge claude: 插件 / fork agent 当成能确认未 pin（会被提醒或拦截）", CH, TTG,
     '''    if isinstance(subagent_type, str) and (subagent_type == "fork" or ":" in subagent_type):\n        # fork 恒继承父代理模型、插件 agent 的 frontmatter 读不到：env 也改变不了「判不出」\n        return None''',
     '''    if isinstance(subagent_type, str) and (subagent_type == "fork" or ":" in subagent_type):\n        # fork 恒继承父代理模型、插件 agent 的 frontmatter 读不到：env 也改变不了「判不出」\n        return False''', "killed"),
    ("nudge claude: remind 顺带附上 permissionDecision（audit 下也像被拦截）", CH, TTG,
     '''            out = {"hookSpecificOutput": {"hookEventName": "PreToolUse", "additionalContext": reminder_text}}''',
     '''            out = {"hookSpecificOutput": {"hookEventName": "PreToolUse", "additionalContext": reminder_text, "permissionDecision": "allow"}}''', "killed"),
    ("nudge claude: deny 顺带输出 updatedInput（deny 该压过改写，没压住）", CH, TTG,
     '''                                             "permissionDecisionReason": deny_reason}}''',
     '''                                             "permissionDecisionReason": deny_reason, "updatedInput": dict(ti)}}''', "killed"),
    ("nudge claude: deny 标记文件名直接用原始 session id（sha256 白算了）", TS, TTG,
     '''    digest = hashlib.sha256(session_id.encode("utf-8")).hexdigest()''',
     '''    digest = session_id''', "killed"),
    ("nudge claude: 审计记录不写 nudge 字段（none/reminded/denied 全无从审计）", CH, TTG,
     '''               nudge=nudge_status, applied=False)''',
     '''               applied=False)''', "killed"),
    # ── Task 11：Codex 薄壳的主代理预路由提醒编码（pin 判定 / 标记复用 / 宿主编码）──
    ("nudge codex: fork_turns 被当成判不出 pin（真实 Codex 每次都带它，提醒永不触发）", CX, TGC,
     '''    if ti.get("model") or ti.get("reasoning_effort"):\n        return True\n    return False''',
     '''    if ti.get("model") or ti.get("reasoning_effort"):\n        return True\n    if any(k.startswith("fork_") and v for k, v in ti.items()):\n        return None\n    return False''', "killed"),
    ("nudge codex: 显式 reasoning_effort 不算 pin", CX, TGC,
     '''    if ti.get("model") or ti.get("reasoning_effort"):\n        return True''',
     '''    if ti.get("model"):\n        return True''', "killed"),
    ("nudge codex: 抢标记 exists 也当 deny 成功（同一会话被拦多次）", CX, TGC,
     '''        if tier_state.claim_nudge_deny(session_id) == "created":''',
     '''        if tier_state.claim_nudge_deny(session_id) in ("created", "exists"):''', "killed"),
    ("nudge codex: deny 顺带输出 updatedInput（deny 该压过改写，没压住）", CX, TGC,
     '''                                             "permissionDecisionReason": deny_reason}}''',
     '''                                             "permissionDecisionReason": deny_reason, "updatedInput": dict(ti)}}''', "killed"),
    ("nudge codex: remind 顺带附上 permissionDecision（audit 下也像被拦截）", CX, TGC,
     '''            out = {"hookSpecificOutput": {"hookEventName": "PreToolUse", "additionalContext": reminder_text}}''',
     '''            out = {"hookSpecificOutput": {"hookEventName": "PreToolUse", "additionalContext": reminder_text, "permissionDecision": "allow"}}''', "killed"),
    ("nudge codex: 审计记录不写 nudge 字段（none/reminded/denied 全无从审计）", CX, TGC,
     '''           "nudge": nudge_status, "applied": False}''',
     '''           "applied": False}''', "killed"),
    ("guard adapter: claude 把 guard 当 auto 输出 updatedInput（guard 本该从不改写参数）", CH, TTG,
     '''    if (mode == "auto" and host_pre_dispatch_apply''',
     '''    if (mode in ("auto", "guard") and host_pre_dispatch_apply''', "killed"),
    ("guard adapter: codex 把 guard 当 auto 输出 updatedInput（guard 本该从不改写参数）", CX, TGC,
     '''    if (mode == "auto" and host_pre_dispatch_apply''',
     '''    if (mode in ("auto", "guard") and host_pre_dispatch_apply''', "killed"),
    ("guard report: profile 计数行漏掉 guard", TR, TTC,
     ''' / guard：{profiles['guard']}''', '''''', "killed"),
    # ── Task 5：skill 同步 / 路径引用 / mode 状态 / 报表 ──
    ("skill-sync: 不比 v2 候选表（配置漂移漏网）", SS, TC,
     '''        if got != want:''', '''        if False:''', "killed"),
    ("skill-sync: 候选表标记丢了当成没东西可比", SS, TC,
     '''    if table is None:\n        print(f"  ❌ {SKILL} 缺 <!-- candidate-table:begin/end --> 标记")\n        return 1''',
     '''    if False:\n        print(f"  ❌ {SKILL} 缺 <!-- candidate-table:begin/end --> 标记")\n        return 1''', "killed"),
    ("mutation-anchors: 只认「一次都不命中」，重复命中放行（重复的变异体同样整条不跑）", MA, TC,
     '''        if hits != 1:''', '''        if hits < 1:''', "killed"),
    ("mutation-anchors: 零个变异体当成通过（空列表等于没这个检查）", MA, TC,
     '''    if not mutants:
        print(f"  ❌ {TARGET} 的变异体列表为空 —— 不算通过")
        return 1''',
     '''    if False:
        print(f"  ❌ {TARGET} 的变异体列表为空 —— 不算通过")
        return 1''', "killed"),
    ("plugin-paths: 路径不存在也放行", PP, TC,
     '''            if not os.path.exists(os.path.join(root, m.group(1))):''', '''            if False:''', "killed"),
    ("plugin-paths: 零个文件当通过", PP, TC,
     '''不等于「没问题」")\n        return 1''', '''不等于「没问题」")\n        return 0''', "killed"),
    ("tier-mode: auto 不再被拒", TS, TTC,
     '''    if mode == "auto":''', '''    if False:''', "killed"),
    ("tier-mode: 状态文件压过环境变量", TS, TTC,
     '''    env = os.environ.get("TIER_GUARD_MODE")\n    if env:''', '''    env = os.environ.get("TIER_GUARD_MODE")\n    if False:''', "killed"),
    ("tier-mode: 状态文件不生效", TS, TTC,
     '''    if m and (allowed is None or m in allowed):\n        return m, f"{path}（/tier-mode 设置）"''',
     '''    if False:\n        return m, f"{path}（/tier-mode 设置）"''', "killed"),
    ("tier-report: 起点未知的钉 T2 也算成欠配（违规数虚高）", TR, TTC,
     '''        if act == "raise" and d.get("start_tier") is not None:''', '''        if act == "raise":''', "killed"),
    ("tier-report: 疑似误报不单列", TR, TTC,
     '''            if _irr(a).get("suspected_false_positive"):''', '''            if False:''', "killed"),
    ("tier-report: 坏行让报表崩溃", TR, TTC,
     '''            except ValueError:\n                broken += 1''', '''            except KeyError:\n                broken += 1''', "killed"),
    ("tier-report: Codex 一致性不分真假", TR, TTC,
     '''        c = Counter(str(r.get("consistent")) for r in codex)''',
     '''        c = Counter("True" for r in codex)''', "killed"),
    # ── Task 4b：Codex 薄壳（编码不同：updatedInput 必须配 allow；只动 effort；effort 未知不动）──
    ("codex: 去掉 permissionDecision=allow（Codex 会拒收 updatedInput）", CX, TGC,
     '''            "permissionDecision": "allow",\n            "permissionDecisionReason": f"tier-guard: v2 选择 {target['id']}",\n''',
     '''            "permissionDecisionReason": f"tier-guard: v2 选择 {target['id']}",\n''', "killed"),
    ("codex v2: 未验证宿主也允许实际改写", CX, TGC,
     '''if (mode == "auto" and host_pre_dispatch_apply''',
     '''if (mode == "auto" and True''', "killed"),
    ("claude v2: 未验证宿主也允许实际改写", CH, TTG,
     '''if (mode == "auto" and host_pre_dispatch_apply''',
     '''if (mode == "auto" and True''', "killed"),
    ("codex v2: 宿主能力状态总记为已验证", CX, TGC,
     '''"host_pre_dispatch_apply": host_pre_dispatch_apply''',
     '''"host_pre_dispatch_apply": True''', "killed"),
    ("claude v2: 宿主能力状态总记为已验证", CH, TTG,
     '''host_pre_dispatch_apply=host_pre_dispatch_apply''',
     '''host_pre_dispatch_apply=True''', "killed"),
    ("codex: dry-run 也产出 updatedInput", CX, TGC,
     '''    if d["mode"] == "auto" and d["action"] == "raise"''', '''    if d["action"] == "raise"''', "killed"),
    ("codex: 升档没改 reasoning_effort", CX, TGC,
     '''        new_ti["reasoning_effort"] = d["target_reasoning_effort"]\n''', '', "killed"),
    ("codex: 继承的 effort 被当成 high（父会话若是 max 会被降档）", CX, TGC,
     '''           "codex_effort": ti.get("reasoning_effort")}''',
     '''           "codex_effort": ti.get("reasoning_effort") or "high"}''', "killed"),
    ("codex: 不看继承的会话 model", CX, TGC,
     '''           "codex_model": ti.get("model") or payload.get("model"),''',
     '''           "codex_model": ti.get("model"),''', "killed"),
    ("codex: 不限 spawn_agent", CX, TGC,
     '''def on_spawn(payload, cfg, mode):\n    if not is_spawn_tool_name(payload.get("tool_name")):\n        return None, None\n    ti = payload.get("tool_input")''',
     '''def on_spawn(payload, cfg, mode):\n    if False:\n        return None, None\n    ti = payload.get("tool_input")''', "killed"),
    # 裁决为行为等价：不优先取 message 时，兜底分支把「非控制类的字符串参数」拼起来 ——
    # spawn_agent 里这样的参数只有 message 一个，拼出来的文本和来源字段都与原来相同。
    ("codex: 不优先取 message 字段", CX, TGC,
     '''    for key in ("message", "prompt"):''', '''    for key in ("prompt",):''', "equivalent"),
    ("codex: codex_hook 不接异常", CX, TGC,
     '''    except Exception as e:                        # 守卫自己不能崩''',
     '''    except ZeroDivisionError as e:                        # 守卫自己不能崩''', "killed"),
    ("codex: python 起不来时退出非零", TGX, TGC,
     '''  fi\n  exit 0\n}''', '''  fi\n  exit 1\n}''', "killed"),
    ("manifests: marketplace 条目名不比", MF, TC,
     '''            if entry.get("name") != claude.get("name"):''', '''            if False:''', "killed"),
    ("manifests: marketplace source 不查", MF, TC,
     '''            if not os.path.isfile(os.path.join(src, ".claude-plugin", "plugin.json")):''',
     '''            if False:''', "killed"),
    ("manifests: 声明的 hooks 路径不查存在", MF, TC,
     '''            if isinstance(rel, str) and not os.path.exists(os.path.join(root, rel)):''',
     '''            if False:''', "killed"),
    ("plugin-paths: 只认 CLAUDE_PLUGIN_ROOT（Codex 的 PLUGIN_ROOT 漏查）", PP, TC,
     r'''REF = re.compile(r"\$\{(?:CLAUDE_)?PLUGIN_ROOT\}/''', r'''REF = re.compile(r"\$\{CLAUDE_PLUGIN_ROOT\}/''', "killed"),
    ("plugin-paths: 只扫 hooks.json（codex-hooks.json 漏查）", PP, TC,
     '''glob.glob(os.path.join(root, "hooks", "*.json"))''', '''glob.glob(os.path.join(root, "hooks", "hooks.json"))''', "killed"),
    # ── Task 6：SubagentStop / 建议 vs 实际 / 打回率 / 误报率 / auto 门槛 / 占比 ──
    ("observe: 升级触发只看编号不看交回", RD, RDT,
     '''            and ("交回" in text or "停止" in text))''', '''            and True)''', "killed"),
    # 两个 handler 的这一行逐字相同（v1 on_subagent_stop / v2 on_subagent_stop_v2），锚点必须
    # 带上各自的上一行才唯一；两条路径由不同套件守（v1 看 actual_tier 关联，v2 看报告的实际执行表）。
    ("observe: SubagentStop(v1) 不读 meta 的 toolUseId", CH, TTO,
     '''           "event": "subagent-stop", "session_id": payload.get("session_id"),\n'''
     '''           "tool_use_id": meta.get("toolUseId"), "agent_type": meta.get("agentType"),''',
     '''           "event": "subagent-stop", "session_id": payload.get("session_id"),\n'''
     '''           "tool_use_id": None, "agent_type": meta.get("agentType"),''', "killed"),
    ("observe: SubagentStop(v2) 不读 meta 的 toolUseId", CH, TTC,
     '''    rec["tool_use_id"] = meta.get("toolUseId")''',
     '''    rec["tool_use_id"] = None''', "killed"),
    ("observe: SubagentStop 有输出（会挡住子代理结束）", CH, TTO,
     '''    return rec, None                               # 永不输出''',
     '''    return rec, {"decision": "block"}                               # 永不输出''', "killed"),
    ("observe: 关联去掉 sha256 兜底", TR, TTO,
     '''by_id.get(a.get("tool_use_id")) or by_sha.get(a.get("prompt_sha256"))''',
     '''by_id.get(a.get("tool_use_id"))''', "killed"),
    ("observe: 实际欠配方向判反", TR, TTO,
     '''                    if rd.rank(st["actual_tier"]) < rd.rank(a["decision"]["tier"])]''',
     '''                    if rd.rank(st["actual_tier"]) > rd.rank(a["decision"]["tier"])]''', "killed"),
    ("observe: 打回推断不限同一会话", TR, TTO,
     '''        again = any(b.get("session_id") == a.get("session_id") and a.get("session_id")''',
     '''        again = any(True''', "killed"),
    ("observe: 人工标注覆写不了打回推断", TR, TTO,
     '''        if label in ("reject", "accept"):''', '''        if False:''', "killed"),
    ("observe: 误报率门槛 < 放宽成 <=（恰好 10% 放行）", TR, TTO,
     '''    elif len(fp) / len(labeled) >= g["max_false_positive_rate"]:''',
     '''    elif len(fp) / len(labeled) > g["max_false_positive_rate"]:''', "killed"),
    ("observe: 误报率不查样本量", TR, TTO,
     '''    if len(labeled) < g["min_labeled_irreversible"]:''', '''    if False:''', "killed"),
    ("observe: 打回率上升不拦", TR, TTO,
     '''        if second > first:''', '''        if False:''', "killed"),
    ("observe: 片段不打码", TR, TTO,
     '''    return TOKEN.sub("[已打码]", prompt[lo:hi]).replace("\\n", " ")''',
     '''    return prompt[lo:hi].replace("\\n", " ")''', "killed"),
    ("observe: 片段窗口不扩到整段 token（漏半截密钥）", TR, TTO,
     '''        if m.end() > lo and m.start() < hi:''', '''        if False:''', "killed"),
    ("observe: 占比把流式重复写的同一条消息累加", TR, TTO,
     '''                    best[key] = (max(out, best.get(key, (0, sub))[0]), sub)''',
     '''                    best[key] = (out + best.get(key, (0, sub))[0], sub)''', "killed"),
    ("observe: 占比不按天数过滤", TR, TTO,
     '''            if os.path.getmtime(f) < cutoff:''', '''            if False:''', "killed"),
    ("observe: fp 可以标在没命中动作词的记录上", TL, TTO,
     '''    if label in ("fp", "tp") and not tier_report._irr(a).get("hit"):''', '''    if False:''', "killed"),
    ("observe: reject 可以标在非 T1 的记录上", TL, TTO,
     '''    if label in ("reject", "accept") and not (s and s.get("actual_tier") == "T1"):''', '''    if False:''', "killed"),
    # ── Claude 薄壳：放行 / 编码 / 日志 / agent 解析 / Codex 派活记录 ──
    ("shell: dry-run 也产出 updatedInput", CH, TTG,
     '''    if d["mode"] == "auto" and d["action"] == "raise"''', '''    if d["action"] == "raise"''', "killed"),
    ("shell: updatedInput 顺带 allow（绕过权限流程）", CH, TTG,
     '''        new_ti["model"] = target["model"]\n        out = {"hookSpecificOutput": {"hookEventName": "PreToolUse", "updatedInput": new_ti}}''',
     '''        new_ti["model"] = target["model"]\n        out = {"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "allow", "updatedInput": new_ti}}''', "killed"),
    ("shell: updatedInput 只剩 model（其余字段丢了）", CH, TTG,
     '''    if (mode == "auto" and host_pre_dispatch_apply\n            and d.get("action") in ("select", "lower", "raise")\n            and target.get("model") and not d.get("fallback")):\n        new_ti = dict(ti)''',
     '''    if (mode == "auto" and host_pre_dispatch_apply\n            and d.get("action") in ("select", "lower", "raise")\n            and target.get("model") and not d.get("fallback")):\n        new_ti = {}''', "killed"),
    ("shell: 日志记 prompt 原文", CH, TTG,
     '''            "prompt_chars": len(prompt),''', '''            "prompt_chars": len(prompt), "prompt": prompt,''', "killed"),
    ("shell: agent 目录顺序反了（用户目录压过项目）", CH, TTG,
     '''    return [os.path.join(project, ".claude", "agents"),\n            os.path.join(os.path.expanduser("~"), ".claude", "agents")]''',
     '''    return [os.path.join(os.path.expanduser("~"), ".claude", "agents"),\n            os.path.join(project, ".claude", "agents")]''', "killed"),
    ("shell: v2 仍跳过 SubagentStop（报告永远未观测）", CH, TTG,
     '''            elif event == "subagent-stop" and mode != "off":''', '''            elif False:''', "killed"),
    ("shell: v2 SubagentStop 在 off 下也记日志", CH, TTG,
     '''            elif event == "subagent-stop" and mode != "off":''', '''            elif event == "subagent-stop":''', "killed"),
    ("shell: v2 实际执行把宿主没给的 effort 编成值", CH, TTG,
     '''{"model": model, "reasoning_effort": None} if model else None''',
     '''{"model": model, "reasoning_effort": "medium"} if model else None''', "killed"),
    ("shell: v2 SubagentStop 记子任务原文", CH, TTG,
     '''    rec["prompt_sha256"] = hashlib.sha256(prompt.encode("utf-8")).hexdigest() if prompt else None''',
     '''    rec["prompt_sha256"] = prompt''', "killed"),
    ("shell: v2 SubagentStop 不留 transcript 路径（未落盘时报告补不回）", CH, TTC,
     '''           "agent_transcript_path": path,''', '', "killed"),
    ("report: v2 不回读 transcript（触发时未落盘的实际模型永远未观测）", TR, TTC,
     '''else _late_actual(r)''', '''else None''', "killed"),
    ("report: v2 实际执行不按 tool_use_id 关联（张冠李戴）", TR, TTC,
     '''        execution = stops.get(r.get("tool_use_id"))''',
     '''        execution = next(iter(stops.values()), None)''', "killed"),
    ("report link: v2 已观测实际执行恒为 0（回到「已关联 0 / N」的误导）", TR, TTC,
     '''        seen = sum(1 for r in v2_routes if r.get("tool_use_id") in v2_stops)''',
     '''        seen = 0''', "killed"),
    ("report link: v1 分母混入 v2 记录", TR, TTC,
     '''    legacy_agents = [a for a in agents if a.get("routing_version") != 2]''',
     '''    legacy_agents = agents''', "killed"),
    ("shell: claude_hook 不接异常（崩溃交给薄壳兜底）", CH, TTG,
     '''    except Exception as e:                        # 守卫自己不能崩''',
     '''    except ZeroDivisionError as e:                        # 守卫自己不能崩''', "killed"),
    ("shell: Codex 建议与实际的一致性判反", CH, TTG,
     '''consistent=(actual == suggested) if d["tier"] else None''',
     '''consistent=(actual != suggested) if d["tier"] else None''', "killed"),
    ("shell: Bash 事件在 auto 下也输出", CH, TTG,
     '''    return rec, None                               # 提议式''',
     '''    return rec, {"x": 1}                               # 提议式''', "killed"),
    ("shell: codex-exec 解析不在 && 处停", CH, TTG,
     '''        if set(a) <= set(";&|<>()"):''', '''        if False:''', "killed"),
    ("shell: python 起不来时退出非零（挡住干活）", TG, TTG,
     '''  fi\n  exit 0\n}''', '''  fi\n  exit 1\n}''', "killed"),
    # 裁决为行为等价：off 快速路径只省一次 python 启动。去掉后 claude_hook 照样
    # 判出 mode=off、不输出、不记日志 —— stdout / 退出码 / 日志三样都不变。
    ("shell: 去掉 off 快速路径", TG, TTG,
     '''[ "${TIER_GUARD_MODE:-}" = off ] && exit 0''', ''':''', "equivalent"),
    # 裁决为行为等价：Bash 快速路径只省 python 启动。去掉后 parse_codex_exec 认不出
    # codex-exec.sh → 不记日志、不输出。代价只在耗时上，这里的断言本来就不测它。
    ("shell: 去掉 Bash 快速路径", TG, TTG,
     '''  case "${PAYLOAD}" in *codex-exec.sh*) ;; *) exit 0 ;; esac''', '''  :''', "equivalent"),
    # ── Task 12：/tier-report 的「主代理预路由提醒」段落——只数字段，判据不在这里 ──
    ("report nudge: 忽略先后顺序（同会话被提醒/拦截之前的记录也算后续派活）", TR, TTC,
     '''        for _, r in items[first + 1:]:''', '''        for _, r in items:''', "killed"),
    ("report nudge: 后续派活不再要求显式传参才计入分子", TR, TTC,
     '''            if ((r.get("decision") or {}).get("requested") or {}).get("pinned") is True:\n                pinned_followups += 1''',
     '''            pinned_followups += 1''', "killed"),
    ("report nudge: 缺 nudge 字段的旧记录也被计入（schema 升级前的日志）", TR, TTC,
     '''              and "nudge" in r]''', ''']''', "killed"),
    ("report nudge: pin 的派活不论是否被提醒或拦截都计入 K", TR, TTC,
     '''    k = sum(1 for r in routes\n            if ((r.get("decision") or {}).get("requested") or {}).get("pinned") is True\n            and r.get("nudge") in ("reminded", "denied"))''',
     '''    k = sum(1 for r in routes\n            if ((r.get("decision") or {}).get("requested") or {}).get("pinned") is True)''', "killed"),
    ("report nudge: 没有记录时的空文案再也不打印", TR, TTC,
     '''    if not routes:\n        out.append("没有提醒记录（宿主 dispatch_nudge 未开启或尚未派活）。")\n        return''',
     '''    if not routes:\n        return''', "killed"),
    # ── Task 13：guard profile —— audit 与 auto 之间新增的、无门槛可持久化的默认档 ──
    ("guard: ROUTING_PROFILES 里缺了 guard（校验和 nudge 都认不出这个 profile）", RD, RDT,
     '''ROUTING_PROFILES = ("off", "audit", "guard", "auto")''',
     '''ROUTING_PROFILES = ("off", "audit", "auto")''', "killed"),
    ("guard: nudge_decision 把 guard 当成只提醒（本该像 auto 一样每会话先 deny 一次）", RD, RDT,
     '''    if profile == "audit":\n        return {"action": "remind", "text": nudge_text("remind", summary)}''',
     '''    if profile in ("audit", "guard"):\n        return {"action": "remind", "text": nudge_text("remind", summary)}''', "killed"),
    ("guard: route() 里 guard 走了 auto 的 pinned 分支（pin 请求会被当成 pinned 而非可审计的 action）", RD, RDT,
     '''        if cfg["mode"] in ("audit", "guard"):''',
     '''        if cfg["mode"] == "audit":''', "killed"),
    ("guard: tier_state 把 set guard 也送进 auto 的质量门槛（guard 本该像 audit 一样无门槛持久化）", TS, TTC,
     '''    if mode == "auto":''', '''    if mode in ("auto", "guard"):''', "killed"),
    ("guard: 生产目录默认值被改回 audit（guard 应该是当前的默认 mode）", "config/routing.catalog.v2.json", RTC,
     '''"mode": "guard",''', '''"mode": "audit",''', "killed"),
    ("catalog: Codex L1 被改回上一代 luna（2026-10 更新后生产表应钉在 gpt-6-luna）",
     "config/routing.catalog.v2.json", RTC,
     '''"model": "gpt-6-luna",''', '''"model": "gpt-5.6-luna",''', "killed"),
    ("pin: 不读宿主配置的子代理模型（auto 会覆盖用户用环境变量做的显式选择）", CH, TTG,
     '''    pinned = bool(ti.get("model")) or bool(found and agent_model) or bool(env_model)''',
     '''    pinned = bool(ti.get("model")) or bool(found and agent_model)''', "killed"),
    ("pin: env 的 inherit / default 也当成 pin（会把「没设」误判为已 pin，整类任务不再路由）", CH, TTG,
     '''        if value and value.lower() not in _MODEL_NOT_A_CHOICE:''',
     '''        if value:''', "killed"),
    ("usage: 读到模型就停（用量只剩第一条 assistant，跨消息的累加全丢）", CH, TTG,
     '''            if model is None and msg.get("role") == "assistant" and msg.get("model"):
                model = msg["model"]''',
     '''            if model is None and msg.get("role") == "assistant" and msg.get("model"):
                model = msg["model"]
                break''', "killed"),
    ("usage: 宿主没给用量时记一串 0（会被读成「真的没花 token」）", CH, TTG,
     '''    return meta, prompt, model, (usage if seen_usage else None)''',
     '''    return meta, prompt, model, usage''', "killed"),
    ("report: 回读未落盘 transcript 时只补模型不补用量（长任务在用量表里整条缺席）", TR, TTC,
     '''            usage = usage if isinstance(usage, dict) else late_usage''',
     '''            usage = usage''', "killed"),
    ("stop: 先读 transcript 再建记录（读失败会把整条记录连同 session_id 和路径一起吞掉）", CH, TTG,
     '''    except FileNotFoundError:''',
     '''    except SystemExit:''', "killed"),
    ("stop: 宿主没写 transcript 也标成 ok（missing 与 ok 不可区分，报告据此失真）", CH, TTG,
     '''        rec["transcript_status"] = "missing"''',
     '''        rec["transcript_status"] = "ok"''', "killed"),
    ("report: 未写 transcript 只认新字段（旧日志上会报 0%，而那里正躺着几千条同类事件）", TR, TTC,
     '''                        if r.get("transcript_status") == "missing"
                        or "FileNotFoundError" in (r.get("fallback") or ""))''',
     '''                        if r.get("transcript_status") == "missing")''', "killed"),
    ("pin: frontmatter 的 inherit / default 当成 pin（整类 agent 的派活静默不再被路由）", CH, TTG,
     '''                model = (fm.get("model") or "").strip()
                if model.lower() in _MODEL_NOT_A_CHOICE:
                    model = ""
                return True, model or None''',
     '''                return True, fm.get("model") or None''', "killed"),
    ("pin: env 优先于 tool_input.model（本次派活的显式参数应最高优先）", CH, TTG,
     '''            "model": ti.get("model") or agent_model or env_model,''',
     '''            "model": env_model or ti.get("model") or agent_model,''', "killed"),
    ("catalog: Claude 候选被塞进 reasoning_effort（Agent 工具 schema 没有这个通道）",
     "config/routing.catalog.v2.json", RTC,
     '''      "id": "claude-sonnet",
      "host": "claude-code",
      "model": "sonnet",
      "reasoning_effort": null,''',
     '''      "id": "claude-sonnet",
      "host": "claude-code",
      "model": "sonnet",
      "reasoning_effort": "medium",''', "killed"),
    # ── Task 16：上游档位标记解析、信封 v2、tier_source ──
    ("tier16: 标记出现两次不再算冲突", RD, RTC,
     '''if count >= 2:''',
     '''if count >= 3:''', "killed"),
    ("tier16: 没有标记不再是 absent", RD, RTC,
     '''return {"status": "absent"}
    if count >= 2:''',
     '''return {"status": "unavailable", "error": "absent"}
    if count >= 2:''', "killed"),
    ("tier16: 不再要求标记独占一行", RD, RTC,
     '''if not (line.startswith(TIER_MARKER_PREFIX) and line.endswith("-->")):''',
     '''if False:''', "killed"),
    ("tier16: 独占一行只看开头不看结尾", RD, RTC,
     '''and line.endswith("-->")):''',
     '''and True):''', "killed"),
    ("tier16: 独占一行只看结尾不看开头", RD, RTC,
     '''if not (line.startswith(TIER_MARKER_PREFIX) and ''',
     '''if not (''', "killed"),
    ("tier16: 标记行不再去掉前后空白", RD, RTC,
     '''if TIER_MARKER_PREFIX in ln).strip()''',
     '''if TIER_MARKER_PREFIX in ln)''', "killed"),
    ("tier16: tier 取值大小写不敏感", RD, RTC,
     '''if tier not in UPSTREAM_TIERS:''',
     '''if tier.upper() not in UPSTREAM_TIERS:''', "killed"),
    ("tier16: failures 接受负数", RD, RTC,
     '''r"[0-9]+", failures''',
     '''r"-?[0-9]+", failures''', "killed"),
    ("tier16: 注释结束符后还有内容也接受", RD, RTC,
     '''if "-->" in inner or match is None:''',
     '''if match is None:''', "killed"),
    ("tier16: 结果里漏出 reason 原文", RD, RTC,
     '''"reason_present": bool(reason)}''',
     '''"reason_present": bool(reason), "reason": reason}''', "killed"),
    ("tier16: reason_present 恒为 False", RD, RTC,
     '''"reason_present": bool(reason)}''',
     '''"reason_present": False}''', "killed"),
    ("tier16: reason 哈希算错对象", RD, RTC,
     '''hashlib.sha256(reason.encode("utf-8"))''',
     '''hashlib.sha256(b"")''', "killed"),
    ("tier16: failures 合法时不回传", RD, RTC,
     '''result["failures"] = int(failures)''',
     '''pass''', "killed"),
    ("tier16: 标记与信封 tier 不一致仍采纳", RD, RTC,
     '''if marker["tier"] != envelope_tier:''',
     '''if False:''', "killed"),
    ("tier16: 非法标记不挡住信封 tier", RD, RTC,
     '''if marker["status"] == "unavailable" or envelope_tier is None:''',
     '''if marker["status"] == "absent" and envelope_tier is None:''', "killed"),
    ("tier16: 只有信封 tier 时不再采纳", RD, RTC,
     '''if marker["status"] == "absent":
        return {"status": "accepted", "source": "envelope"''',
     '''if marker["status"] == "absent" and False:
        return {"status": "accepted", "source": "envelope"''', "killed"),
    ("tier16: v2 信封非法 tier 被接受", RD, RTC,
     '''if "tier" in raw and tier not in UPSTREAM_TIERS:''',
     '''if False:''', "killed"),
    ("tier16: v1 信封也允许 tier 字段", RD, RTC,
     '''allowed_fields = base_fields | {"tier"} if version == 2 else base_fields''',
     '''allowed_fields = base_fields | {"tier"}''', "killed"),
    ("tier16: v1 信封不再被接受", RD, RTC,
     '''version not in (1, 2)''',
     '''version != 2''', "killed"),
    # ── Task 17：pin > floor > tier > 推断，tier_conflict ──
    ("tier17: 上游 L3 在 floor 下也记成冲突（< 改成 <=）", RD, RTC,
     '''UPSTREAM_TIERS.index(routed) < UPSTREAM_TIERS.index(FLOOR_TIER)''',
     '''UPSTREAM_TIERS.index(routed) <= UPSTREAM_TIERS.index(FLOOR_TIER)''', "killed"),
    ("tier17: floor 比较写反（上游 L1 压穿 floor）", RD, RTC,
     '''UPSTREAM_TIERS.index(routed) < UPSTREAM_TIERS.index(FLOOR_TIER)''',
     '''UPSTREAM_TIERS.index(routed) > UPSTREAM_TIERS.index(FLOOR_TIER)''', "killed"),
    ("tier17: 没有 floor 也按冲突处理（上游不能低于推断）", RD, RTC,
     '''if floor and UPSTREAM_TIERS.index''',
     '''if UPSTREAM_TIERS.index''', "killed"),
    ("tier17: floor 判据丢了不可逆", RD, RTC,
     '''return (signals["side_effect"] == "external_or_irreversible"
            or''',
     '''return (False
            or''', "killed"),
    ("tier17: floor 判据丢了验收缺失/歧义", RD, RTC,
     '''or signals["acceptance"] == "missing_or_ambiguous"
            or signals["scope"]''',
     '''or False
            or signals["scope"]''', "killed"),
    ("tier17: floor 判据丢了跨模块", RD, RTC,
     '''or signals["scope"] == "cross_cutting" or''',
     '''or False or''', "killed"),
    ("tier17: floor 判据丢了取舍", RD, RTC,
     '''or signals["decision_load"] == "tradeoff")


def _requirements''',
     '''or False)


def _requirements''', "killed"),
    ("tier17: 低置信保守档被当成 floor（D2 被推翻）", RD, RTC,
     '''return _danger_signals(signals) and required == TIER_REQUIREMENTS[FLOOR_TIER]''',
     '''return required == TIER_REQUIREMENTS[FLOOR_TIER]''', "killed"),
    ("tier17: 只读豁免失效（只读任务验收缺失也算 floor）", RD, RTC,
     '''return _danger_signals(signals) and required == TIER_REQUIREMENTS[FLOOR_TIER]''',
     '''return _danger_signals(signals)''', "killed"),
    ("tier17: tier_conflict 恒不写", RD, RTC,
     '''if tier_conflict is not None:''',
     '''if False:''', "killed"),
    ("tier17: tier_conflict 恒写（无冲突写 null）", RD, RTC,
     '''if tier_conflict is not None:''',
     '''if True:''', "killed"),
    ("tier17: pin 请求不报 pin", RD, RTC,
     '''if requested.get("pinned") is True:
        tier_source = "pin"''',
     '''if False:
        tier_source = "pin"''', "killed"),
    ("tier17: floor 来源标成 inferred", RD, RTC,
     '''tier_source = "floor" if floor else "inferred"''',
     '''tier_source = "inferred"''', "killed"),
    ("tier17: 冲突时来源标成 upstream", RD, RTC,
     '''tier_conflict = {"upstream": declared, "floor": FLOOR_TIER}
''',
     '''tier_conflict = {"upstream": declared, "floor": FLOOR_TIER}
            tier_source = "upstream"
''', "killed"),
    ("tier17: 采纳上游 tier 后来源仍写 inferred", RD, RTC,
     '''required = list(TIER_REQUIREMENTS[routed])
            tier_source = "upstream"''',
     '''required = list(TIER_REQUIREMENTS[routed])
            tier_source = "inferred"''', "killed"),
    ("tier17: 冲突记录里 floor 档写错", RD, RTC,
     '''"floor": FLOOR_TIER}''',
     '''"floor": "L2"}''', "killed"),
    # ── Task 18：真实适配层入口：tier 字段进日志、日志不漏原文 ──
    ("tier18: Claude 薄壳把任务原文写进日志", CH, TTG,
     '''rec.update(routing_version=2, subagent_type=subagent_type,''',
     '''rec.update(prompt=prompt, routing_version=2, subagent_type=subagent_type,''', "killed"),
    ("tier18: Codex 薄壳把任务原文（或不透明令牌）写进日志", CX, TGC,
     '''"task_name": ti.get("task_name"), "text_source": source, "prompt_chars": len(text),''',
     '''"task_name": ti.get("task_name"), "text_source": source, "prompt_chars": len(text), "task": text,''', "killed"),
    ("tier18: 核心把 reason 原文留在结果里（Claude 日志）", RD, TTG,
     '''"reason_present": bool(reason)}''',
     '''"reason_present": bool(reason), "reason": reason}''', "killed"),
    ("tier18: 核心把 reason 原文留在结果里（Codex 日志）", RD, TGC,
     '''"reason_present": bool(reason)}''',
     '''"reason_present": bool(reason), "reason": reason}''', "killed"),
    ("tier18: tier_source 没进决策（Claude 日志）", RD, TTG,
     '''"upstream_tier": upstream, "tier_source": tier_source}''',
     '''"upstream_tier": upstream}''', "killed"),
    ("tier18: tier_source 没进决策（Codex 日志）", RD, TGC,
     '''"upstream_tier": upstream, "tier_source": tier_source}''',
     '''"upstream_tier": upstream}''', "killed"),
    ("tier18: tier_conflict 没进决策（Claude 日志）", RD, TTG,
     '''if tier_conflict is not None:''',
     '''if False:''', "killed"),
    ("tier18: tier_conflict 没进决策（Codex 日志）", RD, TGC,
     '''if tier_conflict is not None:''',
     '''if False:''', "killed"),
    ("tier18: 上游 tier 在 Claude 派活路径上没被解析（标记文本不再传给路由）", CH, TTG,
     '''"task": prompt,
        "host": "claude-code",''',
     '''"task": "",
        "host": "claude-code",''', "killed"),
    # ── Task 19：失败计数 → 升档与收回记录 ──
    ("tier19: 升档阈值上移一位（失败 1 次不升档）", RD, RTC,
     '''routed = "L2" if declared == "L1" and failures >= 1 else declared''',
     '''routed = "L2" if declared == "L1" and failures >= 2 else declared''', "killed"),
    ("tier19: 升档阈值下移一位（失败 0 次也升档）", RD, RTC,
     '''routed = "L2" if declared == "L1" and failures >= 1 else declared''',
     '''routed = "L2" if declared == "L1" and failures >= 0 else declared''', "killed"),
    ("tier19: n=0 / 未升档也写 escalation", RD, RTC,
     '''if routed != declared:''',
     '''if True:''', "killed"),
    ("tier19: escalation.to 用 floor 之前的档", RD, RTC,
     '''"to": effective, "consecutive_failures": failures}''',
     '''"to": routed, "consecutive_failures": failures}''', "killed"),
    ("tier19: tier_conflict 记升档后的档而不是声明档", RD, RTC,
     '''tier_conflict = {"upstream": declared, "floor": FLOOR_TIER}''',
     '''tier_conflict = {"upstream": routed, "floor": FLOOR_TIER}''', "killed"),
    ("tier19: 收回按有效档而不是声明档判定", RD, RTC,
     '''if declared == "L2" and failures >= 2:''',
     '''if effective == "L2" and failures >= 2:''', "killed"),
    ("tier19: 收回阈值上移一位（失败 2 次不收回）", RD, RTC,
     '''if declared == "L2" and failures >= 2:''',
     '''if declared == "L2" and failures >= 3:''', "killed"),
    ("tier19: 收回阈值下移一位（失败 1 次就收回）", RD, RTC,
     '''if declared == "L2" and failures >= 2:''',
     '''if declared == "L2" and failures >= 1:''', "killed"),
    ("tier19: 收回改动了路由目标", RD, RTC,
     '''reclaim = {"tier": "L2", "consecutive_failures": failures}''',
     '''reclaim = {"tier": "L2", "consecutive_failures": failures}
            required = list(TIER_REQUIREMENTS["L3"])''', "killed"),
    ("tier19: 升档也施加在 L2 上（L2 失败 1 次升到 L3）", RD, RTC,
     '''routed = "L2" if declared == "L1" and failures >= 1 else declared''',
     '''routed = "L3" if declared == "L2" and failures >= 1 else ("L2" if declared == "L1" and failures >= 1 else declared)''', "killed"),
    ("tier19: 升档施加在 L3 上（把档位压低，单调性被破坏）", RD, RTC,
     '''routed = "L2" if declared == "L1" and failures >= 1 else declared''',
     '''routed = "L2" if failures >= 1 else declared''', "killed"),
    ("tier19: escalation 不记失败计数", RD, RTC,
     '''"to": effective, "consecutive_failures": failures}''',
     '''"to": effective}''', "killed"),
    ("tier19: reclaim 不记失败计数", RD, RTC,
     '''reclaim = {"tier": "L2", "consecutive_failures": failures}''',
     '''reclaim = {"tier": "L2"}''', "killed"),
    # ── Task 20：L2 第二次失败 → 收回 deny / remind ──
    ("tier20: 收回判据忽略 off（off 也收回）", RD, RDT,
     '''    if profile == "off":
        return None
    if host_gate''',
     '''    if False:
        return None
    if host_gate''', "killed"),
    ("tier20: 收回判据忽略闸门（闸门关也收回）", RD, RDT,
     '''if host_gate is not True or pinned is not False:
        return None
    if not (isinstance''',
     '''if pinned is not False:
        return None
    if not (isinstance''', "killed"),
    ("tier20: 收回判据忽略 pin（pin 也收回）", RD, RDT,
     '''if host_gate is not True or pinned is not False:
        return None
    if not (isinstance''',
     '''if host_gate is not True:
        return None
    if not (isinstance''', "killed"),
    ("tier20: 收回判据把判不出 pin（None）当成未 pin", RD, RDT,
     '''if host_gate is not True or pinned is not False:
        return None
    if not (isinstance''',
     '''if host_gate is not True or pinned is True:
        return None
    if not (isinstance''', "killed"),
    ("tier20: 决策里没有 reclaim 也收回", RD, RDT,
     '''if not (isinstance(decision, dict) and decision.get("reclaim")):
        return None''',
     '''if False:
        return None''', "killed"),
    ("tier20: audit 也 deny（audit 与 guard 不分）", RD, RDT,
     '''return "remind" if profile == "audit" else "deny"''',
     '''return "deny"''', "killed"),
    ("tier20: guard/auto 只提醒（deny 与 remind 对调）", RD, RDT,
     '''return "remind" if profile == "audit" else "deny"''',
     '''return "deny" if profile == "audit" else "remind"''', "killed"),
    ("tier20: auto 只提醒（auto 与 guard 不分）", RD, RDT,
     '''return "remind" if profile == "audit" else "deny"''',
     '''return "remind" if profile in ("audit", "auto") else "deny"''', "killed"),
    ("tier20: 收回文案不带失败计数", RD, RDT,
     '''（上游报告连续失败 {n} 次）''',
     '''（上游报告连续失败）''', "killed"),
    ("tier20: Claude 收回晚于 nudge 判定（消耗了 nudge 标记）", CH, TTG,
     '''        n = {"action": "none", "text": None}
    else:''',
     '''        n = rd.nudge_decision(mode, nudge_pin, host_nudge_gate, session_id, tier_state.nudge_already_denied(session_id), nudge_summary)
    else:''', "killed"),
    ("tier20: Codex 收回晚于 nudge 判定（消耗了 nudge 标记）", CX, TGC,
     '''        n = {"action": "none", "text": None}
    else:''',
     '''        n = rd.nudge_decision(mode, nudge_pin, host_nudge_gate, session_id, tier_state.nudge_already_denied(session_id), nudge_summary)
    else:''', "killed"),
    ("tier20: Claude 收回 deny 带 updatedInput", CH, TTG,
     '''"permissionDecisionReason": reclaim_text}}''',
     '''"permissionDecisionReason": reclaim_text, "updatedInput": ti}}''', "killed"),
    ("tier20: Codex 收回 deny 带 updatedInput", CX, TGC,
     '''"permissionDecisionReason": reclaim_text}}''',
     '''"permissionDecisionReason": reclaim_text, "updatedInput": ti}}''', "killed"),
    ("tier20: Claude 收回原因里带任务原文", CH, TTG,
     '''"permissionDecisionReason": reclaim_text}}''',
     '''"permissionDecisionReason": reclaim_text + prompt}}''', "killed"),
    ("tier20: Codex 收回原因里带任务原文", CX, TGC,
     '''"permissionDecisionReason": reclaim_text}}''',
     '''"permissionDecisionReason": reclaim_text + text}}''', "killed"),
    ("tier20: Claude 不记 reclaim_output", CH, TTG,
     '''rec["reclaim_output"] = reclaim_output  # 只记输出了什么，不记任何文本''',
     '''pass''', "killed"),
    ("tier20: Codex 不记 reclaim_output", CX, TGC,
     '''rec["reclaim_output"] = reclaim_output  # 只记输出了什么，不记任何文本''',
     '''pass''', "killed"),
    ("tier20: Claude 收回要求 session_id", CH, TTG,
     '''reclaim_output = rd.reclaim_decision(mode, nudge_pin, host_nudge_gate, d)''',
     '''reclaim_output = rd.reclaim_decision(mode, nudge_pin, host_nudge_gate, d) if session_id else None''', "killed"),
    ("tier20: Codex 收回要求 session_id", CX, TGC,
     '''reclaim_output = rd.reclaim_decision(mode, nudge_pin, host_nudge_gate, d)''',
     '''reclaim_output = rd.reclaim_decision(mode, nudge_pin, host_nudge_gate, d) if session_id else None''', "killed"),
    ("tier20: Claude audit 收回提醒文本丢失", CH, TTG,
     '''    if reclaim_output == "remind":
        reminder_text = reclaim_text''',
     '''    if reclaim_output == "remind":
        reminder_text = ""''', "killed"),
    ("tier20: Claude audit 收回提醒不输出", CH, TTG,
     '''if nudge_status == "reminded" or reclaim_output == "remind":''',
     '''if nudge_status == "reminded":''', "killed"),
    ("tier20: Codex audit 收回提醒不输出", CX, TGC,
     '''if nudge_status == "reminded" or reclaim_output == "remind":''',
     '''if nudge_status == "reminded":''', "killed"),
    # ── 首次 deny 文案不写模式名（曾写死「（auto）」，guard 下显示错误）──
    ("nudge: deny 文案写回模式名「（auto）」", RD, RDT,
     '''NUDGE_DENY_TEXT = "tier-guard：本会话''',
     '''NUDGE_DENY_TEXT = "tier-guard（auto）：本会话''', "killed"),
    # ── 用量按 message.id 去重（SubagentStop 记录） ──
    ("usage-dedup: 退回逐行累加（不按 message.id 去重）", CH, TTG,
     '''if isinstance(mid, str) and mid:''',
     '''if False:''', "killed"),
    ("usage-dedup: 同 id 取最小而不是最大", CH, TTG,
     '''sum(line_usage.values()) > sum(prev.values())''',
     '''sum(line_usage.values()) < sum(prev.values())''', "killed"),
    ("usage-dedup: 没有 id 的行被合并成一条", CH, TTG,
     '''if isinstance(mid, str) and mid:''',
     '''if True:''', "killed"),
    ("usage-dedup: usage_basis 恒写（用量未知也写）", CH, TTG,
     '''    if usage is not None:
        # 标记这条记录''',
     '''    if True:
        # 标记这条记录''', "killed"),
    ("usage-dedup: usage_basis 从不写", CH, TTG,
     '''rec["usage_basis"] = "message-id-dedup"''',
     '''pass''', "killed"),
]

SUMMARY = re.compile(r"总计 [1-9]\d* 通过 / 0 失败|route contract: OK")


def green(repo, suite):
    try:
        r = subprocess.run(list(suite), cwd=repo, capture_output=True, text=True, timeout=300)
    except subprocess.TimeoutExpired:
        return False
    # 退出码和汇总行都看，别只信一个
    return r.returncode == 0 and SUMMARY.search(r.stdout) is not None


def main(argv):
    only = None
    if "--only" in argv:
        i = argv.index("--only")
        if i + 1 >= len(argv):
            print("  ❌ --only 后面要跟关键词")
            return 1
        only = argv[i + 1]
    selected = [m for m in M if only is None or only in m[0]]
    if not selected:
        print("  ❌ 一个变异体都没选中 —— 这不是「全部被抓到」，是「什么都没测」")
        return 1

    killed, survived, stale = [], [], []
    tmp = tempfile.mkdtemp(prefix="tier-guard-mutation-")
    try:
        repo = os.path.join(tmp, "repo")
        shutil.copytree(ROOT, repo, ignore=shutil.ignore_patterns(".git", "__pycache__"))
        # 基线：没变异时套件必须是绿的。不查的话，套件路径写错 / 环境坏掉会让
        # 每个变异体都「被抓到」—— 全绿，一次都没真测。
        base_ok = {}
        for desc, rel, suite, old, new, expect in selected:
            path = os.path.join(repo, rel)
            with open(path, encoding="utf-8") as fh:
                src = fh.read()
            n = src.count(old)
            if n != 1:
                stale.append(desc)
                print(f"  ⚠️  锚点失效（出现 {n} 次，应为 1）: {desc}", flush=True)
                continue
            if suite not in base_ok:
                base_ok[suite] = green(repo, suite)
                print(f"  {'基线绿' if base_ok[suite] else '⛔ 基线就不是绿的'}: {' '.join(suite)}", flush=True)
            if not base_ok[suite]:
                stale.append(f"{desc}（基线不绿，本条没测）")
                continue
            try:
                with open(path, "w", encoding="utf-8") as fh:
                    fh.write(src.replace(old, new, 1))
                died = not green(repo, suite)
            finally:
                with open(path, "w", encoding="utf-8") as fh:
                    fh.write(src)
            good = died if expect == "killed" else not died
            (killed if good else survived).append(desc)
            if died:
                mark = "✅ 抓到" if expect == "killed" else "⚠️  本以为等价却被抓到了（裁决过期）"
            else:
                mark = "❌ 活下来" if expect == "killed" else "✅ 如期等价"
            print(f"  {mark}: {desc}", flush=True)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    print()
    print(f"  符合预期 {len(killed)} / 不符 {len(survived)} / 锚点失效 {len(stale)}")
    if survived:
        print("\n  不符预期的变异体 —— 这些路径上没有断言：")
        for d in survived:
            print(f"    · {d}")
    return 1 if (survived or stale) else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
