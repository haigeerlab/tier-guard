#!/usr/bin/env python3
"""Codex 薄壳的 Python 半边（入口是 tier-guard-codex.sh）：PreToolUse(spawn_agent)。

判据一行都不在这里 —— 全在 route_decide.py（executor=codex）。这里只做 Codex 专属的事：
  1. 从 spawn_agent 的参数里取任务文本与起点档
  2. 记日志（与 Claude 侧同一数据目录解析：tier_state.data_dir；不记 prompt 原文）
  3. 按 **Codex 的**编码输出 —— updatedInput 必须与 permissionDecision:"allow" 同时出现
     （spike 实测：否则报 `PreToolUse hook returned updatedInput without permissionDecision:allow`）。
     Claude 侧不带 allow，所以两边的输出代码不共用。stdout 不只在 auto 改写参数时才有内容：
     v2 还会在宿主 `dispatch_nudge=true` 时输出主代理预路由提醒（Task 11）——
     audit/guard/auto 下的 additionalContext（可能与 updatedInput 合并在同一个 hookSpecificOutput 里），
     以及 guard（默认）/ auto 下同一 session 第一次未 pin 派活的 deny（此时绝不带 updatedInput）。
     生产目录里 Codex 的 dispatch_nudge 与 pre_dispatch_apply 都是关的，所以实际只记日志。

旧 v1 兼容分支的起点档规则（默认 v2 不使用）：
  - model = 显式 tool_input.model，否则继承的会话 model（payload.model，Codex schema 必填）
  - effort 只认显式 tool_input.reasoning_effort。继承时父会话的 effort 看不到 ——
    父会话若是 max，设成 xhigh 反而是降档，所以 effort 未知一律不动
  - (model, effort) 与配置里某档完全一致才算认出起点；否则不动
抬档只改 reasoning_effort（配置不变量保证 T1 / T2 同 slug），slug 不换。

默认 v2 路径按 RouteRequest 选择候选：tool_input 中未显式传 model/effort 时可同时选择 slug
与 effort；任一显式参数即 pin，不会改写。

输入 schema 来自本机 codex-cli 0.153.4 二进制内嵌的 `pre-tool-use.command.input`；
spawn_agent 参数（message / task_name / agent_type / model / reasoning_effort / service_tier / fork_*）
与 openai/codex 源码 SpawnAgentArgs 对得上（2026-09-12 查证）。
注意：Codex 的 hook 进程先 env_clear，启动 shell 里 export 的 TIER_GUARD_MODE 未必进得来 ——
切 mode 用 /tier-mode 写的状态文件。
"""
import datetime
import hashlib
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import route_decide as rd  # noqa: E402
import tier_state  # noqa: E402

# spawn_agent 的控制类参数：不算任务文本
CONTROL = {"task_name", "agent_type", "fork_turns", "fork_context", "nickname", "model",
           "reasoning_effort", "service_tier"}
SPAWN_TOOL_NAMES = {"Agent", "spawn_agent", "collaborationspawn_agent"}
SPAWN_TOOL_NAME_RE = re.compile(r"^collaboration[.:_]+spawn_agent$")


def is_spawn_tool_name(tool_name):
    """兼容 Codex V1 名、V2 扁平名及有分隔符的 namespaced 名。"""
    return isinstance(tool_name, str) and (
        tool_name in SPAWN_TOOL_NAMES or SPAWN_TOOL_NAME_RE.fullmatch(tool_name) is not None
    )


def _codex_nudge_pin(ti):
    """主代理预路由提醒专用的 pin 判定，与路由用的 pinned 语义分开算：True=已 pin，False=未 pin。

    `fork_turns`（none / all / N）只决定子代理继承多少历史，与 pin 无关：真实 Codex 每次都带它，
    且 rust-v0.154.0 spawn.rs 在区分 fork 模式之前就无条件应用 model / reasoning_effort 覆盖。"""
    if ti.get("model") or ti.get("reasoning_effort"):
        return True
    return False


def task_text(ti):
    """任务文本：优先 message / prompt，其次把非控制类的字符串参数拼起来。→ (文本, 来源字段)。"""
    for key in ("message", "prompt"):
        if isinstance(ti.get(key), str) and ti[key].strip():
            return ti[key], key
    parts = [(k, v) for k, v in ti.items() if k not in CONTROL and isinstance(v, str) and v.strip()]
    return "\n".join(v for _, v in parts), "+".join(k for k, _ in parts)


def write_log(rec):
    d = tier_state.data_dir()
    os.makedirs(d, mode=0o700, exist_ok=True)
    fd = os.open(os.path.join(d, "decisions.jsonl"), os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o600)
    with os.fdopen(fd, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(rec, ensure_ascii=False) + "\n")


def on_spawn(payload, cfg, mode):
    if not is_spawn_tool_name(payload.get("tool_name")):
        return None, None
    ti = payload.get("tool_input")
    if not isinstance(ti, dict):
        raise ValueError("payload 缺 tool_input")
    text, source = task_text(ti)
    ctx = {"executor": "codex", "mode": mode,
           "codex_model": ti.get("model") or payload.get("model"),
           "codex_effort": ti.get("reasoning_effort")}
    d = rd.decide({"tool_name": "Agent", "tool_input": {"prompt": text}}, cfg, ctx)
    rec = {"ts": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"),
           "event": "codex-spawn", "session_id": payload.get("session_id"),
           "tool_use_id": payload.get("tool_use_id"), **tier_state.text_digest("task_name", ti.get("task_name")),
           "text_source": source, "prompt_chars": len(text),
           "prompt_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
           "actual": {"model": ctx["codex_model"], "effort": ctx["codex_effort"]},
           "decision": d, "applied": False}
    out = None
    # **唯一**会产出 updatedInput 的地方，只在 auto 下。
    if d["mode"] == "auto" and d["action"] == "raise" and d["target_model"] and not d["fallback"]:
        new_ti = dict(ti)
        new_ti["model"] = d["target_model"]
        new_ti["reasoning_effort"] = d["target_reasoning_effort"]
        out = {"hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "allow",
            "permissionDecisionReason": f"tier-guard: 升到 {d['tier']}（{d['target_reasoning_effort']}）",
            "updatedInput": new_ti}}
        rec["applied"] = True
    return rec, out


def on_spawn_v2(payload, cfg, mode, catalog_identity):
    """把原生 Codex spawn_agent 输入编码为 v2 RouteRequest。

    父会话的 payload.model 是继承上下文，不等同于用户为这次子任务显式 pin 的参数；
    只有 tool_input 内出现 model 或 reasoning_effort 才禁止自动改写。

    同一事件上还驱动主代理预路由提醒（nudge，Task 11）：判据全在
    route_decide.nudge_decision，这里只算 pin（与路由 pin 语义分开、经 _codex_nudge_pin）、
    管每会话一次的 deny 标记（与 Claude 薄壳共用 tier_state 的原子标记）、按 Codex 编码输出——
    deny 只输出 permissionDecision/permissionDecisionReason，绝不带 updatedInput；
    remind 的 additionalContext 可以与上面的路由 updatedInput 合并进同一个 hookSpecificOutput。
    """
    if not is_spawn_tool_name(payload.get("tool_name")):
        return None, None
    ti = payload.get("tool_input")
    if not isinstance(ti, dict):
        raise ValueError("payload 缺 tool_input")
    text, source = task_text(ti)
    visibility = rd.task_visibility(text)
    pinned = bool(ti.get("model")) or bool(ti.get("reasoning_effort"))
    requested = {
        "model": ti.get("model") or payload.get("model"),
        "reasoning_effort": ti.get("reasoning_effort"),
        "pinned": pinned,
    }
    route_cfg = dict(cfg)
    route_cfg["mode"] = mode
    d = rd.route({"task": text, "host": "codex-cli", "requested": requested, "signals": {}}, route_cfg)
    host_pre_dispatch_apply = rd.host_auto_enabled(cfg, "codex-cli")

    session_id = payload.get("session_id")
    nudge_pin = _codex_nudge_pin(ti)
    host_nudge_gate = rd.host_nudge_enabled(cfg, "codex-cli")
    nudge_summary = rd.catalog_summary(cfg, "codex-cli")
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

    rec = {"ts": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"),
           "event": "codex-spawn", "routing_version": 2,
           "session_id": session_id, "tool_use_id": payload.get("tool_use_id"),
           **tier_state.text_digest("task_name", ti.get("task_name")), "text_source": source, "prompt_chars": len(text),
           "prompt_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
           "task_visibility": visibility,
           "catalog_identity": catalog_identity,
           "decision": d, "host_pre_dispatch_apply": host_pre_dispatch_apply,
           "nudge": nudge_status, "applied": False}
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
    if (mode == "auto" and host_pre_dispatch_apply
            and d.get("action") in ("select", "lower", "raise")
            and visibility == "visible"
            and target.get("model") and target.get("reasoning_effort") and not d.get("fallback")):
        new_ti = dict(ti)
        new_ti["model"] = target["model"]
        new_ti["reasoning_effort"] = target["reasoning_effort"]
        out = {"hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "allow",
            "permissionDecisionReason": f"tier-guard: v2 选择 {target['id']}",
            "updatedInput": new_ti}}
        rec["applied"] = True

    if nudge_status == "reminded" or reclaim_output == "remind":
        if out is not None:
            out["hookSpecificOutput"]["additionalContext"] = reminder_text
        else:
            out = {"hookSpecificOutput": {"hookEventName": "PreToolUse", "additionalContext": reminder_text}}
    return rec, out


def main(argv):
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
            rec, out = on_spawn_v2(payload, cfg, mode, catalog_identity)
        else:
            mode, _ = tier_state.read_mode(tier_state.data_dir(), cfg.get("mode"))
            rec, out = on_spawn(payload, cfg, mode)
    except Exception as e:                        # 守卫自己不能崩：放行，并说清是哪条路径
        rec = {"ts": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"),
               "event": "codex-spawn", "fallback": f"codex_hook: {type(e).__name__}: {e}"}
        out = None
    try:
        decision = rec.get("decision") if isinstance(rec, dict) else {}
        record_mode = (decision or {}).get("mode") or (decision or {}).get("profile")
        # off 一律不记：路由走兜底时决定里没有 profile，只看 record_mode 会漏（Phase 9 D7）
        if rec is not None and record_mode != "off" and mode != "off":
            write_log(rec)
    except Exception:
        pass
    if out is not None:
        print(json.dumps(out, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
