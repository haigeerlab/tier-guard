#!/usr/bin/env python3
"""Claude 薄壳的 Python 半边（入口是 tier-guard.sh）。

判据一行都不在这里 —— 全在 route_decide.py。这里只做 Claude 专属的三件事：
  1. 找 agent 定义拿 frontmatter 的 model（项目 .claude/agents → ~/.claude/agents；
     `plugin:name` 形式的插件 agent 不解析，R2 也就不判）
  2. 记日志（JSONL；只记 prompt 的长度和 sha256，不记原文 —— prompt 里可能有密钥）
  3. 按宿主编码输出。Codex 薄壳（Task 4b）的编码不同，不共用这份

三个事件：
  agent          PreToolUse(Agent)：路由 + 主代理预路由提醒（Task 10）。v2 stdout 在三种
                 情况下有内容：mode=auto 且未 pin、需要应用目标时（updatedInput）；宿主
                 `dispatch_nudge=true` 且未 pin 时的提醒（additionalContext，audit/auto 皆可能
                 出现，可能与 updatedInput 合并在同一个 hookSpecificOutput 里）；auto 下同一
                 session 第一次未 pin 派活的 deny（permissionDecision，此时绝不带 updatedInput）。
                 v1 raise 路径仅为兼容
  bash           PreToolUse(Bash) 且命令里有 codex-exec.sh：只记「建议 vs 实际」，任何
                 mode 下都不输出（Task 4a：提议式，绝不改用户批准过的派活命令）
  subagent-stop  SubagentStop：记实际执行模型（读子代理 transcript）与是否升级触发。
                 关联键是 transcript 旁 .meta.json 的 toolUseId（= PreToolUse 的 tool_use_id），
                 没有就退回首条 prompt 的 sha256。永不输出 —— 不挡子代理结束

stdout 为空 + 退出 0 = 没装这个 hook。任何异常都走这条路，并在日志里写 fallback。
"""
import datetime
import hashlib
import json
import os
import shlex
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import route_decide as rd  # noqa: E402
import tier_state  # noqa: E402  数据目录 / mode 的解析顺序只写在那边


def write_log(rec):
    d = tier_state.data_dir()
    os.makedirs(d, mode=0o700, exist_ok=True)
    fd = os.open(os.path.join(d, "decisions.jsonl"), os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o600)
    with os.fdopen(fd, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(rec, ensure_ascii=False) + "\n")


def _frontmatter(path):
    with open(path, encoding="utf-8") as fh:
        lines = fh.read().splitlines()
    if not lines or lines[0].strip() != "---":
        return None
    fm = {}
    for line in lines[1:]:
        if line.strip() == "---":
            return fm
        key, sep, val = line.partition(":")
        if sep and not line[:1].isspace():
            fm[key.strip()] = val.strip().strip("'\"")
    return None                                    # 没闭合的 frontmatter 不算


def agent_dirs(payload):
    project = os.environ.get("CLAUDE_PROJECT_DIR") or payload.get("cwd") or os.getcwd()
    return [os.path.join(project, ".claude", "agents"),
            os.path.join(os.path.expanduser("~"), ".claude", "agents")]


def resolve_agent_model(subagent_type, dirs):
    """→ (找到没有, model)。model=None 表示文件里没钉 model。按 name 匹配，不按文件名。"""
    if not subagent_type or ":" in subagent_type:
        return False, None
    for d in dirs:
        try:
            names = sorted(os.listdir(d))
        except OSError:
            continue
        for n in names:
            if not n.endswith(".md"):
                continue
            try:
                fm = _frontmatter(os.path.join(d, n))
            except (OSError, UnicodeDecodeError):
                continue
            if fm is not None and fm.get("name", n[:-3]) == subagent_type:
                model = (fm.get("model") or "").strip()
                if model.lower() in _MODEL_NOT_A_CHOICE:
                    model = ""
                return True, model or None
    return False, None


def parse_codex_exec(command):
    """从 Bash 命令里抠出 codex-exec.sh 的 --model / --effort / 任务文本。认不出 → None。"""
    lex = shlex.shlex(command, posix=True, punctuation_chars=True)
    lex.whitespace_split = True
    tokens = list(lex)
    starts = [i for i, t in enumerate(tokens) if os.path.basename(t) == "codex-exec.sh"]
    if not starts:
        return None
    model = effort = task = None
    args, i = tokens[starts[0] + 1:], 0
    while i < len(args):
        a = args[i]
        if set(a) <= set(";&|<>()"):              # 到下一条命令为止
            break
        if a in ("--model", "--effort") and i + 1 < len(args):
            if a == "--model":
                model = args[i + 1]
            else:
                effort = args[i + 1]
            i += 2
            continue
        if a not in ("--write", "--"):
            task = a                               # codex-exec.sh 取最后一个位置参数
        i += 1
    return {"model": model, "effort": effort, "task": task}


def _base_record(event, payload, prompt):
    return {"ts": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"),
            "event": event, "session_id": payload.get("session_id"),
            "tool_use_id": payload.get("tool_use_id"),
            "prompt_chars": len(prompt),
            "prompt_sha256": hashlib.sha256(prompt.encode("utf-8")).hexdigest()}


def on_agent(payload, cfg, mode):
    ti = payload.get("tool_input")
    if not isinstance(ti, dict):
        ti = {}
    ctx = {"executor": "claude"}
    if mode:
        ctx["mode"] = mode
    found, model = resolve_agent_model(ti.get("subagent_type"), agent_dirs(payload))
    if found:
        ctx["agent_model"] = model
    d = rd.decide(payload, cfg, ctx)
    prompt = ti.get("prompt") if isinstance(ti.get("prompt"), str) else ""
    rec = _base_record("agent", payload, prompt)
    rec.update(subagent_type=ti.get("subagent_type"), **tier_state.text_digest("description", ti.get("description")),
               requested_model=ti.get("model"), agent_model=ctx.get("agent_model", "(未解析)"),
               transcript_path=payload.get("transcript_path"), decision=d, applied=False)
    out = None
    # **唯一**会产出 updatedInput 的地方，只在 auto 下。dry-run / off 走不到这里。
    if d["mode"] == "auto" and d["action"] == "raise" and d["target_model"] and not d["fallback"]:
        new_ti = dict(ti)
        new_ti["model"] = d["target_model"]
        out = {"hookSpecificOutput": {"hookEventName": "PreToolUse", "updatedInput": new_ti}}
        rec["applied"] = True
    return rec, out


# Claude Code 2.1.289 读这两个变量决定子代理模型：前者强制（并让 model 参数被忽略），
# 后者是默认值。用户设了就是显式选择，和 tool_input.model 一样是 pin，绝不改写。
# 宿主自身把空值、inherit、default 当作没设，这里与它保持一致，否则会把「没设」当成 pin。
_ENV_MODEL_VARS = ("CLAUDE_CODE_SUBAGENT_MODEL_FORCE", "CLAUDE_CODE_SUBAGENT_MODEL")
# 「跟随父代理」「用默认」都不是一次显式选择。env 与 agent frontmatter 两条路径共用这张表：
# 把它们当成 pin 会让整类派活静默地不再被路由，比漏判 pin 更难发现。
_MODEL_NOT_A_CHOICE = ("inherit", "default")


def env_subagent_model():
    """宿主配置的子代理模型；没设或被宿主忽略的取值 → None。"""
    for var in _ENV_MODEL_VARS:
        value = (os.environ.get(var) or "").strip()
        if value and value.lower() not in _MODEL_NOT_A_CHOICE:
            return value
    return None


def _nudge_pin(ti, subagent_type, found, agent_model, env_model=None):
    """主代理预路由提醒专用的 pin 判定，与上面路由用的 pinned 语义分开算：
    True=能确认已 pin，False=能确认未 pin，None=判不出（插件 agent），永不提醒。"""
    if ti.get("model"):
        return True
    if found and agent_model:
        return True
    if isinstance(subagent_type, str) and (subagent_type == "fork" or ":" in subagent_type):
        # fork 恒继承父代理模型、插件 agent 的 frontmatter 读不到：env 也改变不了「判不出」
        return None
    if env_model:
        return True
    return False


def on_agent_v2(payload, cfg, mode, catalog_identity):
    """把 Claude Agent 输入编码为 v2 RouteRequest。

    tool_input.model 和 agent frontmatter 的 model 都是用户已明确选择的 pin：记录推荐，
    但不改写。没有 pin 时，才由纯路由为本次子任务选择候选。

    同一事件上还驱动主代理预路由提醒（nudge，Task 10）：判据全在 route_decide.nudge_decision，
    这里只算 pin（与路由 pin 语义分开）、管每会话一次的 deny 标记、按宿主编码输出。
    """
    ti = payload.get("tool_input")
    if not isinstance(ti, dict):
        ti = {}
    prompt = ti.get("prompt") if isinstance(ti.get("prompt"), str) else ""
    subagent_type = ti.get("subagent_type")
    found, agent_model = resolve_agent_model(subagent_type, agent_dirs(payload))
    env_model = env_subagent_model()
    pinned = bool(ti.get("model")) or bool(found and agent_model) or bool(env_model)
    request = {
        "task": prompt,
        "host": "claude-code",
        "requested": {
            "model": ti.get("model") or agent_model or env_model,
            "reasoning_effort": None,
            "pinned": pinned,
        },
        "signals": {},
    }
    route_cfg = dict(cfg)
    route_cfg["mode"] = mode
    d = rd.route(request, route_cfg)
    host_pre_dispatch_apply = rd.host_auto_enabled(cfg, "claude-code")

    session_id = payload.get("session_id")
    nudge_pin = _nudge_pin(ti, subagent_type, found, agent_model, env_model)
    host_nudge_gate = rd.host_nudge_enabled(cfg, "claude-code")
    nudge_summary = rd.catalog_summary(cfg, "claude-code")
    # 收回（L2 第二次失败）先于 nudge 判定：命中就只输出收回，不检查也不消耗 nudge 标记。
    reclaim_output = rd.reclaim_decision(mode, nudge_pin, host_nudge_gate, d)
    if reclaim_output is not None:
        reclaim_text = rd.reclaim_text(reclaim_output, d["reclaim"]["consecutive_failures"])
        n = {"action": "none", "text": None}
    else:
        already_denied = tier_state.nudge_already_denied(session_id)
        n = rd.nudge_decision(mode, nudge_pin, host_nudge_gate, session_id, already_denied, nudge_summary)
    nudge_status, deny_reason, reminder_text = "none", None, None
    if n["action"] == "deny":
        if tier_state.claim_nudge_deny(session_id) == "created":
            nudge_status, deny_reason = "denied", n["text"]
        else:
            # 并发抢输（别的 hook 已 deny）或标记写不进去：都只提醒，保证每会话至多 deny 一次、且不会死循环拦截。
            nudge_status, reminder_text = "reminded", rd.nudge_text("remind", nudge_summary)
    elif n["action"] == "remind":
        nudge_status, reminder_text = "reminded", n["text"]

    rec = _base_record("agent", payload, prompt)
    rec.update(routing_version=2, subagent_type=subagent_type,
               **tier_state.text_digest("description", ti.get("description")), requested_model=ti.get("model"),
               agent_model=agent_model if found else "(未解析)",
               task_visibility=rd.task_visibility(prompt),
               transcript_path=payload.get("transcript_path"), decision=d,
               catalog_identity=catalog_identity, host_pre_dispatch_apply=host_pre_dispatch_apply,
               nudge=nudge_status, applied=False)
    if reclaim_output is not None:
        rec["reclaim_output"] = reclaim_output  # 只记输出了什么，不记任何文本

    if reclaim_output == "deny":
        # 收回 deny 同样压过 updatedInput 改写，auto 下也不例外。
        return rec, {"hookSpecificOutput": {"hookEventName": "PreToolUse",
                                             "permissionDecision": "deny",
                                             "permissionDecisionReason": reclaim_text}}
    if reclaim_output == "remind":
        reminder_text = reclaim_text

    if nudge_status == "denied":
        # deny 压过下面的 updatedInput 改写：本次调用绝不应用路由目标。
        return rec, {"hookSpecificOutput": {"hookEventName": "PreToolUse",
                                             "permissionDecision": "deny",
                                             "permissionDecisionReason": deny_reason}}

    out = None
    target = d.get("target") or {}
    # nudge_pin 为 None（fork / 插件 agent）即判不出是否 pin：不提醒也不改写
    if (mode == "auto" and host_pre_dispatch_apply and nudge_pin is False
            and d.get("action") in ("select", "lower", "raise")
            and target.get("model") and not d.get("fallback")):
        new_ti = dict(ti)
        new_ti["model"] = target["model"]
        out = {"hookSpecificOutput": {"hookEventName": "PreToolUse", "updatedInput": new_ti}}
        rec["applied"] = True

    if nudge_status == "reminded" or reclaim_output == "remind":
        if out is not None:
            out["hookSpecificOutput"]["additionalContext"] = reminder_text
        else:
            out = {"hookSpecificOutput": {"hookEventName": "PreToolUse", "additionalContext": reminder_text}}
    return rec, out


def on_bash(payload, cfg, mode):
    ti = payload.get("tool_input") or {}
    parsed = parse_codex_exec(ti.get("command") or "")
    if not parsed or not parsed["task"]:
        return None, None
    ctx = {"executor": "codex", "codex_model": parsed["model"], "codex_effort": parsed["effort"]}
    if mode:
        ctx["mode"] = mode
    d = rd.decide({"tool_name": "Agent", "tool_input": {"prompt": parsed["task"]}}, cfg, ctx)
    rec = _base_record("codex-dispatch", payload, parsed["task"])
    suggested = {"model": d["target_model"], "effort": d["target_reasoning_effort"]}
    actual = {"model": parsed["model"], "effort": parsed["effort"]}
    rec.update(actual=actual, suggested=suggested, decision=d,
               consistent=(actual == suggested) if d["tier"] else None)
    return rec, None                               # 提议式：任何 mode 下都不改命令


def _first_text(content):
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "".join(b.get("text", "") for b in content if isinstance(b, dict) and b.get("type") == "text")
    return None


USAGE_FIELDS = ("input_tokens", "cache_creation_input_tokens",
                "cache_read_input_tokens", "output_tokens")


def subagent_facts(transcript_path):
    """→ (meta, 首条 prompt, 实际模型, token 用量)。

    实际模型取第一条带 model 的 assistant 消息 —— 同一子代理内不变。
    用量必须跨全部 assistant 消息累加，所以这里读完整个文件，不能读到模型就停。
    同一条 assistant 消息（同一 message.id）宿主会写成多行（每个 content block 一行，流式过程中还会再写），
    必须按 id 去重：同 id 取用量合计最大的那一行（流式行只增不减，最大的是完整的）；没有 id 的行各算各的，
    绝不合并。实测 109 份 transcript 不去重会把 input 多算 1.97×、缓存写 1.96×、缓存读 1.83×。
    实测代价（2026-10-05，本机最大的 8 份 transcript，2.5MB / 1200 行级别）：读完 6.5–15.6ms，
    只读到首条 1.1–1.9ms；薄壳整体预算是中位 100ms、实测 32–50ms，这点开销吃得下。
    """
    meta = {}
    if transcript_path.endswith(".jsonl"):
        mp = transcript_path[:-len(".jsonl")] + ".meta.json"
        if os.path.isfile(mp):
            with open(mp, encoding="utf-8") as fh:
                meta = json.load(fh)
    prompt = model = None
    by_id = {}        # message.id → 该 id 下合计最大的那一行用量
    anonymous = []    # 没有 id 的行：逐行计入
    seen_usage = False
    with open(transcript_path, encoding="utf-8") as fh:
        for line in fh:
            try:
                msg = json.loads(line).get("message") or {}
            except (ValueError, AttributeError):
                continue
            if prompt is None and msg.get("role") == "user":
                prompt = _first_text(msg.get("content"))
            if model is None and msg.get("role") == "assistant" and msg.get("model"):
                model = msg["model"]
            u = msg.get("usage")
            if isinstance(u, dict):
                seen_usage = True
                line_usage = {field: (u[field] if isinstance(u.get(field), int) and not isinstance(u.get(field), bool) else 0)
                              for field in USAGE_FIELDS}
                mid = msg.get("id")
                if isinstance(mid, str) and mid:
                    prev = by_id.get(mid)
                    if prev is None or sum(line_usage.values()) > sum(prev.values()):
                        by_id[mid] = line_usage
                else:
                    anonymous.append(line_usage)
    usage = dict.fromkeys(USAGE_FIELDS, 0)
    for line_usage in list(by_id.values()) + anonymous:
        for field in USAGE_FIELDS:
            usage[field] += line_usage[field]
    # 宿主一条用量都没给时记未知，而不是一串 0 —— 0 会被读成「真的没花 token」。
    return meta, prompt, model, (usage if seen_usage else None)


def on_subagent_stop(payload, cfg, mode):
    path = payload.get("agent_transcript_path")
    if not isinstance(path, str) or not path:
        raise ValueError("SubagentStop payload 缺 agent_transcript_path")
    meta, prompt, model, _usage = subagent_facts(path)   # v1 冻结层：不记 usage，只跟上新签名
    rec = {"ts": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"),
           "event": "subagent-stop", "session_id": payload.get("session_id"),
           "tool_use_id": meta.get("toolUseId"), "agent_type": meta.get("agentType"),
           **tier_state.text_digest("description", meta.get("description")), "requested_model": meta.get("model"),
           "actual_model": model, "actual_tier": rd._family_tier(model, cfg) if model else None,
           "prompt_sha256": hashlib.sha256(prompt.encode("utf-8")).hexdigest() if prompt else None,
           "escalated": rd.escalated(payload.get("last_assistant_message"))}
    return rec, None                               # 永不输出：SubagentStop 的输出能挡住子代理结束


def on_subagent_stop_v2(payload):
    """v2 实际执行记录：model 只取子代理 transcript 里宿主写下的值；宿主不给 effort 就记 None。

    不做路由、不带 decision —— 报告按 tool_use_id 关联到 agent 记录。永不输出。
    """
    path = payload.get("agent_transcript_path")
    if not isinstance(path, str) or not path:
        raise ValueError("SubagentStop payload 缺 agent_transcript_path")
    # 先用 payload 里已知的事实把记录立起来，再去读 transcript。顺序反过来的话，读失败会把
    # 整条记录连同 session_id 和路径一起吞掉 —— 实测该路径占全部 stop 的 85.7%。
    rec = {"ts": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"),
           "event": "subagent-stop", "routing_version": 2, "session_id": payload.get("session_id"),
           "tool_use_id": None, "agent_type": None, "actual_execution": None,
           # 实测：触发时子代理唯一的 assistant 行可能还没落盘；留路径给报告回读，不留内容
           "agent_transcript_path": path, "prompt_sha256": None, "transcript_status": "ok",
           "usage": None}
    try:
        meta, prompt, model, usage = subagent_facts(path)
    except FileNotFoundError:
        # 宿主对某些子代理种类不写 transcript（实测：文件事后全盘也搜不到，不是落盘时序）。
        # 这是正常的宿主状况，不是守卫异常 —— 不占用 fallback 这个诊断位，否则真正的异常会被淹没。
        rec["transcript_status"] = "missing"
        return rec, None
    rec["tool_use_id"] = meta.get("toolUseId")
    rec["agent_type"] = meta.get("agentType")
    rec["actual_execution"] = {"model": model, "reasoning_effort": None} if model else None
    rec["prompt_sha256"] = hashlib.sha256(prompt.encode("utf-8")).hexdigest() if prompt else None
    rec["usage"] = usage
    if usage is not None:
        # 标记这条记录是按 message.id 去重后写的；更早的记录没有这个字段，其用量被重复计算过。
        rec["usage_basis"] = "message-id-dedup"
    return rec, None


def main(argv):
    event = argv[0] if argv else "agent"
    raw = sys.stdin.read()
    rec, out, mode = None, None, None
    try:
        payload = json.loads(raw)
        if not isinstance(payload, dict):
            raise ValueError("payload 不是 JSON 对象")
        configured_catalog = os.environ.get("TIER_GUARD_CONFIG")
        cfg, catalog_sha256 = rd.load_config_with_fingerprint(
            configured_catalog or rd.DEFAULT_CATALOG)
        if cfg.get("schema_version") == 2:
            catalog_identity = {"origin": "environment" if configured_catalog else "default",
                                "sha256": catalog_sha256}
            mode, _ = tier_state.read_mode(tier_state.data_dir(), cfg.get("mode"), rd.ROUTING_PROFILES)
            if mode not in rd.ROUTING_PROFILES:
                raise rd.ConfigError(f"未知 v2 mode {mode!r}")
            if event == "agent":
                rec, out = on_agent_v2(payload, cfg, mode, catalog_identity)
            elif event == "subagent-stop" and mode != "off":
                rec, out = on_subagent_stop_v2(payload)
            # Bash 的 v2 审计记录尚未迁移；在此之前静默放行，
            # 绝不把 v1 解释器拿来误读 v2 目录。
        else:
            mode, _ = tier_state.read_mode(tier_state.data_dir(), cfg.get("mode"))
            handler = {"bash": on_bash, "subagent-stop": on_subagent_stop}.get(event, on_agent)
            rec, out = handler(payload, cfg, mode)
    except Exception as e:                        # 守卫自己不能崩：放行，并说清是哪条路径
        rec = {"ts": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"),
               "event": event, "fallback": f"claude_hook: {type(e).__name__}: {e}"}
        out = None
    try:
        decision = rec.get("decision") if isinstance(rec, dict) else {}
        record_mode = (decision or {}).get("mode") or (decision or {}).get("profile")
        # off 一律不记：路由走兜底时决定里没有 profile，只看 record_mode 会漏（Phase 9 D7）
        if rec is not None and record_mode != "off" and mode != "off":
            write_log(rec)
    except Exception:
        pass                                       # 日志写不进去也不能挡住干活
    if out is not None:
        print(json.dumps(out, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
