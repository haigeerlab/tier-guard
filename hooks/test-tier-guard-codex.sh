#!/bin/bash
# ─────────────────────────────────────────────────────────────
# Codex 薄壳（tier-guard-codex.sh + codex_hook.py）的回归断言。Task 4b 的离线部分。
#
# payload 形状照本机 codex-cli 0.153.4 内嵌的 pre-tool-use.command.input schema 造
# （必填：cwd / hook_event_name / model / permission_mode / session_id / tool_input /
#   tool_name / tool_use_id / transcript_path / turn_id）。
# 与 Claude 侧的关键差别：updatedInput 必须配 permissionDecision:"allow"。
# ─────────────────────────────────────────────────────────────
set -uo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
HOOK="${ROOT}/hooks/tier-guard-codex.sh"
TMP="$(mktemp -d)"
trap 'rm -rf "${TMP}"' EXIT
PASS=0; FAIL=0
check() { if [ "$2" = yes ]; then printf '  ✅ %s\n' "$1"; PASS=$((PASS+1)); else printf '  ❌ %s\n' "$1"; FAIL=$((FAIL+1)); fi; }
# yn 只包一条命令；复合条件写成具名函数（`$(yn A && B)` 是永远为真的空断言）
yn() { if "$@"; then echo yes; else echo no; fi; }
has() { case "$1" in *"$2"*) return 0 ;; *) return 1 ;; esac; }
LOGD="${TMP}/log"; FAKEHOME="${TMP}/home"; mkdir -p "${FAKEHOME}"

run() {  # $1=mode $2=payload → OUT / RC
  OUT="$(printf '%s' "$2" | env HOME="${FAKEHOME}" TIER_GUARD_LOG_DIR="${LOGD}" TIER_GUARD_MODE="$1" \
        TIER_GUARD_CONFIG="${ROOT}/config/routing.default.json" /bin/bash "${HOOK}")"
  RC=$?
}
runv2with() {  # $1=profile $2=payload $3=config → OUT / RC
  OUT="$(printf '%s' "$2" | env HOME="${FAKEHOME}" TIER_GUARD_LOG_DIR="${LOGD}" TIER_GUARD_MODE="$1" \
        TIER_GUARD_CONFIG="$3" /bin/bash "${HOOK}")"
  RC=$?
}
runv2() { runv2with "$1" "$2" "${ROOT}/config/routing.catalog.v2.json"; }
runv2verified() { runv2with "$1" "$2" "${V2_VERIFIED_CONFIG}"; }
V2_CATALOG_SHA="$(shasum -a 256 "${ROOT}/config/routing.catalog.v2.json" | awk '{print $1}')"
# $1=message $2=显式 model(- 不传) $3=显式 reasoning_effort(- 不传) [$4=会话 model] [$5=tool_name]
sp() {
  python3 - "$1" "$2" "$3" "${4:-gpt-5.6-terra}" "${5:-spawn_agent}" <<'PY'
import json, sys
msg, model, effort, session_model, tool = sys.argv[1:6]
ti = {"message": msg, "task_name": "t1", "agent_type": "worker", "fork_turns": "none"}
if model != "-":
    ti["model"] = model
if effort != "-":
    ti["reasoning_effort"] = effort
print(json.dumps({"session_id": "s", "turn_id": "t", "cwd": "/x", "hook_event_name": "PreToolUse",
                  "model": session_model, "permission_mode": "default", "transcript_path": None,
                  "tool_name": tool, "tool_use_id": "c1", "tool_input": ti}, ensure_ascii=False))
PY
}
jsonq() {  # $1=python 表达式（o = stdout 的 JSON）
  python3 - "$1" "${OUT}" <<'PY'
import json, sys
try:
    o = json.loads(sys.argv[2])
    print("yes" if eval(sys.argv[1]) else "no")
except Exception:
    print("no")
PY
}
lastlog() {
  python3 - "$1" "${LOGD}/decisions.jsonl" <<'PY'
import json, sys
try:
    r = json.loads(open(sys.argv[2], encoding="utf-8").read().splitlines()[-1])
    print("yes" if eval(sys.argv[1]) else "no")
except Exception:
    print("no")
PY
}
PAD="背景：这是一段中性的背景说明，只用来让 prompt 越过收益门槛，不含任何判据词。背景：这是一段中性的背景说明，只用来让 prompt 越过收益门槛。背景：再补一句中性的说明文字，凑够长度。"
AC=$'\n验收：pytest 全绿\n'
IRR="改完后 git push 到 origin。${AC}${PAD}"
SAFE="按 spec 第 3 节实现缓存层。${AC}${PAD}"
V2_VERIFIED_CONFIG="${TMP}/routing.catalog.v2.verified.json"
python3 - "${ROOT}/config/routing.catalog.v2.json" "${V2_VERIFIED_CONFIG}" <<'PY'
import json, sys
cfg = json.load(open(sys.argv[1], encoding="utf-8"))
cfg.setdefault("host_capabilities", {}).setdefault("codex-cli", {})["pre_dispatch_apply"] = True
with open(sys.argv[2], "w", encoding="utf-8") as fh:
    json.dump(cfg, fh, ensure_ascii=False)
PY

echo "═══ tier-guard-codex.sh 回归 ═══"

CODEX_MATCHERS="$(python3 - "${ROOT}/hooks/codex-hooks.json" <<'PY'
import json, sys
try:
    entries = json.load(open(sys.argv[1], encoding="utf-8"))["hooks"]["PreToolUse"]
    expected = "^(?:Agent|spawn_agent|collaborationspawn_agent|collaboration[.:_]+spawn_agent)$"
    print("yes" if {e.get("matcher") for e in entries} == {expected} else "no")
except Exception:
    print("no")
PY
)"
check "插件以单一严格 matcher 覆盖规范名、扁平 V2 名与分隔符兼容名" "${CODEX_MATCHERS}"

rm -rf "${LOGD}"
run off "$(sp "${IRR}" gpt-5.6-terra high)"
c_off() { [ "${RC}" -eq 0 ] && [ -z "${OUT}" ] && [ ! -e "${LOGD}/decisions.jsonl" ]; }
check "off：退出 0、stdout 空、不留日志" "$(yn c_off)"

run dry-run "$(sp "${IRR}" gpt-5.6-terra high)"
check "dry-run：欠配调用 stdout 仍为空" "$(yn [ "${RC}" -eq 0 -a -z "${OUT}" ])"
check "dry-run：日志记下 raise（起点 T1 → T2），applied=false" \
  "$(lastlog 'r["event"] == "codex-spawn" and r["decision"]["start_tier"] == "T1" and r["decision"]["action"] == "raise" and r["applied"] is False')"
check "dry-run：任务文本取自 message，日志不含原文" \
  "$(lastlog 'r["text_source"] == "message" and "改完后" not in json.dumps(r, ensure_ascii=False)')"

run auto "$(sp "${IRR}" gpt-5.6-terra high)"
check "auto：带 permissionDecision=allow（Codex 要求，Claude 侧没有）" \
  "$(jsonq 'o["hookSpecificOutput"]["permissionDecision"] == "allow" and o["hookSpecificOutput"]["hookEventName"] == "PreToolUse"')"
check "auto：只抬 effort 到 xhigh，slug 不换" \
  "$(jsonq 'o["hookSpecificOutput"]["updatedInput"]["reasoning_effort"] == "xhigh" and o["hookSpecificOutput"]["updatedInput"]["model"] == "gpt-5.6-terra"')"
check "auto：updatedInput 是完整参数（message / task_name / agent_type / fork_turns 原样）" \
  "$(jsonq 'o["hookSpecificOutput"]["updatedInput"]["message"].startswith("改完后") and o["hookSpecificOutput"]["updatedInput"]["task_name"] == "t1" and o["hookSpecificOutput"]["updatedInput"]["agent_type"] == "worker" and o["hookSpecificOutput"]["updatedInput"]["fork_turns"] == "none"')"
check "auto：日志标记已输出 updatedInput" "$(lastlog 'r["applied"] is True')"

run auto "$(sp "${IRR}" - high)"
check "auto：显式 effort + 继承会话 model（terra）也认得出 T1 → 抬到 xhigh" \
  "$(jsonq 'o["hookSpecificOutput"]["updatedInput"]["reasoning_effort"] == "xhigh"')"
run auto "$(sp "${IRR}" - -)"
check "auto：effort 继承（看不到父会话的 effort）→ 不动（父会话若是 max，设 xhigh 反而降档）" "$(yn [ -z "${OUT}" ])"
run auto "$(sp "${IRR}" gpt-5.6-sol high)"
check "auto：表外组合（sol）→ 不动" "$(yn [ -z "${OUT}" ])"
run auto "$(sp "${IRR}" gpt-5.6-terra xhigh)"
check "auto：已经是 T2（terra/xhigh）→ 不动" "$(yn [ -z "${OUT}" ])"
run auto "$(sp "${IRR}" gpt-5.6-terra max)"
check "auto：比 T2 还高（max）→ 不动（只升不降）" "$(yn [ -z "${OUT}" ])"
run auto "$(sp "${SAFE}" gpt-5.6-terra high)"
check "auto：无 floor 的 T1 调用 → 不动" "$(yn [ -z "${OUT}" ])"
run auto "$(sp "${IRR}" gpt-5.6-terra high gpt-5.6-terra exec_command)"
check "auto：不是 spawn_agent → 不动、不记" "$(yn [ -z "${OUT}" ])"

BAD=0
for msg in "${IRR}" "${SAFE}" "两种做法权衡后选一个。${AC}${PAD}" "把 foo 改名。${PAD}"; do
  for pair in "gpt-5.6-luna medium" "gpt-5.6-terra high" "gpt-5.6-terra xhigh" "- -" "gpt-6-astra high"; do
    set -- ${pair}
    run auto "$(sp "${msg}" "$1" "$2")"
    case "${OUT}" in *'"deny"'*|*'"ask"'*|*'"max"'*|*'"ultra"'*|*gpt-6-astra*|*gpt-5.6-sol*) BAD=$((BAD+1)) ;; esac
  done
done
check "auto：20 种组合里从不出现 deny / ask，也从不自动选 astra / sol / max / ultra" "$(yn [ "${BAD}" -eq 0 ])"
LEAK=0
for msg in "${IRR}" "${SAFE}" "两种做法权衡后选一个。${AC}${PAD}"; do
  for pair in "gpt-5.6-luna medium" "gpt-5.6-terra high" "- -"; do
    set -- ${pair}
    run dry-run "$(sp "${msg}" "$1" "$2")"
    [ -z "${OUT}" ] || LEAK=$((LEAK+1))
  done
done
check "dry-run：9 种组合里没有一条产出 stdout" "$(yn [ "${LEAK}" -eq 0 ])"

run auto 'not json'
check "payload 不是 JSON → 退出 0、stdout 空" "$(yn [ "${RC}" -eq 0 -a -z "${OUT}" ])"
check "payload 不是 JSON → 日志写明 fallback（codex_hook 自己接住）" "$(lastlog 'r["fallback"].startswith("codex_hook:")')"
mkdir -p "${TMP}/bin"; ln -s /bin/cat "${TMP}/bin/cat"; ln -s /usr/bin/dirname "${TMP}/bin/dirname"
OUT="$(printf '%s' "$(sp "${IRR}" gpt-5.6-terra high)" | env PATH="${TMP}/bin" TIER_GUARD_LOG_DIR="${LOGD}" TIER_GUARD_MODE=auto /bin/bash "${HOOK}")"; RC=$?
check "python3 不在 PATH → 退出 0、stdout 空" "$(yn [ "${RC}" -eq 0 -a -z "${OUT}" ])"

# ── v2 Codex CLI pre-dispatch：只验证宿主编码，判据由 route contract 覆盖 ──
V2SIMPLE="$(sp $'只读审查配置，禁止修改任何文件。\n验收：报告所有键名。' - -)"
runv2 audit "${V2SIMPLE}"
check "v2 audit：未 pin 的简单任务只记 select，stdout 空" "$(yn [ "${RC}" -eq 0 -a -z "${OUT}" ])"
check "v2 audit：记录 v2 决策且 applied=false" \
  "$(lastlog 'r["routing_version"] == 2 and r["decision"]["action"] == "select" and r["decision"]["target"] == {"id": "codex-luna-high", "model": "gpt-6-luna", "reasoning_effort": "high"} and r["applied"] is False')"
check "v2 audit：记录实际读取目录的来源与内容指纹，不记录路径" \
  "$(lastlog 'r["catalog_identity"] == {"origin": "environment", "sha256": "'"${V2_CATALOG_SHA}"'"}')"
check "v2 audit：派发前输入只记为 requested，不冒充实际执行" \
  "$(lastlog 'r["routing_version"] == 2 and "actual" not in r and r["decision"]["requested"]["model"] == "gpt-5.6-terra" and r["decision"]["requested"]["reasoning_effort"] is None')"
OPAQUE_TASK_TOKEN='gAAAAABqpV6vt1_VldXEBZKJFvQMBgplGnbDAsDfxP_Yk4J18GutDTltnSfReyHQokOmEoLYexQltP_gH8Dbbi8_fDfzmTT3f7YW0fSkHJDKu_ltyNhCSuj_uuO95A3l-T_uxvrekZ-TsnHEtBiGhf0Q66CtHM0kvnhOqAaXZCbfVIwuIUCA-9BdxAm9Us7zfcTWUO46R6Ka'
runv2 audit "$(sp "${OPAQUE_TASK_TOKEN}" - -)"
check "v2 audit：宿主不透明任务令牌明确标记，保守选高能力候选" \
  "$(lastlog 'r["task_visibility"] == "opaque_token" and r["decision"]["confidence"] == "low" and r["decision"]["target"]["id"] == "codex-sol-xhigh"')"
runv2verified auto "$(sp "${OPAQUE_TASK_TOKEN}" - -)"
check "v2 auto：不透明任务令牌不自动改写，避免无语义依据的升档" \
  "$(yn [ "${RC}" -eq 0 -a -z "${OUT}" ])"
check "v2 auto：不透明任务令牌保留审计但 applied=false" \
  "$(lastlog 'r["task_visibility"] == "opaque_token" and r["host_pre_dispatch_apply"] is True and r["applied"] is False')"
runv2 audit "$(sp $'实现 parse_duration，只动 util.py。\n验收：tests/test_util.py 全部通过。' - -)"
check "catalog25：v2 audit：L2（受限实现 + 明确验收）的 Codex 目标是 codex-luna-high" \
  "$(lastlog 'r["routing_version"] == 2 and r["decision"]["requirements"] == ["implementation", "bounded_change"] and r["decision"]["target"] == {"id": "codex-luna-high", "model": "gpt-6-luna", "reasoning_effort": "high"} and r["applied"] is False')"
runv2 audit "$(sp $'比较两种缓存架构并权衡后选一个。\n验收：给出取舍理由。' - -)"
check "catalog25：v2 audit：L3（取舍）的 Codex 目标仍是 codex-sol-xhigh" \
  "$(lastlog 'r["routing_version"] == 2 and r["decision"]["requirements"] == ["tradeoff", "cross_cutting"] and r["decision"]["target"]["id"] == "codex-sol-xhigh"')"
runv2 audit "$(sp $'完成后 git push 到 origin。\n验收：远端分支可见。' gpt-6-luna high)"
check "v2 audit：显式 pin 仍报告 luna/high → sol/xhigh 的 raise，但不产出 target" \
  "$(lastlog 'r["routing_version"] == 2 and r["decision"]["action"] == "raise" and r["decision"]["target"] is None and r["decision"]["recommended"]["id"] == "codex-sol-xhigh" and r["applied"] is False')"
rm -rf "${LOGD}"
runv2 audit "$(sp $'只读审查配置，禁止修改任何文件。\n验收：报告所有键名。' - - gpt-5.6-terra collaboration.spawn_agent)"
check "v2 audit：MultiAgentV2 原始工具名归一后也记录 select" \
  "$(lastlog 'r["routing_version"] == 2 and r["event"] == "codex-spawn" and r["decision"]["action"] == "select" and r["applied"] is False')"
rm -rf "${LOGD}"
runv2 audit "$(sp $'只读审查配置，禁止修改任何文件。\n验收：报告所有键名。' - - gpt-5.6-terra collaborationspawn_agent)"
check "v2 audit：MultiAgentV2 扁平工具名也记录 select" \
  "$(lastlog 'r["routing_version"] == 2 and r["event"] == "codex-spawn" and r["decision"]["action"] == "select" and r["applied"] is False')"
runv2 auto "${V2SIMPLE}"
check "v2 auto：未验证 Codex 宿主不得改写参数，仍只审计" \
  "$(yn [ "${RC}" -eq 0 -a -z "${OUT}" ])"
check "v2 auto：未验证 Codex 宿主记录 applied=false" \
  "$(lastlog 'r["routing_version"] == 2 and r["decision"]["action"] == "select" and r["applied"] is False and r["host_pre_dispatch_apply"] is False')"
runv2verified auto "${V2SIMPLE}"
check "v2 auto：已验证 Codex 宿主选择 luna/high 并带 allow" \
  "$(jsonq 'o["hookSpecificOutput"]["permissionDecision"] == "allow" and o["hookSpecificOutput"]["updatedInput"]["model"] == "gpt-6-luna" and o["hookSpecificOutput"]["updatedInput"]["reasoning_effort"] == "high"')"
check "v2 auto：已验证宿主只改 model / effort，保留完整 spawn 参数" \
  "$(jsonq 'o["hookSpecificOutput"]["updatedInput"]["message"].startswith("只读审查") and o["hookSpecificOutput"]["updatedInput"]["task_name"] == "t1" and o["hookSpecificOutput"]["updatedInput"]["agent_type"] == "worker" and o["hookSpecificOutput"]["updatedInput"]["fork_turns"] == "none"')"
check "v2 auto：已验证宿主的 updatedInput 输出可审计" \
  "$(lastlog 'r["routing_version"] == 2 and r["decision"]["action"] == "select" and r["host_pre_dispatch_apply"] is True and r["applied"] is True')"
runv2 auto "$(sp $'只读审查配置，禁止修改任何文件。\n验收：报告所有键名。' gpt-6.1-sol medium)"
check "v2 auto：显式 model / effort 是 pin，不改写" "$(yn [ -z "${OUT}" ])"
check "v2 auto：pin 留下建议但 target 为空" \
  "$(lastlog 'r["routing_version"] == 2 and r["decision"]["action"] == "pinned" and r["decision"]["target"] is None and r["decision"]["recommended"]["id"] == "codex-luna-high" and r["applied"] is False')"
runv2 auto "$(sp $'只读审查配置，禁止修改任何文件。\n验收：报告所有键名。' - high)"
check "v2 auto：仅显式 effort 也视为 pin，不改写" "$(yn [ -z "${OUT}" ])"
runv2verified auto "$(sp $'比较两种缓存架构并权衡后选一个实现。\n验收：给出取舍理由。' - -)"
check "v2 auto：复杂取舍任务选择 sol/xhigh" \
  "$(jsonq 'o["hookSpecificOutput"]["updatedInput"]["model"] == "gpt-6.1-sol" and o["hookSpecificOutput"]["updatedInput"]["reasoning_effort"] == "xhigh"')"
runv2verified auto "$(sp '处理这个问题。' - -)"
check "v2 auto：未知任务保守选择高能力候选" \
  "$(lastlog 'r["routing_version"] == 2 and r["decision"]["confidence"] == "low" and r["decision"]["target"]["id"] == "codex-sol-xhigh" and r["applied"] is True')"
rm -rf "${LOGD}"
runv2 auto "$(sp "${V2SIMPLE}" - - gpt-5.6-terra exec_command)"
check "v2：不是 spawn_agent → stdout 空、不留日志" \
  "$(yn [ "${RC}" -eq 0 -a -z "${OUT}" -a ! -e "${LOGD}/decisions.jsonl" ])"
runv2 auto '{"tool_name":"spawn_agent","tool_input":{"task_name":"t"}}'
check "v2：没有任务文本 → 退出 0、stdout 空且不应用" "$(yn [ "${RC}" -eq 0 -a -z "${OUT}" ])"
check "v2：没有任务文本 → fallback 可审计" \
  "$(lastlog 'r["routing_version"] == 2 and r["decision"]["action"] == "pass" and bool(r["decision"]["fallback"]) and r["applied"] is False')"

# ── v2 主代理预路由提醒（Task 11）：判据在 route_decide.nudge_decision，这里只测薄壳编码 ──
# $1=session_id(- 不传) $2=message $3=显式 model(- 不传) $4=显式 reasoning_effort(- 不传) $5=fork_turns 值(空/- 不传)
spn() {
  python3 - "$1" "$2" "$3" "$4" "${5:-}" <<'PY'
import json, sys
sid, msg, model, effort, fork = sys.argv[1:6]
ti = {"message": msg, "task_name": "t1", "agent_type": "worker"}
if model != "-":
    ti["model"] = model
if effort != "-":
    ti["reasoning_effort"] = effort
if fork and fork != "-":
    ti["fork_turns"] = fork
payload = {"turn_id": "t", "cwd": "/x", "hook_event_name": "PreToolUse",
           "model": "gpt-5.6-terra", "permission_mode": "default", "transcript_path": None,
           "tool_name": "spawn_agent", "tool_use_id": "c1", "tool_input": ti}
if sid != "-":
    payload["session_id"] = sid
print(json.dumps(payload, ensure_ascii=False))
PY
}
# nudge 专用目录：dispatch_nudge=true；merged 变体额外开 pre_dispatch_apply=true，测 deny 之后的合框。
V2_NUDGE_CONFIG="${TMP}/routing.catalog.v2.nudge.json"
python3 - "${ROOT}/config/routing.catalog.v2.json" "${V2_NUDGE_CONFIG}" <<'PY'
import json, sys
cfg = json.load(open(sys.argv[1], encoding="utf-8"))
cfg.setdefault("host_capabilities", {}).setdefault("codex-cli", {})["dispatch_nudge"] = True
with open(sys.argv[2], "w", encoding="utf-8") as fh:
    json.dump(cfg, fh, ensure_ascii=False)
PY
V2_NUDGE_MERGED_CONFIG="${TMP}/routing.catalog.v2.nudge.merged.json"
python3 - "${ROOT}/config/routing.catalog.v2.json" "${V2_NUDGE_MERGED_CONFIG}" <<'PY'
import json, sys
cfg = json.load(open(sys.argv[1], encoding="utf-8"))
hc = cfg.setdefault("host_capabilities", {}).setdefault("codex-cli", {})
hc["dispatch_nudge"] = True
hc["pre_dispatch_apply"] = True
with open(sys.argv[2], "w", encoding="utf-8") as fh:
    json.dump(cfg, fh, ensure_ascii=False)
PY
NLOGD="${TMP}/nudge-log"
runnudgewith() {  # $1=profile $2=payload $3=config $4=logdir
  local profile="$1" payload="$2" config="$3" ld="$4"
  OUT="$(printf '%s' "${payload}" | env HOME="${FAKEHOME}" TIER_GUARD_LOG_DIR="${ld}" TIER_GUARD_MODE="${profile}" \
          TIER_GUARD_CONFIG="${config}" /bin/bash "${HOOK}")"
  RC=$?
}
runnudge()       { runnudgewith "$1" "$2" "${V2_NUDGE_CONFIG}"        "${NLOGD}"; }
runnudgemerged() { runnudgewith "$1" "$2" "${V2_NUDGE_MERGED_CONFIG}" "${NLOGD}"; }
runnudgeprod()   { runnudgewith "$1" "$2" "${ROOT}/config/routing.catalog.v2.json" "${NLOGD}"; }
lastnudgelog() {  # $1=python 表达式（变量 r = NLOGD 最后一条日志）
  python3 - "$1" "${NLOGD}/decisions.jsonl" <<'PY'
import json, sys
expr, path = sys.argv[1], sys.argv[2]
try:
    r = json.loads(open(path, encoding="utf-8").read().splitlines()[-1])
    print("yes" if eval(expr) else "no")
except Exception:
    print("no")
PY
}
nudgeq() {  # $1=python 表达式（变量 o=stdout JSON，rd=route_decide 模块，cfg=对应配置字典，
            #   remind_ok/deny_ok/all_models_ok=下面预置的断言辅助函数）$2=配置路径（默认 V2_NUDGE_CONFIG）
  local expr="$1" cfgpath="${2:-${V2_NUDGE_CONFIG}}"
  python3 - "${expr}" "${OUT}" "${ROOT}/hooks" "${cfgpath}" <<'PY'
import json, sys
sys.path.insert(0, sys.argv[3])
import route_decide as rd  # noqa: F401
try:
    o = json.loads(sys.argv[2])
    cfg = json.load(open(sys.argv[4], encoding="utf-8"))
    # remind/deny 文案 = 常量 + 候选目录摘要；两半分开验，别把测试写成跟产出一样的拼接。
    def remind_ok(text):
        return text.startswith(rd.NUDGE_REMIND_TEXT) and rd.catalog_summary(cfg, "codex-cli") in text
    def deny_ok(text):
        return text.startswith(rd.NUDGE_DENY_TEXT) and rd.catalog_summary(cfg, "codex-cli") in text
    def all_models_ok(text):
        own = {c["model"] for c in rd.catalog_candidates(cfg, "codex-cli")}
        other = {c["model"] for c in rd.catalog_candidates(cfg, "claude-code")}
        return all(m in text for m in own) and not any(m in text for m in other)
    print("yes" if eval(sys.argv[1]) else "no")
except Exception:
    print("no")
PY
}
NUDGE_TASK=$'只读审查配置，禁止修改任何文件。\n验收：报告所有键名。'

rm -rf "${NLOGD}"
runnudgeprod audit "$(spn s0 "${NUDGE_TASK}" - -)"
check "nudge：生产目录 dispatch_nudge=false，audit + 未 pin → stdout 空" "$(yn [ "${RC}" -eq 0 -a -z "${OUT}" ])"
check "nudge：生产目录 dispatch_nudge=false → 记 nudge=none" "$(lastnudgelog 'r["nudge"] == "none"')"

runnudge audit "$(spn s1 "${NUDGE_TASK}" - -)"
check "nudge：gate 开 + audit + 未 pin → stdout 只有 additionalContext（常量开头 + 候选摘要）" \
  "$(nudgeq 'o["hookSpecificOutput"]["hookEventName"] == "PreToolUse" and remind_ok(o["hookSpecificOutput"]["additionalContext"]) and "updatedInput" not in o["hookSpecificOutput"] and "permissionDecision" not in o["hookSpecificOutput"]')"
check "nudge：audit 提醒记 nudge=reminded，applied=false" \
  "$(lastnudgelog 'r["nudge"] == "reminded" and r["applied"] is False')"
check "nudge：提醒文案含 codex-cli 全部候选 model，不含 claude-code 候选 model" \
  "$(nudgeq 'all_models_ok(o["hookSpecificOutput"]["additionalContext"])')"

runnudge audit "$(spn s2 "${NUDGE_TASK}" gpt-5.6-terra -)"
check "nudge：gate 开 + audit：显式 model 是 pin → stdout 空" "$(yn [ -z "${OUT}" ])"
check "nudge：显式 model pin → 记 nudge=none" "$(lastnudgelog 'r["nudge"] == "none"')"
runnudge audit "$(spn s3 "${NUDGE_TASK}" - high)"
check "nudge：gate 开 + audit：显式 reasoning_effort 是 pin → stdout 空" "$(yn [ -z "${OUT}" ])"
check "nudge：显式 effort pin → 记 nudge=none" "$(lastnudgelog 'r["nudge"] == "none"')"
# 真实 Codex 0.154.0 的原生 spawn_agent 每次都带 fork_turns（"all" / "none"）；它只决定继承多少历史，
# 与是否 pin 无关（rust-v0.154.0 spawn.rs：model/effort 覆盖在区分 fork 模式之前无条件生效）。
runnudge audit "$(spn s4 "${NUDGE_TASK}" - - all)"
check "nudge：真实形状 fork_turns=all + 未 pin + audit → 仍提醒，不 deny" \
  "$(nudgeq 'remind_ok(o["hookSpecificOutput"]["additionalContext"]) and "permissionDecision" not in o["hookSpecificOutput"]')"
check "nudge：fork_turns=all 未 pin → 记 nudge=reminded" "$(lastnudgelog 'r["nudge"] == "reminded"')"
runnudge auto "$(spn FORK1 "${NUDGE_TASK}" - - all)"
check "nudge：真实形状 fork_turns=all + 未 pin + auto 新会话 → deny" \
  "$(nudgeq 'o["hookSpecificOutput"]["permissionDecision"] == "deny" and deny_ok(o["hookSpecificOutput"]["permissionDecisionReason"])')"

runnudge audit "$(spn s5 "${OPAQUE_TASK_TOKEN}" - -)"
check "nudge：不透明任务令牌 + 未 pin + audit → 仍提醒（additionalContext）" \
  "$(nudgeq 'remind_ok(o["hookSpecificOutput"]["additionalContext"])')"
check "nudge：不透明任务令牌 → 记 nudge=reminded" \
  "$(lastnudgelog 'r["nudge"] == "reminded" and r["task_visibility"] == "opaque_token"')"

runnudge auto "$(spn A "${NUDGE_TASK}" - -)"
check "nudge：gate 开 + auto + session A 第一次未 pin → deny（原因以 route_decide 的 deny 常量开头 + 候选摘要）" \
  "$(nudgeq 'o["hookSpecificOutput"]["hookEventName"] == "PreToolUse" and o["hookSpecificOutput"]["permissionDecision"] == "deny" and deny_ok(o["hookSpecificOutput"]["permissionDecisionReason"]) and "updatedInput" not in o["hookSpecificOutput"]')"
check "nudge：deny 记 nudge=denied，applied=false" "$(lastnudgelog 'r["nudge"] == "denied" and r["applied"] is False')"

runnudge auto "$(spn A "${NUDGE_TASK}" - -)"
check "nudge：同一 session A 第二次未 pin → 不再 deny，只提醒（宿主未验证 apply，不带 updatedInput）" \
  "$(nudgeq '"permissionDecision" not in o["hookSpecificOutput"] and "updatedInput" not in o["hookSpecificOutput"] and remind_ok(o["hookSpecificOutput"]["additionalContext"])')"
check "nudge：session A 第二次记 nudge=reminded" "$(lastnudgelog 'r["nudge"] == "reminded"')"

# ── guard（默认 profile，Task 14）：merged 目录 pre_dispatch_apply=true 也只拦一次 / 提醒，从不改写 ──
runnudgemerged guard "$(spn G1 "${NUDGE_TASK}" - - all)"
check "guard：merged 目录 + 新会话未 pin → deny，不带 updatedInput" \
  "$(nudgeq 'o["hookSpecificOutput"]["permissionDecision"] == "deny" and deny_ok(o["hookSpecificOutput"]["permissionDecisionReason"]) and "updatedInput" not in o["hookSpecificOutput"]' "${V2_NUDGE_MERGED_CONFIG}")"
check "guard：deny 记 profile=guard、nudge=denied、applied=false" \
  "$(lastnudgelog 'r["decision"]["profile"] == "guard" and r["nudge"] == "denied" and r["applied"] is False')"
runnudgemerged guard "$(spn G1 "${NUDGE_TASK}" - - all)"
check "guard：同会话第二次未 pin → 只提醒，从不 updatedInput / permissionDecision" \
  "$(nudgeq '"permissionDecision" not in o["hookSpecificOutput"] and "updatedInput" not in o["hookSpecificOutput"] and remind_ok(o["hookSpecificOutput"]["additionalContext"])' "${V2_NUDGE_MERGED_CONFIG}")"
check "guard：第二次记 nudge=reminded、applied=false" "$(lastnudgelog 'r["nudge"] == "reminded" and r["applied"] is False')"

runnudgemerged auto "$(spn E "${NUDGE_TASK}" - -)"
check "nudge：宿主已验证 pre_dispatch_apply 时，session E 第一次仍先 deny（deny 压过改写）" \
  "$(nudgeq 'o["hookSpecificOutput"]["permissionDecision"] == "deny" and "updatedInput" not in o["hookSpecificOutput"]')"
runnudgemerged auto "$(spn E "${NUDGE_TASK}" - -)"
check "nudge：session E 第二次未 pin → allow + updatedInput + additionalContext 同框（宿主已验证 apply）" \
  "$(nudgeq 'o["hookSpecificOutput"]["permissionDecision"] == "allow" and o["hookSpecificOutput"]["updatedInput"]["model"] == "gpt-6-luna" and o["hookSpecificOutput"]["updatedInput"]["reasoning_effort"] == "high" and remind_ok(o["hookSpecificOutput"]["additionalContext"])' "${V2_NUDGE_MERGED_CONFIG}")"
check "nudge：session E 第二次记 nudge=reminded 且 applied=true" "$(lastnudgelog 'r["nudge"] == "reminded" and r["applied"] is True')"

runnudge auto "$(spn B "${NUDGE_TASK}" - -)"
check "nudge：不同 session B 第一次未 pin → 仍然 deny（按 session 各算一次）" \
  "$(nudgeq 'o["hookSpecificOutput"]["permissionDecision"] == "deny"')"
check "nudge：session B 第一次记 nudge=denied" "$(lastnudgelog 'r["nudge"] == "denied"')"

runnudge auto "$(spn - "${NUDGE_TASK}" - -)"
check "nudge：auto 但 payload 没 session_id → 只 remind，不 deny" \
  "$(nudgeq '"permissionDecision" not in o["hookSpecificOutput"] and remind_ok(o["hookSpecificOutput"]["additionalContext"])')"
check "nudge：无 session_id → 记 nudge=reminded" "$(lastnudgelog 'r["nudge"] == "reminded"')"

# env=off 会被薄壳快速路径拦下，这里走状态文件，才真正测到 python 这一侧
NOFFD="${TMP}/nudge-off"; mkdir -p "${NOFFD}"; printf 'off\n' > "${NOFFD}/mode"
OUT="$(printf '%s' "$(spn C "${NUDGE_TASK}" - -)" | env -u TIER_GUARD_MODE HOME="${FAKEHOME}" \
        TIER_GUARD_LOG_DIR="${NOFFD}" TIER_GUARD_CONFIG="${V2_NUDGE_CONFIG}" /bin/bash "${HOOK}")"; RC=$?
check "nudge：状态文件 off → 退出 0、stdout 空" "$(yn [ "${RC}" -eq 0 -a -z "${OUT}" ])"
check "nudge：状态文件 off → 不留日志" "$(yn [ ! -e "${NOFFD}/decisions.jsonl" ])"
# Phase 9 D7：off 下路由走兜底（空任务）时决定里没有 profile，旧代码会把它记进日志
printf '%s' "$(spn C "" - -)" | env -u TIER_GUARD_MODE HOME="${FAKEHOME}" \
  TIER_GUARD_LOG_DIR="${NOFFD}" TIER_GUARD_CONFIG="${V2_NUDGE_CONFIG}" /bin/bash "${HOOK}" >/dev/null
check "状态文件 off + 路由兜底 → 仍不留日志" "$(yn [ ! -e "${NOFFD}/decisions.jsonl" ])"

# ── deny 标记：目录名 64-hex，不含原始 session id ──
check "nudge：deny 标记文件名都是 64 位十六进制，且不含原始 session id" \
  "$(python3 - "${NLOGD}/nudge-denied" <<'PY'
import os, re, sys
d = sys.argv[1]
names = os.listdir(d)
raw_ids = ["A", "B", "E"]
ok = bool(names) and all(re.fullmatch(r"[0-9a-f]{64}", n) for n in names) \
    and not any(rid in n for n in names for rid in raw_ids)
print("yes" if ok else "no")
PY
)"

# ── 标记写不进去（nudge-denied 被占成普通文件）→ 降级成 remind，不能真 deny，退出仍是 0 ──
NLOGD_FAIL="${TMP}/nudge-log-fail"; mkdir -p "${NLOGD_FAIL}"
: > "${NLOGD_FAIL}/nudge-denied"
runnudgewith auto "$(spn D "${NUDGE_TASK}" - -)" "${V2_NUDGE_CONFIG}" "${NLOGD_FAIL}"
check "nudge：标记目录被占用 → 退出 0" "$(yn [ "${RC}" -eq 0 ])"
check "nudge：标记写不进去 → 降级为 remind，不 deny，仍带候选摘要" \
  "$(nudgeq '"permissionDecision" not in o["hookSpecificOutput"] and remind_ok(o["hookSpecificOutput"]["additionalContext"])')"

# ── stdout 从不出现 ask，deny 原因从不为空 ──
BADNUDGE=0
for sid in nx1 nx2 nx3; do
  runnudge auto "$(spn "${sid}" "${NUDGE_TASK}" - -)"
  case "${OUT}" in *'"ask"'*) BADNUDGE=$((BADNUDGE+1)) ;; esac
  case "${OUT}" in *'"permissionDecisionReason":""'*) BADNUDGE=$((BADNUDGE+1)) ;; esac
done
check "nudge：stdout 从不出现 ask，deny 原因从不为空" "$(yn [ "${BADNUDGE}" -eq 0 ])"

# ── prompt 原文不出现在 remind / deny 的 stdout 或日志里 ──
SECRET_TOKEN="NUDGE_SECRET_TOKEN_9f3a1c"
out_lacks_token() { case "${OUT}" in *"${SECRET_TOKEN}"*) return 1 ;; esac; return 0; }
runnudge audit "$(spn se1 "只读检查一遍。${SECRET_TOKEN}" - -)"
check "nudge：remind 的 stdout 不含 prompt 原文" "$(yn out_lacks_token)"
check "nudge：remind 的日志不含 prompt 原文" "$(lastnudgelog '"'"${SECRET_TOKEN}"'" not in json.dumps(r, ensure_ascii=False)')"
runnudge auto "$(spn se2 "只读检查一遍。${SECRET_TOKEN}" - -)"
check "nudge：deny 的 stdout 不含 prompt 原文" "$(yn out_lacks_token)"
check "nudge：deny 的日志不含 prompt 原文" "$(lastnudgelog '"'"${SECRET_TOKEN}"'" not in json.dumps(r, ensure_ascii=False)')"

# ── 并发：同一轮并行派出的多个 spawn_agent 会并发跑 hook，都读到「没 deny 过」──
NRACED="${TMP}/nudge-race"
nudge_race() {
  env HOME="${FAKEHOME}" TIER_GUARD_LOG_DIR="${NRACED}" \
    python3 - "${ROOT}/hooks" "${V2_NUDGE_CONFIG}" "$(spn R "${NUDGE_TASK}" - -)" <<'PY'
import json, sys
sys.path.insert(0, sys.argv[1])
import codex_hook as cx
import route_decide as rd
import tier_state
cfg, sha = rd.load_config_with_fingerprint(sys.argv[2])
payload = json.loads(sys.argv[3])
tier_state.nudge_already_denied = lambda session_id: False
outs = [cx.on_spawn_v2(payload, cfg, "auto", {"origin": "environment", "sha256": sha})[1] for _ in range(3)]
hso = [(o or {}).get("hookSpecificOutput", {}) for o in outs]
denies = sum(1 for h in hso if h.get("permissionDecision") == "deny")
reminds = sum(1 for h in hso if h.get("additionalContext", "").startswith(rd.NUDGE_REMIND_TEXT) and "permissionDecision" not in h)
print("yes" if denies == 1 and reminds == 2 else "no")
PY
}
check "nudge：并发抢标记 → 同一会话 3 次只有 1 次 deny，其余 2 次只提醒" "$(nudge_race)"

# ── Task 18：上游档位字段进审计日志，且日志不漏 reason / 任务原文 / 不透明令牌 ──
# 可见文本用例沿用本套件的 sp（message 为明文）造；真实宿主多数时候给的是不透明令牌，所以另有一条令牌用例。
TG18LOG="${TMP}/tg18-log"; rm -rf "${TG18LOG}"
TG18_REASON="TG18-REASON-SENTINEL-7f3a"; TG18_TASK="TG18-TASK-SENTINEL-c91e"
run18() {  # $1=profile $2=payload → OUT / RC（日志写进 TG18LOG）
  OUT="$(printf '%s' "$2" | env HOME="${FAKEHOME}" TIER_GUARD_LOG_DIR="${TG18LOG}" TIER_GUARD_MODE="$1" \
        TIER_GUARD_CONFIG="${ROOT}/config/routing.catalog.v2.json" /bin/bash "${HOOK}")"
  RC=$?
}
rec18() {  # $1=下标（-3 / -2 / -1）$2=python 表达式（r = 该条日志）
  python3 - "$1" "$2" "${TG18LOG}/decisions.jsonl" <<'PY'
import json, sys
try:
    r = json.loads(open(sys.argv[3], encoding="utf-8").read().splitlines()[int(sys.argv[1])])
    print("yes" if eval(sys.argv[2]) else "no")
except Exception:
    print("no")
PY
}
logdir_free_of() { dir_free_of "${TG18LOG}" "$@"; }
dir_free_of() {  # $1=目录 其余=不许出现的字符串。整个目录的每个文件都读一遍；目录或日志为空也算失败（防空断言）
  python3 - "$@" <<'PY'
import os, sys
root, needles = sys.argv[1], sys.argv[2:]
seen = 0
for dirpath, _, names in os.walk(root):
    for name in names:
        with open(os.path.join(dirpath, name), encoding="utf-8", errors="replace") as fh:
            body = fh.read()
        seen += len(body)
        if any(n in body for n in needles):
            print("no"); sys.exit(0)
print("yes" if seen > 0 and os.path.exists(os.path.join(root, "decisions.jsonl")) else "no")
PY
}
run18 guard "$(sp "${TG18_TASK} 只读审查配置，禁止修改任何文件。"$'\n验收：报告所有键名。\n'"<!-- tier-guard: tier=L2 reason=${TG18_REASON} -->" - -)"
check "tier18：合法标记 → 记录里 tier_source=upstream，upstream_tier 已接受且 reason_present=true" \
  "$(rec18 -1 'r["task_visibility"] == "visible" and r["decision"]["tier_source"] == "upstream" and r["decision"]["upstream_tier"]["status"] == "accepted" and r["decision"]["upstream_tier"]["tier"] == "L2" and r["decision"]["upstream_tier"]["reason_present"] is True')"
check "tier18：合法标记 → 记录里只有 reason 的 sha256，且没有 tier_conflict 键" \
  "$(rec18 -1 'len(r["decision"]["upstream_tier"]["reason_sha256"]) == 64 and "tier_conflict" not in r["decision"]')"
run18 guard "$(sp "${TG18_TASK} 完成后 git push 到 origin。"$'\n验收：远端分支可见。\n'"<!-- tier-guard: tier=L1 reason=${TG18_REASON} -->" - -)"
check "tier18：伪造 tier=L1 的不可逆任务 → 记录 tier_conflict={upstream:L1,floor:L3}" \
  "$(rec18 -1 'r["decision"]["tier_conflict"] == {"upstream": "L1", "floor": "L3"}')"
check "tier18：伪造 tier=L1 的不可逆任务 → 记录 tier_source=floor，目标是 sol/xhigh" \
  "$(rec18 -1 'r["decision"]["tier_source"] == "floor" and r["decision"]["target"]["id"] == "codex-sol-xhigh"')"
run18 guard "$(sp "${OPAQUE_TASK_TOKEN}" - -)"
check "tier18：不透明令牌 → 不采纳任何 tier（upstream_tier=absent），tier_source=inferred，无冲突" \
  "$(rec18 -1 'r["task_visibility"] == "opaque_token" and r["decision"]["upstream_tier"] == {"status": "absent"} and r["decision"]["tier_source"] == "inferred" and "tier_conflict" not in r["decision"]')"
check "tier18：日志目录里找不到 reason 原文、任务原文和不透明令牌" \
  "$(logdir_free_of "${TG18_REASON}" "${TG18_TASK}" "${OPAQUE_TASK_TOKEN}")"

# ── Task 20：L2 第二次失败 → 收回 deny（可见文本路径；不透明令牌看不到标记，永远不会收回）──
# 生产目录的 codex-cli.dispatch_nudge 仍关闭；这里用闸门打开的派生目录，与上面的 nudge 用例同法。
TG20LOG="${TMP}/tg20-log"; rm -rf "${TG20LOG}"
TG20_REASON="TG20-REASON-SENTINEL-4b8d"; TG20_TASK="TG20-TASK-SENTINEL-e72a"
R20_TASK="${TG20_TASK} 只读审查配置，禁止修改任何文件。"$'\n验收：报告所有键名。\n'"<!-- tier-guard: tier=L2 failures=2 reason=${TG20_REASON} -->"
rec20() {  # $1=python 表达式（r = TG20LOG 里最后一条日志）
  python3 - "$1" "${TG20LOG}/decisions.jsonl" <<'PY'
import json, sys
try:
    r = json.loads(open(sys.argv[2], encoding="utf-8").read().splitlines()[-1])
    print("yes" if eval(sys.argv[1]) else "no")
except Exception:
    print("no")
PY
}
r20_deny_json='o["hookSpecificOutput"]["permissionDecision"] == "deny" and "第二次失败" in o["hookSpecificOutput"]["permissionDecisionReason"] and "2 次" in o["hookSpecificOutput"]["permissionDecisionReason"] and "重新界定" in o["hookSpecificOutput"]["permissionDecisionReason"] and "updatedInput" not in o["hookSpecificOutput"]'
reason_lacks_sentinels() { case "${OUT}" in *TG20-*) return 1 ;; esac; return 0; }
runnudgewith guard "$(spn R20S "${R20_TASK}" - -)" "${V2_NUDGE_CONFIG}" "${TG20LOG}"
check "tier20：gate 开 + guard + L2 失败 2 次（可见文本）→ deny，原因含第二次失败与失败计数，不带 updatedInput" "$(jsonq "${r20_deny_json}")"
check "tier20：收回 deny 的输出不含任务原文和 reason 原文" "$(yn reason_lacks_sentinels)"
check "tier20：收回 deny 记 task_visibility=visible、reclaim_output=deny、nudge=none" \
  "$(rec20 'r["task_visibility"] == "visible" and r["reclaim_output"] == "deny" and r["nudge"] == "none"')"
check "tier20：收回 deny 没有创建 nudge 标记（既不检查也不消耗）" "$(yn [ ! -e "${TG20LOG}/nudge-denied" ])"
runnudgewith guard "$(spn R20S "${NUDGE_TASK}" - -)" "${V2_NUDGE_CONFIG}" "${TG20LOG}"
check "tier20：收回之后同会话的普通未 pin 派活仍拿到第一次 nudge deny" \
  "$(jsonq 'o["hookSpecificOutput"]["permissionDecision"] == "deny" and "第二次失败" not in o["hookSpecificOutput"]["permissionDecisionReason"]')"
runnudgewith auto "$(spn R20M "${R20_TASK}" - -)" "${V2_NUDGE_MERGED_CONFIG}" "${TG20LOG}"
check "tier20：auto + pre_dispatch_apply=true → 仍是 deny，不带 updatedInput" "$(jsonq "${r20_deny_json}")"
runnudgewith audit "$(spn R20U "${R20_TASK}" - -)" "${V2_NUDGE_CONFIG}" "${TG20LOG}"
check "tier20：audit → 只提醒（additionalContext），不 deny" \
  "$(jsonq '"第二次失败" in o["hookSpecificOutput"]["additionalContext"] and "permissionDecision" not in o["hookSpecificOutput"]')"
runnudgewith guard "$(spn R20G "${R20_TASK}" - -)" "${ROOT}/config/routing.catalog.v2.json" "${TG20LOG}"
check "tier20：生产目录 codex-cli.dispatch_nudge=false → 不收回、stdout 空" "$(yn [ "${RC}" -eq 0 -a -z "${OUT}" ])"
check "tier20：闸门关闭只记录：决策里有 reclaim，但没有 reclaim_output" "$(rec20 '"reclaim" in r["decision"] and "reclaim_output" not in r')"
runnudgewith guard "$(spn R20P "${R20_TASK}" gpt-6.1-sol medium)" "${V2_NUDGE_CONFIG}" "${TG20LOG}"
check "tier20：pin 的派活 → 不收回、stdout 空" "$(yn [ "${RC}" -eq 0 -a -z "${OUT}" ])"
runnudgewith guard "$(spn - "${R20_TASK}" - -)" "${V2_NUDGE_CONFIG}" "${TG20LOG}"
check "tier20：payload 没有 session_id → 收回 deny 照样成立（不依赖 session_id）" "$(jsonq "${r20_deny_json}")"
runnudgewith guard "$(spn R20Q "${OPAQUE_TASK_TOKEN}" - -)" "${V2_NUDGE_CONFIG}" "${TG20LOG}"
check "tier20：不透明令牌看不到标记 → 永远没有 reclaim，也没有收回输出" \
  "$(rec20 'r["task_visibility"] == "opaque_token" and "reclaim" not in r["decision"] and "reclaim_output" not in r')"
check "tier20：收回全过程的日志目录里找不到任务原文和 reason 原文" "$(dir_free_of "${TG20LOG}" "${TG20_REASON}" "${TG20_TASK}")"

MS="$(python3 - "${HOOK}" "$(sp "${IRR}" gpt-5.6-terra high)" "${FAKEHOME}" "${LOGD}" <<'PY'
import os, subprocess, sys, time
hook, payload, home, logd = sys.argv[1:5]
env = dict(os.environ, HOME=home, TIER_GUARD_LOG_DIR=logd, TIER_GUARD_MODE="auto",
           TIER_GUARD_CONFIG=os.path.join(os.path.dirname(os.path.dirname(hook)), "config", "routing.default.json"))
ts = []
for _ in range(15):
    t = time.perf_counter()
    subprocess.run(["/bin/bash", hook], input=payload, capture_output=True, text=True, env=env)
    ts.append((time.perf_counter() - t) * 1000)
print(int(sorted(ts)[len(ts) // 2]))
PY
)"
check "性能：单次执行中位 ${MS}ms < 100ms" "$(yn [ "${MS}" -lt 100 ])"

echo ""
echo "  总计 ${PASS} 通过 / ${FAIL} 失败"
[ "${PASS}" -gt 0 ] && [ "${FAIL}" -eq 0 ]
