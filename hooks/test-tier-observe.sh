#!/bin/bash
# ─────────────────────────────────────────────────────────────
# Task 6 可观测性回归：SubagentStop 记实际档、建议 vs 实际、打回率、误报率、auto 门槛、占比。
#
# 判定记录一律由真 hook（tier-guard.sh）产生；子代理 transcript / .meta.json 夹具的结构照
# 2026-09-12 差分验收时读到的真实文件造（meta 里有 toolUseId，assistant 消息带 model）。
# ─────────────────────────────────────────────────────────────
set -uo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TMP="$(mktemp -d)"
trap 'rm -rf "${TMP}"' EXIT
PASS=0; FAIL=0
check() { if [ "$2" = yes ]; then printf '  ✅ %s\n' "$1"; PASS=$((PASS+1)); else printf '  ❌ %s\n' "$1"; FAIL=$((FAIL+1)); fi; }
# yn 只包一条命令；复合条件写成具名函数（`$(yn A && B)` 是永远为真的空断言）
yn() { if "$@"; then echo yes; else echo no; fi; }
has() { case "$1" in *"$2"*) return 0 ;; *) return 1 ;; esac; }
FAKEHOME="${TMP}/home"; mkdir -p "${FAKEHOME}"

hook() {  # $1=数据目录 $2=事件 $3=payload
  printf '%s' "$3" | env -u TIER_GUARD_MODE HOME="${FAKEHOME}" TIER_GUARD_LOG_DIR="$1" TIER_GUARD_CONFIG="${ROOT}/config/routing.default.json" /bin/bash "${ROOT}/hooks/tier-guard.sh" "$2"
}
report() { env -u TIER_GUARD_MODE HOME="${FAKEHOME}" python3 "${ROOT}/hooks/tier_report.py" --data "$1" "${@:2}"; }
label()  { env -u TIER_GUARD_MODE HOME="${FAKEHOME}" python3 "${ROOT}/hooks/tier_label.py" "$2" "$3" --data "$1"; }
state()  { env -u TIER_GUARD_MODE HOME="${FAKEHOME}" python3 "${ROOT}/hooks/tier_state.py" "${@:2}" --data "$1" --config "${ROOT}/config/routing.default.json"; }

# Agent 的 PreToolUse payload：$1=tool_use_id $2=session $3=description $4=model(-) $5=prompt $6=主 transcript
agentp() {
  python3 - "$@" <<'PY'
import json, sys
tid, sess, desc, model, prompt, tr = sys.argv[1:7]
ti = {"description": desc, "prompt": prompt, "subagent_type": "general-purpose"}
if model != "-":
    ti["model"] = model
print(json.dumps({"session_id": sess, "tool_use_id": tid, "transcript_path": tr, "tool_name": "Agent",
                  "tool_input": ti}, ensure_ascii=False))
PY
}
# 造一份主会话 transcript（含这次 Agent 调用的 tool_use）：$1=文件 $2=tool_use_id $3=prompt
maintr() {
  python3 - "$@" <<'PY'
import json, sys
path, tid, prompt = sys.argv[1:4]
with open(path, "a", encoding="utf-8") as fh:
    fh.write(json.dumps({"type": "assistant", "message": {"role": "assistant", "model": "claude-opus-5",
        "content": [{"type": "tool_use", "id": tid, "name": "Agent", "input": {"prompt": prompt}}]}}, ensure_ascii=False) + "\n")
PY
}
# 造一份子代理 transcript（+ 可选 meta）并打一次 SubagentStop：$1=数据目录 $2=tool_use_id $3=实际模型 $4=prompt $5=meta(yes|no) $6=最后回复
stop() {
  local f="${TMP}/proj/sess/subagents/agent-$2.jsonl"
  mkdir -p "$(dirname "${f}")"
  python3 - "${f}" "$2" "$3" "$4" "$5" <<'PY'
import json, sys
f, tid, model, prompt, meta = sys.argv[1:6]
with open(f, "w", encoding="utf-8") as fh:
    fh.write(json.dumps({"type": "user", "isSidechain": True, "message": {"role": "user", "content": prompt}}, ensure_ascii=False) + "\n")
    fh.write(json.dumps({"type": "attachment", "isSidechain": True}) + "\n")
    fh.write(json.dumps({"type": "assistant", "isSidechain": True, "message": {"role": "assistant", "model": model,
        "content": [{"type": "text", "text": "ok"}]}}, ensure_ascii=False) + "\n")
if meta == "yes":
    json.dump({"agentType": "general-purpose", "description": "d", "toolUseId": tid, "model": "sonnet"},
              open(f[:-len(".jsonl")] + ".meta.json", "w", encoding="utf-8"))
PY
  hook "$1" subagent-stop "$(python3 -c 'import json,sys; print(json.dumps({"session_id":"s","hook_event_name":"SubagentStop","agent_transcript_path":sys.argv[1],"last_assistant_message":sys.argv[2]},ensure_ascii=False))' "${f}" "$6")"
}
lastlog() {  # $1=数据目录 $2=python 表达式（r = 最后一条日志）
  python3 - "$1/decisions.jsonl" "$2" <<'PY'
import json, sys
try:
    r = json.loads(open(sys.argv[1], encoding="utf-8").read().splitlines()[-1])
    print("yes" if eval(sys.argv[2]) else "no")
except Exception:
    print("no")
PY
}

PAD="背景：这是一段中性的背景说明，只用来让 prompt 越过收益门槛，不含任何判据词。背景：这是一段中性的背景说明，只用来让 prompt 越过收益门槛。背景：再补一句中性的说明文字，凑够长度。"
PAD="${PAD}${PAD}"
AC=$'\n验收：pytest 全绿\n'
IRRP="改完后 git push 到 origin。${AC}${PAD}"
SAFEP="按 spec 第 3 节实现缓存层。${AC}${PAD}"
MAIN="${TMP}/main.jsonl"; : > "${MAIN}"

echo "═══ SubagentStop：实际执行档 ═══"
D1="${TMP}/d1"
hook "${D1}" agent "$(agentp u-irr s d-irr sonnet "${IRRP}" "${MAIN}")" >/dev/null
OUT="$(stop "${D1}" u-irr claude-sonnet-5 "${IRRP}" yes "完成了")"
check "SubagentStop：stdout 永远为空" "$(yn [ -z "${OUT}" ])"
check "SubagentStop：按 meta 的 toolUseId 关联、实际模型 claude-sonnet-5 → T1" \
  "$(lastlog "${D1}" 'r["event"] == "subagent-stop" and r["tool_use_id"] == "u-irr" and r["actual_tier"] == "T1"')"
check "SubagentStop：正常完成 → 不算升级触发" "$(lastlog "${D1}" 'r["escalated"] is False')"
hook "${D1}" agent "$(agentp u-nometa s d-nometa sonnet "${SAFEP}" "${MAIN}")" >/dev/null
stop "${D1}" u-nometa claude-opus-5 "${SAFEP}" no "② 验收标准有歧义，我先停止，把现状交回。" >/dev/null
check "SubagentStop：没有 meta → 记 prompt sha256 兜底" "$(lastlog "${D1}" 'r["tool_use_id"] is None and len(r["prompt_sha256"]) == 64')"
check "SubagentStop：引用合同 ② 并交回 → 升级触发" "$(lastlog "${D1}" 'r["escalated"] is True')"
OUT="$(hook "${D1}" subagent-stop '{"session_id":"s","agent_transcript_path":"/nonexistent/agent.jsonl"}')"; RC=$?
c_stop_missing() { [ "${RC}" -eq 0 ] && [ -z "${OUT}" ]; }
check "SubagentStop：transcript 不存在 → 退出 0、stdout 空" "$(yn c_stop_missing)"
check "SubagentStop：transcript 不存在 → 日志写明 fallback" "$(lastlog "${D1}" '"FileNotFoundError" in r["fallback"]')"
REP="$(report "${D1}")"
check "report：两次都关联上（meta 与 sha256 两条路）" "$(yn has "${REP}" "已关联 2 / 2 次")"
check "report：建议 T2 实际 T1 → 实际欠配 1" "$(yn has "${REP}" "**实际欠配**（实际档低于建议档）1 次")"
check "report：升级触发 1" "$(yn has "${REP}" "疑似升级触发（子代理照合同交回）1 次")"
check "report：实际欠配列出的是 u-irr（建议 T2 实际 T1），不是方向反了的那条" "$(yn has "${REP}" '`u-irr`：建议 T2，实际 T1')"

echo ""
echo "═══ 打回率 ═══"
D2="${TMP}/d2"
hook "${D2}" agent "$(agentp u-a1 s2 同一件事 sonnet "${SAFEP}" "${MAIN}")" >/dev/null
stop "${D2}" u-a1 claude-sonnet-5 "${SAFEP}" yes "完成了" >/dev/null
hook "${D2}" agent "$(agentp u-a2 s2 同一件事 sonnet "${SAFEP}再补一句" "${MAIN}")" >/dev/null
stop "${D2}" u-a2 claude-sonnet-5 "${SAFEP}再补一句" yes "完成了" >/dev/null
hook "${D2}" agent "$(agentp u-a3 s3 同一件事 sonnet "${SAFEP}换个会话" "${MAIN}")" >/dev/null
check "打回：同会话同 description 重派 → 前一次记打回（另一会话的不算）" \
  "$(yn has "$(report "${D2}")" "T1 子代理 2 次，打回 1 次（50%；重派推断 1，人工标注 0）")"
label "${D2}" u-a1 accept >/dev/null
check "打回：人工 accept 覆写重派推断" "$(yn has "$(report "${D2}")" "T1 子代理 2 次，打回 0 次")"
label "${D2}" u-a2 reject >/dev/null
check "打回：人工 reject 计入" "$(yn has "$(report "${D2}")" "打回 1 次（50%；重派推断 0，人工标注 1）")"

echo ""
echo "═══ /tier-label 校验 ═══"
label "${D2}" u-nope reject >/dev/null; RC=$?
check "label：不存在的 id → 拒绝" "$(yn [ "${RC}" -ne 0 ])"
label "${D2}" u-a1 fp >/dev/null; RC=$?
check "label：没命中 R-IRREVERSIBLE 的记录标 fp → 拒绝" "$(yn [ "${RC}" -ne 0 ])"
label "${D2}" u-a3 reject >/dev/null; RC=$?
check "label：没跑成 T1 子代理的记录标 reject → 拒绝" "$(yn [ "${RC}" -ne 0 ])"
label "${D2}" u-a1 maybe >/dev/null; RC=$?
check "label：未知判定 → 拒绝" "$(yn [ "${RC}" -ne 0 ])"
# Phase 9：v2 记录没有 R-IRREVERSIBLE / T1 判定，/tier-label 只用于 v1 历史记录，要明说而不是报「没命中」
DV2="${TMP}/dv2"; mkdir -p "${DV2}"
printf '%s' "$(agentp u-v2 s2 d - $'只读审查配置，禁止修改任何文件。\n验收：报告所有键名。' /nope)" | env -u TIER_GUARD_MODE HOME="${FAKEHOME}" \
  TIER_GUARD_LOG_DIR="${DV2}" TIER_GUARD_CONFIG="${ROOT}/config/routing.catalog.v2.json" /bin/bash "${ROOT}/hooks/tier-guard.sh" agent >/dev/null
OUT="$(label "${DV2}" u-v2 fp)"; RC=$?
v2_label_refused() { [ "${RC}" -ne 0 ] && has "${OUT}" "仅限 v1 历史记录"; }
check "label：v2 记录 → 拒绝并说明仅限 v1 历史记录" "$(yn v2_label_refused)"

echo ""
echo "═══ 误报率与片段 ═══"
D3="${TMP}/d3"
SECRETP="部署前把 API_KEY=test_token_not_a_secret_abcdefghijklmnopqrstuvwxyz0123 写进 .env 然后 deploy。${AC}${PAD}"
maintr "${MAIN}" u-f1 "${IRRP}"; maintr "${MAIN}" u-f2 "${IRRP}"; maintr "${MAIN}" u-f3 "${SECRETP}"
hook "${D3}" agent "$(agentp u-f1 s f1 sonnet "${IRRP}" "${MAIN}")" >/dev/null
hook "${D3}" agent "$(agentp u-f2 s f2 sonnet "${IRRP}" "${MAIN}")" >/dev/null
hook "${D3}" agent "$(agentp u-f3 s f3 sonnet "${SECRETP}" "${MAIN}")" >/dev/null
hook "${D3}" agent "$(agentp u-f4 s f4 sonnet "${IRRP}" "${TMP}/gone.jsonl")" >/dev/null
# 密钥跨在片段左边界上：token 结尾离命中词正好 35 字（窗口 40）。不把窗口扩到整段 token，
# 就会切出 token 的最后 5 个字符 —— 不到 20 字，打码正则抓不住，半截密钥就漏出去了。
EDGEP="$(python3 -c 'tok = "ghp_" + "a" * 27 + "Z9x7"; fill = "这是一段用来隔开密钥和命中词的中文说明文字，长度正好三十五个字符的样子吗？"[:35]; print("前情：" + tok + fill + "deploy 到生产。\n验收：CI 绿\n" + "背景说明" * 40)')"
maintr "${MAIN}" u-f5 "${EDGEP}"
hook "${D3}" agent "$(agentp u-f5 s f5 sonnet "${EDGEP}" "${MAIN}")" >/dev/null
label "${D3}" u-f1 fp >/dev/null; label "${D3}" u-f2 tp >/dev/null
REP="$(report "${D3}")"
check "误报率：已标注 2 条、误报 1 条（50%）" "$(yn has "${REP}" "命中 5 条，已标注 2 条，其中误报 1 条（50%）")"
c_no_edge() { has "${REP}" '`u-f5` 命中' && ! has "${REP}" "Z9x7"; }
check "待标注：跨在片段边界上的密钥也整段打码（不漏半截）" "$(yn c_no_edge)"
check "待标注：列出未标注的 u-f3" "$(yn has "${REP}" '`u-f3` 命中')"
check "待标注：片段里的长 token 被打码" "$(yn has "${REP}" "[已打码]")"
c_no_secret() { ! has "${REP}" "test_token_not_a_secret" && ! has "${REP}" "0123 写进"; }
check "待标注：密钥一个字符都不漏（含半截）" "$(yn c_no_secret)"
check "待标注：transcript 读不到 → 明说无法给片段" "$(yn has "${REP}" "transcript 读不到，无法给片段")"
c_no_f1() { ! has "${REP}" '`u-f1` 命中'; }
check "待标注：已标注的 u-f1 不再列出" "$(yn c_no_f1)"

echo ""
echo "═══ auto 门槛 ═══"
OUT="$(state "${D3}" set auto)"; RC=$?
c_gate_small() { [ "${RC}" -ne 0 ] && has "${OUT}" "误报率样本不足" && has "${OUT}" "打回率样本不足"; }
check "门槛：样本不足 → /tier-mode auto 拒绝并说明" "$(yn c_gate_small)"
D4="${TMP}/d4"
i=1
while [ "${i}" -le 20 ]; do
  hook "${D4}" agent "$(agentp "g-irr-${i}" s "irr-${i}" sonnet "${IRRP}" "${MAIN}")" >/dev/null
  hook "${D4}" agent "$(agentp "g-t1-${i}" s "t1-${i}" sonnet "${SAFEP}${i}" "${MAIN}")" >/dev/null
  stop "${D4}" "g-t1-${i}" claude-sonnet-5 "${SAFEP}${i}" yes "完成了" >/dev/null
  if [ "${i}" -eq 1 ]; then label "${D4}" "g-irr-${i}" fp >/dev/null; else label "${D4}" "g-irr-${i}" tp >/dev/null; fi
  i=$((i+1))
done
check "门槛：20 条已标注误报 1 条（5%）+ 20 次 T1 无打回 → report 显示已满足" \
  "$(yn has "$(report "${D4}")" "✅ 数据门槛已满足")"
label "${D4}" g-irr-2 fp >/dev/null
OUT="$(state "${D4}" set auto)"; RC=$?
c_gate_fp() { [ "${RC}" -ne 0 ] && has "${OUT}" "误报率 2/20"; }
check "门槛：误报率恰好 10% → 拒绝（要 < 10%）" "$(yn c_gate_fp)"
label "${D4}" g-irr-2 tp >/dev/null
label "${D4}" g-t1-19 reject >/dev/null; label "${D4}" g-t1-20 reject >/dev/null
OUT="$(state "${D4}" set auto)"; RC=$?
c_gate_rej() { [ "${RC}" -ne 0 ] && has "${OUT}" "打回率在上升"; }
check "门槛：打回率前半 0% → 后半 20% → 拒绝" "$(yn c_gate_rej)"
label "${D4}" g-t1-19 accept >/dev/null; label "${D4}" g-t1-20 accept >/dev/null
OUT="$(state "${D4}" set auto)"; RC=$?
c_gate_ok() { [ "${RC}" -eq 0 ] && [ "$(cat "${D4}/mode")" = auto ]; }
check "门槛全过 → /tier-mode auto 放行并写入状态文件" "$(yn c_gate_ok)"

echo ""
echo "═══ subagent 占比（--share）═══"
P="${TMP}/projects"; mkdir -p "${P}/proj/sess/subagents" "${P}/old"
python3 - "${P}" <<'PY'
import json, os, sys, time
p = sys.argv[1]
def w(path, lines):
    with open(path, "w", encoding="utf-8") as fh:
        for l in lines:
            fh.write(json.dumps(l) + "\n")
a = lambda mid, out: {"type": "assistant", "message": {"role": "assistant", "id": mid, "usage": {"output_tokens": out}}}
w(f"{p}/proj/main.jsonl", [a("m1", 100), a("m1", 300)])           # 流式重复：取 300，不是 400
w(f"{p}/proj/sess/subagents/agent-x.jsonl", [a("s1", 100)])
w(f"{p}/old/main.jsonl", [a("o1", 5000)])                         # 30 天前，不算
old = time.time() - 30 * 86400
os.utime(f"{p}/old/main.jsonl", (old, old))
PY
REP="$(report "${D1}" --share 7 --projects "${P}")"
check "share：同一条消息只算一次、旧文件不算 → 100 / (300+100) = 25.0%" "$(yn has "${REP}" "占比 **25.0%**")"
check "share：报出扫了几个文件" "$(yn has "${REP}" "扫了 2 个 transcript")"
c_noshare() { ! has "$(report "${D1}")" "subagent 占比"; }
check "不加 --share 时不扫 transcript" "$(yn c_noshare)"

echo ""
echo "  总计 ${PASS} 通过 / ${FAIL} 失败"
[ "${PASS}" -gt 0 ] && [ "${FAIL}" -eq 0 ]
