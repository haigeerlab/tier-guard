#!/bin/bash
# ─────────────────────────────────────────────────────────────
# /tier-mode（tier_state.py）与 /tier-report（tier_report.py）的回归断言。
#
# 报表的输入不手写：先让真的 hook（tier-guard.sh）判一轮，再汇总它写下的日志 ——
# 手写的日志夹具只能证明报表认得「我以为 hook 会写的格式」。
# ─────────────────────────────────────────────────────────────
set -uo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TMP="$(mktemp -d)"
trap 'rm -rf "${TMP}"' EXIT
PASS=0; FAIL=0
check() { if [ "$2" = yes ]; then printf '  ✅ %s\n' "$1"; PASS=$((PASS+1)); else printf '  ❌ %s\n' "$1"; FAIL=$((FAIL+1)); fi; }
# yn 只包一条命令。复合条件写成具名函数再交给 yn —— `$(yn A && B)` 里 yn 先打印了 yes，
# B 失败也改不了结果，是一条永远为真的空断言。
yn() { if "$@"; then echo yes; else echo no; fi; }
has() { case "$1" in *"$2"*) return 0 ;; *) return 1 ;; esac; }   # 纯 bash 子串判断，不走管道

DATA="${TMP}/data"; FAKEHOME="${TMP}/home"; mkdir -p "${FAKEHOME}"
state()  { env -u TIER_GUARD_MODE HOME="${FAKEHOME}" python3 "${ROOT}/hooks/tier_state.py" "$@" --data "${DATA}" --config "${ROOT}/config/routing.default.json"; }
statev2() { env -u TIER_GUARD_MODE HOME="${FAKEHOME}" python3 "${ROOT}/hooks/tier_state.py" "$@" --data "${V2STATE}" --config "${ROOT}/config/routing.catalog.v2.json"; }
statecurrent() { env -u TIER_GUARD_MODE HOME="${FAKEHOME}" python3 "${ROOT}/hooks/tier_state.py" "$@" --data "${V2STATE}"; }
report() { env -u TIER_GUARD_MODE HOME="${FAKEHOME}" python3 "${ROOT}/hooks/tier_report.py" --data "${DATA}"; }
hook() {  # $1=事件 $2=payload [$3=TIER_GUARD_MODE，空 = 不设]
  if [ -n "${3:-}" ]; then
    printf '%s' "$2" | env HOME="${FAKEHOME}" TIER_GUARD_LOG_DIR="${DATA}" TIER_GUARD_MODE="$3" TIER_GUARD_CONFIG="${ROOT}/config/routing.default.json" /bin/bash "${ROOT}/hooks/tier-guard.sh" "$1"
  else
    printf '%s' "$2" | env -u TIER_GUARD_MODE HOME="${FAKEHOME}" TIER_GUARD_LOG_DIR="${DATA}" TIER_GUARD_CONFIG="${ROOT}/config/routing.default.json" /bin/bash "${ROOT}/hooks/tier-guard.sh" "$1"
  fi
}
hookv2() {  # $1=数据目录 $2=profile $3=事件 $4=payload
  printf '%s' "$4" | env HOME="${FAKEHOME}" TIER_GUARD_LOG_DIR="$1" TIER_GUARD_MODE="$2" \
    TIER_GUARD_CONFIG="${ROOT}/config/routing.catalog.v2.json" /bin/bash "${ROOT}/hooks/tier-guard.sh" "$3"
}
hookv2state() {  # $1=数据目录 $2=事件 $3=payload
  printf '%s' "$3" | env -u TIER_GUARD_MODE HOME="${FAKEHOME}" TIER_GUARD_LOG_DIR="$1" \
    TIER_GUARD_CONFIG="${ROOT}/config/routing.catalog.v2.json" /bin/bash "${ROOT}/hooks/tier-guard.sh" "$2"
}
hookcurrent() {  # $1=数据目录 $2=事件 $3=payload
  printf '%s' "$3" | env -u TIER_GUARD_MODE HOME="${FAKEHOME}" TIER_GUARD_LOG_DIR="$1" \
    /bin/bash "${ROOT}/hooks/tier-guard.sh" "$2"
}
v2_state_profile() {  # $1=期望的 profile
  python3 - "${V2STATE}/decisions.jsonl" "$1" <<'PY'
import json, sys
try:
    record = json.loads(open(sys.argv[1], encoding="utf-8").read().splitlines()[-1])
    raise SystemExit(0 if record["decision"]["profile"] == sys.argv[2] else 1)
except Exception:
    raise SystemExit(1)
PY
}
v2_state_audit() { v2_state_profile audit; }
v2_state_guard() { v2_state_profile guard; }
mk() {  # $1=prompt $2=model(- 不传)
  python3 -c 'import json,sys
ti={"description":"t","prompt":sys.argv[1],"subagent_type":"general-purpose"}
if sys.argv[2]!="-": ti["model"]=sys.argv[2]
print(json.dumps({"session_id":"s","tool_use_id":"u","tool_name":"Agent","tool_input":ti},ensure_ascii=False))' "$1" "$2"
}
bashp() { python3 -c 'import json,sys; print(json.dumps({"tool_name":"Bash","tool_input":{"command":sys.argv[1]}},ensure_ascii=False))' "$1"; }
# PAD 要让 prompt 真的越过收益门槛（150 字），否则「放行」那条会被判成 local —— 第一版就栽在这
PAD="背景：这是一段中性的背景说明，只用来让 prompt 越过收益门槛，不含任何判据词。背景：这是一段中性的背景说明，只用来让 prompt 越过收益门槛。背景：再补一句中性的说明文字，凑够长度。背景：再补一句中性的说明文字。"
PAD="${PAD}${PAD}"
AC=$'\n验收：pytest 全绿\n'

echo "═══ /tier-mode ═══"
OUT="$(state show)"
check "legacy show：显式旧配置默认 dry-run" "$(yn has "${OUT}" "当前 mode：dry-run（来源：当前路由配置默认值）")"
state set off >/dev/null; RC=$?
check "set off → 退出 0，写入状态文件" "$(yn [ "${RC}" -eq 0 -a "$(cat "${DATA}/mode" 2>/dev/null)" = off ])"
check "show：状态文件生效" "$(yn has "$(state show)" "当前 mode：off")"
OUT="$(hook agent "$(mk "改完后 git push。${AC}${PAD}" sonnet)")"
check "状态文件 off → hook stdout 空、不留日志" "$(yn [ -z "${OUT}" -a ! -e "${DATA}/decisions.jsonl" ])"
OUT="$(hook agent "$(mk "改完后 git push。${AC}${PAD}" sonnet)" auto)"
check "环境变量优先于状态文件（env=auto 压过 off）" "$(yn has "${OUT}" '"updatedInput"')"
rm -f "${DATA}/decisions.jsonl"
OUT="$(state set auto)"; RC=$?
c_auto_rejected() { [ "${RC}" -ne 0 ] && has "${OUT}" "数据门槛没过"; }
check "set auto → 拒绝（退出非零、说明数据门槛没过）" "$(yn c_auto_rejected)"
check "set auto → 状态文件没被改" "$(yn [ "$(cat "${DATA}/mode")" = off ])"
state set deny >/dev/null; RC=$?
check "set 未知值 → 拒绝" "$(yn [ "${RC}" -ne 0 ])"
state set dry-run >/dev/null

echo ""
echo "═══ /tier-report ═══"
rm -rf "${TMP}/empty"
OUT="$(env -u TIER_GUARD_MODE HOME="${FAKEHOME}" python3 "${ROOT}/hooks/tier_report.py" --data "${TMP}/empty")"; RC=$?
c_empty() { [ "${RC}" -eq 0 ] && has "${OUT}" "还没有任何记录"; }
check "没有日志 → 退出 0，明说还没有记录" "$(yn c_empty)"

# 让真 hook 判一轮（状态文件是 dry-run）
hook agent "$(mk "改完后 git push 到 origin。${AC}${PAD}" sonnet)"        >/dev/null  # 欠配
hook agent "$(mk "检查有没有人写了 git push。${AC}${PAD}" sonnet)"        >/dev/null  # 欠配 + 疑似误报
hook agent "$(mk "改完后 git push 到 origin。${AC}${PAD}" -)"             >/dev/null  # 起点未知被钉 T2
hook agent "$(mk "按 spec 实现缓存层。${AC}${PAD}" sonnet)"               >/dev/null  # 放行
hook agent "$(mk "改个常量。${AC}" sonnet)"                               >/dev/null  # 建议 local
hook bash  "$(bashp "bash /x/codex-exec.sh --model gpt-5.6-terra --effort high \"按 spec 实现缓存层。${AC}${PAD}\"")" >/dev/null
hook bash  "$(bashp "bash /x/codex-exec.sh --model gpt-5.6-terra --effort high \"改完后 git push。${AC}${PAD}\"")"   >/dev/null
hook bash  "$(bashp 'ls -la')" >/dev/null                                                                          # 不记
REP="$(report)"
check "report：判定总数 5" "$(yn has "${REP}" "| 判定总数 | 5 |")"
check "report：欠配 2（只算起点已知的）" "$(yn has "${REP}" "被判 raise） | 2 |")"
check "report：其中疑似误报 1" "$(yn has "${REP}" "其中疑似误报（只是提到动作词） | 1 |")"
check "report：dry-run 下 hook 改写输出 0" "$(yn has "${REP}" "其中 auto 下 hook 已输出改写 | 0 |")"
check "report：起点未知被钉 T2 单列 1" "$(yn has "${REP}" "不计入欠配） | 1 |")"
check "report：建议 local 1" "$(yn has "${REP}" "| 建议 local / defer | 1 / 0 |")"
check "report：Codex 一致 1 / 不一致 1（普通 Bash 不计）" "$(yn has "${REP}" "共 2 次：一致 1 / 不一致 1")"
check "report：Codex 表格给出建议值（不一致那条建议 xhigh）" "$(yn has "${REP}" "| gpt-5.6-terra / high | gpt-5.6-terra / xhigh | ❌ |")"
check "report：当前 mode 来自状态文件" "$(yn has "${REP}" "当前 mode：**dry-run**")"
c_sections() { has "${REP}" "### 建议档 vs 实际执行档" && has "${REP}" "### 打回率" && has "${REP}" "### 误报率" && has "${REP}" "### 切 auto 的门槛"; }
check "report：建议 vs 实际 / 打回率 / 误报率 / auto 门槛 四节都在" "$(yn c_sections)"
c_v1_only_link() { has "${REP}" "已关联 0 / 5 次" && ! has "${REP}" "v1 旧记录：" && ! has "${REP}" "v2：已观测实际执行"; }
check "report：全是无 nudge 字段的旧记录 → 提醒段落明说没有记录" \
  "$(yn has "${REP}" "没有提醒记录（宿主 dispatch_nudge 未开启或尚未派活）。")"
printf 'not json\n' >> "${DATA}/decisions.jsonl"
OUT="$(report)"; RC=$?
c_broken() { [ "${RC}" -eq 0 ] && has "${OUT}" "有 1 行不是合法 JSON"; }
check "report：坏行跳过并提示，仍退出 0" "$(yn c_broken)"

echo ""
echo "═══ v2 路由审计 ═══"
V2DATA="${TMP}/v2-data"
V2STATE="${TMP}/v2-state"
V2SIMPLE=$'只读审查配置，禁止修改任何文件。\n验收：报告所有键名。'
# 2026-10-06 用户确认：出厂默认 off（派活大多不省钱；不派活的用户不该被宿主自己的子代理触发拦截）
check "运行时默认：mode 命令读取 v2 off" "$(yn has "$(statecurrent show)" "当前 mode：off")"
OUT="$(hookcurrent "${V2STATE}" agent "$(mk "${V2SIMPLE}" -)")"
check "运行时默认：off 下 Claude hook 不输出、不留记录" "$(yn [ -z "${OUT}" -a ! -e "${V2STATE}/decisions.jsonl" ])"
check "v2 mode：默认是 off" "$(yn has "$(statev2 show)" "当前 mode：off")"
statev2 set audit >/dev/null; RC=$?
check "v2 mode：set audit 写入状态文件" "$(yn [ "${RC}" -eq 0 -a "$(cat "${V2STATE}/mode")" = audit ])"
statev2 set dry-run >/dev/null; RC=$?
check "v2 mode：拒绝遗留 dry-run 名称" "$(yn [ "${RC}" -ne 0 ])"
OUT="$(statev2 set auto)"; RC=$?
check "v2 mode：无真实宿主质量证据时拒绝持久 auto" "$(yn [ "${RC}" -ne 0 -a "$(cat "${V2STATE}/mode")" = audit ])"
hookv2state "${V2STATE}" agent "$(mk "${V2SIMPLE}" -)" >/dev/null
check "v2 mode：hook 从状态文件读 audit" \
  "$(yn v2_state_audit)"
statev2 set guard >/dev/null; RC=$?
check "v2 mode：set guard 写入状态文件（无门槛）" "$(yn [ "${RC}" -eq 0 -a "$(cat "${V2STATE}/mode")" = guard ])"
hookv2state "${V2STATE}" agent "$(mk "${V2SIMPLE}" -)" >/dev/null
check "v2 mode：hook 从状态文件读 guard" \
  "$(yn v2_state_guard)"
hookv2 "${V2DATA}" audit agent "$(mk "${V2SIMPLE}" -)" >/dev/null
hookv2 "${V2DATA}" auto agent "$(mk "${V2SIMPLE}" -)" >/dev/null
# 显式 model 是 pin：真实 hook 要记录建议，但绝不能偷偷覆盖用户指定值。
hookv2 "${V2DATA}" audit agent "$(mk "${V2SIMPLE}" sonnet)" >/dev/null
V2REP="$(env -u TIER_GUARD_MODE HOME="${FAKEHOME}" python3 "${ROOT}/hooks/tier_report.py" --data "${V2DATA}")"
check "v2 report：列出请求、选择、hook 改写输出与实际观测" \
  "$(yn has "${V2REP}" "### v2 路由审计")"
v2_host_capability() { has "${V2REP}" "宿主可改写" && has "${V2REP}" "是"; }
check "v2 report：列出宿主是否获准派发前改写" "$(yn v2_host_capability)"
v2_profiles() { has "${V2REP}" "audit：2 / guard：0 / auto：1" && has "${V2REP}" "haiku"; }
check "v2 report：audit / auto 分开且能看到 selected haiku" \
  "$(yn v2_profiles)"
# guard 记录单独计数（Task 14）：用生产目录让真 hook 以 guard 写一条
V2GUARD="${TMP}/v2-guard"
hookv2 "${V2GUARD}" guard agent "$(mk "${V2SIMPLE}" -)" >/dev/null
v2_guard_count() { has "$(env -u TIER_GUARD_MODE HOME="${FAKEHOME}" python3 "${ROOT}/hooks/tier_report.py" --data "${V2GUARD}")" "audit：0 / guard：1 / auto：0"; }
check "v2 report：guard 记录单独计数" "$(yn v2_guard_count)"
v2_pin() { has "${V2REP}" "pin 1" && has "${V2REP}" "| lower |"; }
check "v2 report：audit 的 pin 保留方向建议、仍不写成实际执行" \
  "$(yn v2_pin)"
# 整份报告都查，只去掉「主代理预路由提醒」一节固定的免责声明（Task 12）——它字面含 token 是预期的。
v2_no_token() { has "${V2REP}" "未观测" && ! has "${V2REP//"报告不推算 token"/}" "token"; }
check "v2 report：未观测到实际执行时明确写未知，不推算 token" \
  "$(yn v2_no_token)"

# 实际执行只来自真 hook 在 SubagentStop 读到的子代理 transcript，严格按 tool_use_id 关联（不靠时间）。
V2JOIN="${TMP}/v2-join"
agentv2() {  # $1=tool_use_id
  python3 -c 'import json,sys
print(json.dumps({"session_id":"s","tool_use_id":sys.argv[1],"tool_name":"Agent","tool_input":{"description":"t","prompt":sys.argv[2],"subagent_type":"general-purpose"}},ensure_ascii=False))' "$1" "${V2SIMPLE}"
}
hookv2 "${V2JOIN}" audit agent "$(agentv2 u-seen)" >/dev/null
hookv2 "${V2JOIN}" audit agent "$(agentv2 u-unseen)" >/dev/null
SUBTR="${TMP}/v2-sub/agent-seen.jsonl"; mkdir -p "${TMP}/v2-sub"
python3 - "${SUBTR}" <<'PY'
import json, sys
f = sys.argv[1]
with open(f, "w", encoding="utf-8") as fh:
    fh.write(json.dumps({"type": "user", "message": {"role": "user", "content": "x"}}) + "\n")
    fh.write(json.dumps({"type": "assistant", "message": {"role": "assistant", "model": "claude-haiku-4-5", "content": []}}) + "\n")
json.dump({"toolUseId": "u-seen"}, open(f[:-len(".jsonl")] + ".meta.json", "w", encoding="utf-8"))
PY
hookv2 "${V2JOIN}" audit subagent-stop "$(python3 -c 'import json,sys; print(json.dumps({"session_id":"s","agent_transcript_path":sys.argv[1]}))' "${SUBTR}")" >/dev/null
JOINREP="$(env -u TIER_GUARD_MODE HOME="${FAKEHOME}" python3 "${ROOT}/hooks/tier_report.py" --data "${V2JOIN}")"
v2_join_seen() { has "${JOINREP}" "| claude-haiku-4-5 |"; }
check "v2 report：按 tool_use_id 关联 SubagentStop，列出实际执行模型" "$(yn v2_join_seen)"
v2_join_unseen() { has "${JOINREP}" "| 未观测 |" && has "${JOINREP}" "共 2 次"; }
check "v2 report：未关联到的那条仍写未观测，stop 记录不计入路由次数" "$(yn v2_join_unseen)"
# 宿主对某些子代理不写 transcript。报告必须把它单列，否则读者会把「宿主没给」误读成「tier-guard 没观测到」。
# 新记录带 transcript_status，更早的记录把同一件事记成 FileNotFoundError 兜底 —— 两种口径都要算。
# Phase 9 R1/R2：不带 agent_type、关联不到派活的 stop 是宿主内部子代理（本机 2900 / 2900 条如此），
# 不是派活：单独一行，不进覆盖率分母，它们的 FileNotFoundError 也不算守卫兜底。
V2NOTR="${TMP}/v2-notranscript"; mkdir -p "${V2NOTR}"
python3 - "${V2NOTR}/decisions.jsonl" <<'PY2'
import json, sys
rows = [{"ts": "2026-10-05T00:00:00+00:00", "event": "subagent-stop", "routing_version": 2,
         "session_id": "s", "agent_type": "executor", "tool_use_id": "u-notr",
         "transcript_status": "missing", "actual_execution": None},
        {"ts": "2026-10-05T00:00:01+00:00", "event": "subagent-stop", "agent_type": "executor", "tool_use_id": "u-notr2",
         "fallback": "claude_hook: FileNotFoundError: [Errno 2] No such file or directory: '/x/a.jsonl'"},
        {"ts": "2026-10-05T00:00:02+00:00", "event": "subagent-stop", "routing_version": 2,
         "session_id": "s", "agent_type": "executor", "tool_use_id": "u-notr3", "transcript_status": "ok",
         "actual_execution": {"model": "claude-haiku-4-5", "reasoning_effort": None}},
        {"ts": "2026-10-05T00:00:03+00:00", "event": "subagent-stop", "routing_version": 2,
         "session_id": "s", "transcript_status": "missing", "actual_execution": None},
        {"ts": "2026-10-05T00:00:04+00:00", "event": "subagent-stop",
         "fallback": "claude_hook: FileNotFoundError: [Errno 2] No such file or directory: '/x/b.jsonl'"}]
with open(sys.argv[1], "w", encoding="utf-8") as fh:
    for r in rows:
        fh.write(json.dumps(r, ensure_ascii=False) + "\n")
PY2
for u in u-notr u-notr2 u-notr3; do hookv2 "${V2NOTR}" audit agent "$(agentv2 "${u}")" >/dev/null; done
NOTRREP="$(env -u TIER_GUARD_MODE HOME="${FAKEHOME}" python3 "${ROOT}/hooks/tier_report.py" --data "${V2NOTR}")"
v2_notr() { has "${NOTRREP}" "SubagentStop（派活）3 次，其中宿主未写 transcript 2 次"; }
check "v2 report：派活的 stop 里宿主未写 transcript 单列，新旧两种口径都算" "$(yn v2_notr)"
v2_notr_not_fault() { has "${NOTRREP}" "与守卫异常无关"; }
check "v2 report：明说它与守卫异常无关，不占 fallback 的诊断位" "$(yn v2_notr_not_fault)"
v2_internal() { has "${NOTRREP}" "宿主内部子代理的 SubagentStop 2 次"; }
check "v2 report：宿主内部子代理单独一行，不进覆盖率分母" "$(yn v2_internal)"
v2_internal_no_fb() { has "${NOTRREP}" "| 守卫放行兜底（fallback） | 1 |"; }
check "v2 report：宿主内部子代理的 FileNotFoundError 不算守卫兜底（只剩派活那 1 条）" "$(yn v2_internal_no_fb)"
# token 用量：只报 token、不报成本。价格随模型和账号变动，写进插件就是埋一个会过期的事实。
V2USE="${TMP}/v2-usage"; mkdir -p "${V2USE}"
python3 - "${V2USE}/decisions.jsonl" <<'PY2'
import json, sys
rows = [{"ts": "2026-10-05T00:00:00+00:00", "event": "subagent-stop", "routing_version": 2,
         "session_id": "s", "transcript_status": "ok",
         "actual_execution": {"model": "claude-haiku-4-5", "reasoning_effort": None}, "usage_basis": "message-id-dedup",
         "usage": {"input_tokens": 100, "cache_creation_input_tokens": 200,
                   "cache_read_input_tokens": 3000, "output_tokens": 40}},
        {"ts": "2026-10-05T00:00:01+00:00", "event": "subagent-stop", "routing_version": 2,
         "session_id": "s", "transcript_status": "ok",
         "actual_execution": {"model": "claude-haiku-4-5", "reasoning_effort": None}, "usage_basis": "message-id-dedup",
         "usage": {"input_tokens": 200, "cache_creation_input_tokens": 400,
                   "cache_read_input_tokens": 1000, "output_tokens": 60}},
        {"ts": "2026-10-05T00:00:02+00:00", "event": "subagent-stop", "routing_version": 2,
         "session_id": "s", "transcript_status": "missing", "actual_execution": None, "usage": None}]
with open(sys.argv[1], "w", encoding="utf-8") as fh:
    for r in rows:
        fh.write(json.dumps(r, ensure_ascii=False) + "\n")
PY2
hookv2 "${V2USE}" audit agent "$(agentv2 u-use)" >/dev/null
USEREP="$(env -u TIER_GUARD_MODE HOME="${FAKEHOME}" python3 "${ROOT}/hooks/tier_report.py" --data "${V2USE}")"
v2_use_avg() { has "${USEREP}" "| claude-haiku-4-5 | 2 | 150 | 300 | 2,000 | 50 |"; }
check "v2 report：按实际执行模型列出平均 token（只算有用量的那些）" "$(yn v2_use_avg)"
v2_use_nocost() { has "${USEREP}" "不换算成本"; }
check "v2 report：明说不换算成本（价格不写进插件）" "$(yn v2_use_nocost)"

# 真实宿主实测：SubagentStop 触发时，子代理唯一的 assistant 行可能还没落盘。报告须回读 transcript 补齐。
V2LATE="${TMP}/v2-late"
hookv2 "${V2LATE}" audit agent "$(agentv2 u-late)" >/dev/null
LATETR="${TMP}/v2-sub/agent-late.jsonl"
python3 - "${LATETR}" <<'PY'
import json, sys
f = sys.argv[1]
with open(f, "w", encoding="utf-8") as fh:
    fh.write(json.dumps({"type": "user", "message": {"role": "user", "content": "x"}}) + "\n")
json.dump({"toolUseId": "u-late"}, open(f[:-len(".jsonl")] + ".meta.json", "w", encoding="utf-8"))
PY
hookv2 "${V2LATE}" audit subagent-stop "$(python3 -c 'import json,sys; print(json.dumps({"session_id":"s","agent_transcript_path":sys.argv[1]}))' "${LATETR}")" >/dev/null
python3 - "${LATETR}" <<'PY'
import json, sys
with open(sys.argv[1], "a", encoding="utf-8") as fh:
    fh.write(json.dumps({"type": "assistant", "message": {"role": "assistant", "model": "claude-sonnet-5", "content": [],
        "usage": {"input_tokens": 7, "cache_creation_input_tokens": 70,
                  "cache_read_input_tokens": 700, "output_tokens": 3}}}) + "\n")
PY
LATEREP="$(env -u TIER_GUARD_MODE HOME="${FAKEHOME}" python3 "${ROOT}/hooks/tier_report.py" --data "${V2LATE}")"
v2_late() { has "${LATEREP}" "| claude-sonnet-5 |" && ! has "${LATEREP}" "| 未观测 |"; }
check "v2 report：SubagentStop 时 transcript 未落盘，报告回读后仍列出实际模型" "$(yn v2_late)"
# 回读只捞模型不捞用量的话，落盘慢的派活会在用量表里整条缺席 —— 而那往往正是跑得久的那些。
v2_late_usage() { has "${LATEREP}" "| claude-sonnet-5 | 1 | 7 | 70 | 700 | 3 |"; }
check "v2 report：回读未落盘 transcript 时连 token 用量一并补回" "$(yn v2_late_usage)"

# 恢复运行的子代理会追加同一份 transcript 并再触发 SubagentStop，每条记录存的都是整份文件的累计用量。
# 用量表按 transcript 路径分组：文件在就回读；文件没了取最晚的带 usage_basis 记录；只剩修复前的旧记录则不可信。
V2GRP="${TMP}/v2-grp"; mkdir -p "${V2GRP}/sub"
python3 - "${V2GRP}" <<'PY'
import json, os, sys
d = sys.argv[1]
t1 = os.path.join(d, "sub", "agent-resumed.jsonl")
with open(t1, "w", encoding="utf-8") as fh:
    for mid, u in (("m1", (4, 8, 12, 1)), ("m2", (6, 12, 18, 3))):
        fh.write(json.dumps({"type": "assistant", "message": {"role": "assistant", "id": mid, "model": "claude-sonnet-5",
            "usage": dict(zip(("input_tokens", "cache_creation_input_tokens", "cache_read_input_tokens", "output_tokens"), u))}}) + "\n")
def use(i, w, r, o):
    return {"input_tokens": i, "cache_creation_input_tokens": w, "cache_read_input_tokens": r, "output_tokens": o}
def stop(ts, path, execution, usage, basis=True):
    r = {"ts": ts, "event": "subagent-stop", "routing_version": 2, "session_id": "s", "transcript_status": "ok",
         "agent_transcript_path": path, "actual_execution": {"model": execution, "reasoning_effort": None}, "usage": usage}
    if basis:
        r["usage_basis"] = "message-id-dedup"
    return r
gone1, gone2 = os.path.join(d, "sub", "gone-marked.jsonl"), os.path.join(d, "sub", "gone-old.jsonl")
rows = [stop("2026-10-05T00:00:01+00:00", t1, "claude-stale", use(999, 999, 999, 999)),
        stop("2026-10-05T00:00:02+00:00", t1, "claude-stale", use(888, 888, 888, 888)),
        # 较晚的 ts 排在文件前面：取「最晚」必须按 ts，而不是按行序
        stop("2026-10-05T00:00:09+00:00", gone1, "claude-haiku-4-5", use(2000, 400, 3000, 50)),
        stop("2026-10-05T00:00:03+00:00", gone1, "claude-haiku-4-5", use(1000, 100, 100, 5)),
        stop("2026-10-05T00:00:04+00:00", gone2, "claude-opus-old", use(777, 777, 777, 777), basis=False)]
with open(os.path.join(d, "decisions.jsonl"), "w", encoding="utf-8") as fh:
    for r in rows:
        fh.write(json.dumps(r, ensure_ascii=False) + "\n")
PY
hookv2 "${V2GRP}" audit agent "$(agentv2 u-grp)" >/dev/null
GRPREP="$(env -u TIER_GUARD_MODE HOME="${FAKEHOME}" python3 "${ROOT}/hooks/tier_report.py" --data "${V2GRP}")"
v2_grp_file() { has "${GRPREP}" "| claude-sonnet-5 | 1 | 10 | 20 | 30 | 4 |" && ! has "${GRPREP}" "claude-stale"; }
check "v2 report：同一 transcript 的两次 stop 只算一个子代理，用量取自回读的文件而非记录里存的值" "$(yn v2_grp_file)"
v2_grp_latest() { has "${GRPREP}" "| claude-haiku-4-5 | 1 | 2,000 | 400 | 3,000 | 50 |"; }
check "v2 report：文件没了且有两条带 usage_basis 的记录，取 ts 最晚的那条" "$(yn v2_grp_latest)"
v2_grp_untrusted() { ! has "${GRPREP}" "claude-opus-old" && has "${GRPREP}" "另有 1 个子代理只有修复前记下的用量（输入与缓存约重复计算一倍），未计入上表。"; }
check "v2 report：文件没了且只有修复前旧记录的子代理不入表，注脚写 1" "$(yn v2_grp_untrusted)"
v2_no_note() { ! has "${USEREP}" "未计入上表" && ! has "${LATEREP}" "未计入上表"; }
check "v2 report：没有不可信子代理时不出注脚" "$(yn v2_no_note)"
v2_header_unit() { has "${GRPREP}" "| 实际执行模型 | 子代理数 |" && ! has "${GRPREP}" "| 次数 |"; }
check "v2 report：用量表表头写明计数单位是子代理" "$(yn v2_header_unit)"

# 「建议档 vs 实际执行档」一节原先只认 v1 的 tier 字段，v2 恒显示「已关联 0 / N」，与表格里已入账的实际执行矛盾
# （2026-09-14 安装版 0.2.0 真实宿主验收发现）。v2 只报已观测次数，档位高低不在报告里推算。
v2_link_line() { has "${JOINREP}" "v2：已观测实际执行 1 / 2 次" && ! has "${JOINREP}" "已关联 0 / 2 次"; }
check "v2 report：建议 vs 实际一节按 tool_use_id 报已观测次数，不再恒为已关联 0" "$(yn v2_link_line)"
check "v2 report：建议 vs 实际一节同样回读未落盘的 transcript" "$(yn has "${LATEREP}" "v2：已观测实际执行 1 / 1 次")"
check "v1 report：只有旧记录时仍按 v1 口径，不出现 v2 行" "$(yn c_v1_only_link)"
V2MIXED="${TMP}/v2-mixed"; mkdir -p "${V2MIXED}"
cat "${DATA}/decisions.jsonl" "${V2JOIN}/decisions.jsonl" > "${V2MIXED}/decisions.jsonl"
MIXEDREP="$(env -u TIER_GUARD_MODE HOME="${FAKEHOME}" python3 "${ROOT}/hooks/tier_report.py" --data "${V2MIXED}")"
v2_mixed_link() { has "${MIXEDREP}" "v1 旧记录：已关联 0 / 5 次" && has "${MIXEDREP}" "v2：已观测实际执行 1 / 2 次"; }
check "混合日志：v1 分母只数旧记录，v2 单独报已观测次数" "$(yn v2_mixed_link)"

echo ""
echo "═══ 主代理预路由提醒（Task 12） ═══"
# 报告的输入照旧不手写：用真 hook（Claude 与 Codex 两侧）在 dispatch_nudge=true 的目录下
# 判一轮，再汇总它写下的 nudge 字段 —— 判据全在 route_decide.nudge_decision，这里只验证计数。
NUDGE_CATALOG="${TMP}/routing.catalog.v2.nudge-both.json"
python3 - "${ROOT}/config/routing.catalog.v2.json" "${NUDGE_CATALOG}" <<'PY'
import json, sys
cfg = json.load(open(sys.argv[1], encoding="utf-8"))
hc = cfg.setdefault("host_capabilities", {})
hc.setdefault("claude-code", {})["dispatch_nudge"] = True
hc.setdefault("codex-cli", {})["dispatch_nudge"] = True
with open(sys.argv[2], "w", encoding="utf-8") as fh:
    json.dump(cfg, fh, ensure_ascii=False)
PY
hookv2cfg() {  # $1=数据目录 $2=profile $3=事件 $4=payload $5=config
  printf '%s' "$4" | env HOME="${FAKEHOME}" TIER_GUARD_LOG_DIR="$1" TIER_GUARD_MODE="$2" \
    TIER_GUARD_CONFIG="$5" /bin/bash "${ROOT}/hooks/tier-guard.sh" "$3"
}
hookcodexcfg() {  # $1=数据目录 $2=profile $3=payload $4=config
  printf '%s' "$3" | env HOME="${FAKEHOME}" TIER_GUARD_LOG_DIR="$1" TIER_GUARD_MODE="$2" \
    TIER_GUARD_CONFIG="$4" /bin/bash "${ROOT}/hooks/tier-guard-codex.sh"
}
mknudge() {  # $1=session_id $2=tool_use_id $3=prompt $4=model(- 不传)
  python3 -c 'import json,sys
sid,tid,prompt,model=sys.argv[1:5]
ti={"description":"t","prompt":prompt,"subagent_type":"general-purpose"}
if model!="-": ti["model"]=model
print(json.dumps({"session_id":sid,"tool_use_id":tid,"tool_name":"Agent","tool_input":ti},ensure_ascii=False))' "$1" "$2" "$3" "$4"
}
spnudge() {  # $1=session_id $2=message —— fork_turns:"all" 是真实 Codex 每次都带的控制参数，与 pin 无关
  python3 -c 'import json,sys
sid,msg=sys.argv[1:3]
ti={"message":msg,"task_name":"t1","agent_type":"worker","fork_turns":"all"}
print(json.dumps({"session_id":sid,"turn_id":"t","cwd":"/x","hook_event_name":"PreToolUse",
                  "model":"gpt-5.6-terra","permission_mode":"default","transcript_path":None,
                  "tool_name":"spawn_agent","tool_use_id":"c1","tool_input":ti},ensure_ascii=False))' "$1" "$2"
}
NUDGEDATA="${TMP}/nudge-data"
NUDGETOKEN="反重力引擎设计方案禁止外泄"
# S1（audit）：未 pin → 提醒；pin → 不触发；未 pin → 提醒
hookv2cfg "${NUDGEDATA}" audit agent "$(mknudge n-s1 n-u1 "${V2SIMPLE} ${NUDGETOKEN}" -)"      "${NUDGE_CATALOG}" >/dev/null
hookv2cfg "${NUDGEDATA}" audit agent "$(mknudge n-s1 n-u2 "${V2SIMPLE}" sonnet)"                "${NUDGE_CATALOG}" >/dev/null
hookv2cfg "${NUDGEDATA}" audit agent "$(mknudge n-s1 n-u3 "${V2SIMPLE}" -)"                     "${NUDGE_CATALOG}" >/dev/null
# S2（auto）：未 pin → 本会话第一次拦截；pin → 不触发
hookv2cfg "${NUDGEDATA}" auto  agent "$(mknudge n-s2 n-u4 "${V2SIMPLE}" -)"                     "${NUDGE_CATALOG}" >/dev/null
hookv2cfg "${NUDGEDATA}" auto  agent "$(mknudge n-s2 n-u5 "${V2SIMPLE}" sonnet)"                "${NUDGE_CATALOG}" >/dev/null
# S3（Codex，audit）：未 pin → 提醒
hookcodexcfg "${NUDGEDATA}" audit "$(spnudge n-s3 "${V2SIMPLE}")" "${NUDGE_CATALOG}" >/dev/null
NUDGEREP="$(env -u TIER_GUARD_MODE HOME="${FAKEHOME}" python3 "${ROOT}/hooks/tier_report.py" --data "${NUDGEDATA}")"
check "report：主代理预路由提醒段落存在" "$(yn has "${NUDGEREP}" "### 主代理预路由提醒")"
check "report：提醒 3 / 拦截 1 / 未触发 2（共 6 次派活）" \
  "$(yn has "${NUDGEREP}" "提醒 3 次 / 拦截 1 次 / 未触发 2 次（共 6 次派活）。")"
check "report：提醒或拦截之后同会话派活 3 次，显式传参 2 次" \
  "$(yn has "${NUDGEREP}" "提醒或拦截之后同会话派活 3 次，其中显式传参 2 次（2/3）。")"
check "report：pin 的派活被提醒或拦截 0 次" \
  "$(yn has "${NUDGEREP}" "pin 的派活被提醒或拦截 0 次（应为 0）。")"
c_no_prompt() { ! has "${NUDGEREP}" "${NUDGETOKEN}"; }
check "report：提醒统计不泄露 prompt 原文" "$(yn c_no_prompt)"

# 缺 nudge 字段的 v2 记录（schema 升级前的旧日志）必须被忽略，不能计入统计。
# 基底记录本身仍由真 hook 产出，这里只对复制出来的第二行删掉 nudge 键，模拟旧版本没有这个字段。
NUDGELEGACY="${TMP}/nudge-legacy"
hookv2cfg "${NUDGELEGACY}" audit agent "$(mknudge n-legacy n-legacy-u1 "${V2SIMPLE}" -)" "${NUDGE_CATALOG}" >/dev/null
python3 - "${NUDGELEGACY}/decisions.jsonl" <<'PY'
import json, sys
path = sys.argv[1]
lines = open(path, encoding="utf-8").read().splitlines()
rec = json.loads(lines[-1])
del rec["nudge"]
lines.append(json.dumps(rec, ensure_ascii=False))
open(path, "w", encoding="utf-8").write("\n".join(lines) + "\n")
PY
LEGACYREP="$(env -u TIER_GUARD_MODE HOME="${FAKEHOME}" python3 "${ROOT}/hooks/tier_report.py" --data "${NUDGELEGACY}")"
check "report：缺 nudge 字段的 v2 记录被忽略，只数带该字段的那条" \
  "$(yn has "${LEGACYREP}" "提醒 1 次 / 拦截 0 次 / 未触发 0 次（共 1 次派活）。")"

echo ""
echo "  总计 ${PASS} 通过 / ${FAIL} 失败"
[ "${PASS}" -gt 0 ] && [ "${FAIL}" -eq 0 ]
