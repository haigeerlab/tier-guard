#!/bin/bash
# ─────────────────────────────────────────────────────────────
# Claude 薄壳（tier-guard.sh + claude_hook.py）的回归断言。
#
# 判据本身的正反用例在 route_decide.py --selftest；这里只测薄壳自己的职责：
#   - 放行：异常 / 缺字段 / fork / python 不在 → 一律退出 0、stdout 空
#   - dry-run 下**没有任何**返回 updatedInput 的路径（扫一遍，不是口头保证）
#   - off 下与未装插件一致：stdout 空、退出 0、不留日志
#   - auto 下 updatedInput 只改 model、其余字段原样，路由路径永不出现 deny / ask（deny 只来自下面的 v2 提醒）
#   - agent 定义解析（项目优先于用户目录）、Codex 派活「建议 vs 实际」
#   - v2 主代理预路由提醒（Task 10）：宿主 dispatch_nudge 关闭时 audit 的 v2 stdout
#     确实为空；开启后 audit 会输出 additionalContext，auto 每会话第一次未 pin 会 deny
#   - 单次执行 < 100ms（实测中位数）
# ─────────────────────────────────────────────────────────────
set -uo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
HOOK="${ROOT}/hooks/tier-guard.sh"
TMP="$(mktemp -d)"
trap 'rm -rf "${TMP}"' EXIT
PASS=0; FAIL=0
ok()  { printf '  ✅ %s\n' "$1"; PASS=$((PASS+1)); }
bad() { printf '  ❌ %s\n' "$1"; FAIL=$((FAIL+1)); }
check() { if [ "$2" = yes ]; then ok "$1"; else bad "$1"; fi; }  # $1=说明 $2=yes|no

FAKEHOME="${TMP}/home"; PROJ="${TMP}/proj"; LOGD="${TMP}/log"
mkdir -p "${FAKEHOME}/.claude/agents" "${PROJ}/.claude/agents"
agent() {  # $1=目录 $2=name $3=model（- 表示不写 model 行）
  { echo "---"; echo "name: $2"; [ "$3" = - ] || echo "model: $3"; echo "description: x"; echo "---"; echo "body"; } \
    > "$1/.claude/agents/$2.md"
}
agent "${FAKEHOME}" executor sonnet
agent "${FAKEHOME}" shadowed sonnet
agent "${PROJ}"     shadowed haiku
agent "${FAKEHOME}" nomodel -
agent "${FAKEHOME}" inheritor inherit
agent "${FAKEHOME}" defaulter default

# $1=mode $2=payload [$3=事件] → 设置 OUT / RC
run() {
  local mode="$1" payload="$2" ev="${3:-agent}"
  OUT="$(printf '%s' "${payload}" | env HOME="${FAKEHOME}" CLAUDE_PROJECT_DIR="${PROJ}" \
          TIER_GUARD_LOG_DIR="${LOGD}" TIER_GUARD_MODE="${mode}" \
          TIER_GUARD_CONFIG="${ROOT}/config/routing.default.json" /bin/bash "${HOOK}" "${ev}")"
  RC=$?
}
# v2 使用独立目录，避免迁移期旧配置的断言与新路由混在一起。
runv2with() {  # $1=profile $2=payload $3=config [$4=事件]
  local profile="$1" payload="$2" config="$3" ev="${4:-agent}"
  OUT="$(printf '%s' "${payload}" | env HOME="${FAKEHOME}" CLAUDE_PROJECT_DIR="${PROJ}" \
          TIER_GUARD_LOG_DIR="${LOGD}" TIER_GUARD_MODE="${profile}" \
          TIER_GUARD_CONFIG="${config}" /bin/bash "${HOOK}" "${ev}")"
  RC=$?
}
# 路由编码用例与主代理提醒分开测：生产目录已为 claude-code 打开 dispatch_nudge（Task 15），
# 这里用只关掉 claude-code.dispatch_nudge 的派生目录，其余字段与生产目录一致。
runv2() { runv2with "$1" "$2" "${V2_ROUTE_CONFIG}" "${3:-agent}"; }
runv2unverified() { runv2with "$1" "$2" "${V2_UNVERIFIED_CONFIG}" "${3:-agent}"; }
# 用 python 拼 payload / 断言 JSON，避免 jq 依赖
mk() {  # $1=prompt $2=model(- 不传) $3=subagent_type
  python3 - "$1" "$2" "$3" <<'PY'
import json, sys
prompt, model, st = sys.argv[1:4]
ti = {"description": "t", "prompt": prompt, "subagent_type": st, "run_in_background": False}
if model != "-":
    ti["model"] = model
print(json.dumps({"session_id": "s", "tool_use_id": "u", "hook_event_name": "PreToolUse",
                  "tool_name": "Agent", "tool_input": ti}, ensure_ascii=False))
PY
}
lastlog() {  # $1=python 表达式（变量 r = 最后一条日志）→ 打印结果
  python3 - "$1" "${LOGD}/decisions.jsonl" <<'PY'
import json, sys
expr, path = sys.argv[1], sys.argv[2]
try:
    r = json.loads(open(path, encoding="utf-8").read().splitlines()[-1])
    print("yes" if eval(expr) else "no")
except Exception as e:
    print("no")
PY
}
jsonq() {  # $1=python 表达式（变量 o = stdout 解析出的 JSON）
  python3 - "$1" "${OUT}" <<'PY'
import json, sys
try:
    o = json.loads(sys.argv[2])
    print("yes" if eval(sys.argv[1]) else "no")
except Exception:
    print("no")
PY
}
yn() { if "$@"; then echo yes; else echo no; fi; }

V2_ROUTE_CONFIG="${TMP}/routing.catalog.v2.route.json"
python3 - "${ROOT}/config/routing.catalog.v2.json" "${V2_ROUTE_CONFIG}" <<'PY'
import json, sys
cfg = json.load(open(sys.argv[1], encoding="utf-8"))
cfg["host_capabilities"]["claude-code"]["dispatch_nudge"] = False
with open(sys.argv[2], "w", encoding="utf-8") as fh:
    json.dump(cfg, fh, ensure_ascii=False)
PY
V2_CATALOG_SHA="$(shasum -a 256 "${V2_ROUTE_CONFIG}" | awk '{print $1}')"

# 反向用例：即使处在 auto，未获宿主授权的目录也必须只审计。
V2_UNVERIFIED_CONFIG="${TMP}/routing.catalog.v2.unverified.json"
python3 - "${ROOT}/config/routing.catalog.v2.json" "${V2_UNVERIFIED_CONFIG}" <<'PY'
import json, sys
cfg = json.load(open(sys.argv[1], encoding="utf-8"))
cfg.setdefault("host_capabilities", {}).setdefault("claude-code", {})["pre_dispatch_apply"] = False
cfg["host_capabilities"]["claude-code"]["dispatch_nudge"] = False  # 路由编码用例不掺主代理提醒（生产目录已开 Claude 闸门）
with open(sys.argv[2], "w", encoding="utf-8") as fh:
    json.dump(cfg, fh, ensure_ascii=False)
PY

# nudge 专用：从 v2 目录派生一份 dispatch_nudge=true 的副本，其余字段原样
# （生产目录 claude-code.pre_dispatch_apply 已是 true，够测「deny 之后第二次带 updatedInput」）。
V2_NUDGE_CONFIG="${TMP}/routing.catalog.v2.nudge.json"
python3 - "${ROOT}/config/routing.catalog.v2.json" "${V2_NUDGE_CONFIG}" <<'PY'
import json, sys
cfg = json.load(open(sys.argv[1], encoding="utf-8"))
cfg.setdefault("host_capabilities", {}).setdefault("claude-code", {})["dispatch_nudge"] = True
with open(sys.argv[2], "w", encoding="utf-8") as fh:
    json.dump(cfg, fh, ensure_ascii=False)
PY
# nudge 测试用独立日志目录，别和上面 v2 断言的 LOGD 混在一起
NLOGD="${TMP}/nudge-log"
runnudgewith() {  # $1=profile $2=payload $3=config $4=logdir [$5=事件]
  local profile="$1" payload="$2" config="$3" ld="$4" ev="${5:-agent}"
  OUT="$(printf '%s' "${payload}" | env HOME="${FAKEHOME}" CLAUDE_PROJECT_DIR="${PROJ}" \
          TIER_GUARD_LOG_DIR="${ld}" TIER_GUARD_MODE="${profile}" \
          TIER_GUARD_CONFIG="${config}" /bin/bash "${HOOK}" "${ev}")"
  RC=$?
}
runnudge()     { runnudgewith "$1" "$2" "${V2_NUDGE_CONFIG}"            "${NLOGD}" "${3:-agent}"; }
runnudgeprod() { runnudgewith "$1" "$2" "${ROOT}/config/routing.catalog.v2.json" "${NLOGD}" "${3:-agent}"; }
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
mksess() {  # $1=session_id（- 表示不传该字段）$2=prompt $3=model（- 不传）$4=subagent_type
  python3 - "$1" "$2" "$3" "$4" <<'PY'
import json, sys
sid, prompt, model, st = sys.argv[1:5]
ti = {"description": "t", "prompt": prompt, "subagent_type": st, "run_in_background": False}
if model != "-":
    ti["model"] = model
payload = {"tool_use_id": "u", "hook_event_name": "PreToolUse", "tool_name": "Agent", "tool_input": ti}
if sid != "-":
    payload["session_id"] = sid
print(json.dumps(payload, ensure_ascii=False))
PY
}

PAD="背景：这是一段中性的背景说明，只用来让 prompt 越过收益门槛，不含任何判据词。背景：这是一段中性的背景说明，只用来让 prompt 越过收益门槛。背景：再补一句中性的说明文字，凑够长度。"
AC=$'\n验收：python3 -m pytest 全绿\n'
IRR="$(mk "改完后 git push 到 origin。${AC}${PAD}" sonnet executor)"
SAFE="$(mk "按 spec 第 3 节实现缓存层。${AC}${PAD}" sonnet executor)"

echo "═══ tier-guard.sh 回归 ═══"

# ── off：与未装插件一致 ──
rm -rf "${LOGD}"
run off "${IRR}"
check "off：退出 0、stdout 空" "$(yn [ "${RC}" -eq 0 -a -z "${OUT}" ])"
check "off：不留日志" "$(yn [ ! -e "${LOGD}/decisions.jsonl" ])"

# ── dry-run：只记不改 ──
run dry-run "${IRR}"
check "dry-run：欠配调用 stdout 仍为空" "$(yn [ "${RC}" -eq 0 -a -z "${OUT}" ])"
check "dry-run：日志记下 raise，applied=false" \
  "$(lastlog 'r["decision"]["action"] == "raise" and r["applied"] is False')"
check "dry-run：日志不含 prompt 原文（只有长度和 sha256）" \
  "$(lastlog '"改完后" not in json.dumps(r, ensure_ascii=False) and len(r["prompt_sha256"]) == 64')"
LEAK=0
for p in "改完后 git push。${AC}${PAD}" "把 foo 改名为 bar。${PAD}" "两种做法权衡后选一个。${AC}${PAD}" "改个常量。${AC}"; do
  for m in haiku sonnet opus -; do
    for st in executor fork nomodel general-purpose; do
      run dry-run "$(mk "${p}" "${m}" "${st}")"
      [ "${RC}" -eq 0 ] && [ -z "${OUT}" ] || LEAK=$((LEAK+1))
    done
  done
done
check "dry-run：64 种组合里没有一条产出 stdout（updatedInput 路径不存在）" "$(yn [ "${LEAK}" -eq 0 ])"

# ── auto：只改 model ──
run auto "${IRR}"
check "auto：欠配调用 → updatedInput.model = opus" \
  "$(jsonq 'o["hookSpecificOutput"]["hookEventName"] == "PreToolUse" and o["hookSpecificOutput"]["updatedInput"]["model"] == "opus"')"
check "auto：updatedInput 其余字段原样" \
  "$(jsonq 'o["hookSpecificOutput"]["updatedInput"]["prompt"].startswith("改完后 git push") and o["hookSpecificOutput"]["updatedInput"]["subagent_type"] == "executor" and o["hookSpecificOutput"]["updatedInput"]["run_in_background"] is False')"
check "auto：不带 permissionDecision（不绕过权限流程）" \
  "$(jsonq '"permissionDecision" not in o["hookSpecificOutput"]')"
check "auto：日志标记已输出 updatedInput" "$(lastlog 'r["applied"] is True')"
run auto "${SAFE}"
check "auto：无 floor 的 sonnet 调用 → stdout 空" "$(yn [ -z "${OUT}" ])"
run auto "$(mk "改完后 git push 到 origin。${AC}${PAD}" opus executor)"
check "auto：动作词 + opus → stdout 空（不算欠配）" "$(yn [ -z "${OUT}" ])"
run auto "$(mk "git push。${PAD}" sonnet fork)"
check "auto：fork → 原样放行" "$(yn [ -z "${OUT}" ])"
DENY=0
for p in "改完后 git push。${AC}${PAD}" "把 foo 改名为 bar。${PAD}" "改个常量。${AC}"; do
  for m in haiku sonnet opus -; do
    run auto "$(mk "${p}" "${m}" executor)"
    case "${OUT}" in *deny*|*'"ask"'*) DENY=$((DENY+1)) ;; esac
  done
done
check "auto：任何组合都不出现 deny / ask" "$(yn [ "${DENY}" -eq 0 ])"
run deny "${IRR}"
check "未知 mode（deny）→ 放行" "$(yn [ "${RC}" -eq 0 -a -z "${OUT}" ])"

# ── 异常一律放行，且日志能看出是哪条路径 ──
run auto 'not json'
check "payload 不是 JSON → 退出 0、stdout 空" "$(yn [ "${RC}" -eq 0 -a -z "${OUT}" ])"
check "payload 不是 JSON → 日志写明 fallback（claude_hook 自己接住，不是薄壳兜底）" \
  "$(lastlog 'r["fallback"].startswith("claude_hook:")')"
run auto '{"tool_name":"Agent","tool_input":{"subagent_type":"x"}}'
check "缺 prompt → 退出 0、stdout 空" "$(yn [ "${RC}" -eq 0 -a -z "${OUT}" ])"
check "缺 prompt → 日志写明缺什么" "$(lastlog '"prompt" in r["decision"]["fallback"]')"
OUT="$(printf '%s' "${IRR}" | env HOME="${FAKEHOME}" TIER_GUARD_LOG_DIR="${LOGD}" TIER_GUARD_MODE=auto \
        TIER_GUARD_CONFIG=/nonexistent/routing.json /bin/bash "${HOOK}" agent)"; RC=$?
check "配置读不到 → 退出 0、stdout 空" "$(yn [ "${RC}" -eq 0 -a -z "${OUT}" ])"
mkdir -p "${TMP}/bin"; ln -s /bin/cat "${TMP}/bin/cat"; ln -s /usr/bin/dirname "${TMP}/bin/dirname"
OUT="$(printf '%s' "${IRR}" | env PATH="${TMP}/bin" TIER_GUARD_LOG_DIR="${LOGD}" TIER_GUARD_MODE=auto \
        /bin/bash "${HOOK}" agent)"; RC=$?
check "python3 不在 PATH → 退出 0、stdout 空" "$(yn [ "${RC}" -eq 0 -a -z "${OUT}" ])"
check "python3 不在 PATH → 薄壳自己补一条 fallback 记录" "$(lastlog '"没跑起来" in r["fallback"]')"

# ── agent 定义解析 ──
run auto "$(mk "改完后 git push。${AC}${PAD}" - executor)"
check "agent：未传 model 时读 ~/.claude/agents 的 frontmatter（sonnet → T1）" \
  "$(lastlog 'r["decision"]["start_tier"] == "T1" and r["agent_model"] == "sonnet"')"
run dry-run "$(mk "跑测试。${AC}${PAD}" - shadowed)"
check "agent：项目 .claude/agents 优先于用户目录（haiku → T0）" "$(lastlog 'r["decision"]["start_tier"] == "T0"')"
run dry-run "$(mk "跑测试。${AC}${PAD}" - nomodel)"
check "agent：没钉 model → 日志有 R2 提示" "$(lastlog 'any(w["rule"] == "R2" for w in r["decision"]["why"])')"
run dry-run "$(mk "跑测试。${AC}${PAD}" - some-plugin:executor)"
check "agent：插件 agent（带冒号）不解析，也不判 R2" \
  "$(lastlog 'r["agent_model"] == "(未解析)" and not any(w["rule"] == "R2" for w in r["decision"]["why"])')"

# ── Bash：Codex 派活的「建议 vs 实际」（Task 4a）──
bashp() {  # $1=命令
  python3 -c 'import json,sys; print(json.dumps({"session_id":"s","tool_use_id":"b","tool_name":"Bash","tool_input":{"command":sys.argv[1]}}, ensure_ascii=False))' "$1"
}
N0="$(wc -l < "${LOGD}/decisions.jsonl" | tr -d ' ')"
run auto "$(bashp 'ls -la && echo hi')" bash
N1="$(wc -l < "${LOGD}/decisions.jsonl" | tr -d ' ')"
check "Bash：普通命令 → stdout 空、不留日志" "$(yn [ -z "${OUT}" -a "${N0}" = "${N1}" ])"
T1TASK="按 spec 第 3 节实现缓存层。${AC}${PAD}"
run auto "$(bashp "bash \"/x/delegate/scripts/codex-exec.sh\" --write --model gpt-5.6-terra --effort high \"${T1TASK}\"")" bash
check "Bash：T1 任务按 terra/high 派出 → 建议与实际一致" \
  "$(lastlog 'r["event"] == "codex-dispatch" and r["consistent"] is True and r["suggested"] == {"model": "gpt-5.6-terra", "effort": "high"}')"
run auto "$(bashp "bash /x/codex-exec.sh --model gpt-5.6-terra --effort high -- \"改完后 git push。${AC}${PAD}\" && echo done")" bash
check "Bash：不可逆任务按 T1 派出 → 记为不一致，建议 xhigh" \
  "$(lastlog 'r["consistent"] is False and r["suggested"]["effort"] == "xhigh"')"
check "Bash：任务文本在 && 处截断（取到的是任务，不是后面的 echo done）" \
  "$(lastlog 'r["prompt_chars"] > 50')"
check "Bash：即使 auto 也不改派活命令（stdout 空）" "$(yn [ -z "${OUT}" ])"

# ── v2 Claude pre-dispatch：目录/纯路由在前，此处只验证宿主编码 ──
V2SIMPLE="$(mk $'只读审查配置，禁止修改任何文件。\n验收：报告所有键名。' - nomodel)"
runv2 audit "${V2SIMPLE}"
check "v2 audit：未 pin 的简单任务只记 select，stdout 空" \
  "$(yn [ "${RC}" -eq 0 -a -z "${OUT}" ])"
check "v2 audit：记录 v2 决策且 applied=false" \
  "$(lastlog 'r["routing_version"] == 2 and r["decision"]["action"] == "select" and r["decision"]["target"]["model"] == "haiku" and r["applied"] is False')"
check "v2 audit：记录实际读取目录的来源与内容指纹，不记录路径" \
  "$(lastlog 'r["catalog_identity"] == {"origin": "environment", "sha256": "'"${V2_CATALOG_SHA}"'"}')"
runv2unverified auto "${V2SIMPLE}"
check "v2 auto：未验证宿主不得改写参数，仍只审计" \
  "$(yn [ "${RC}" -eq 0 -a -z "${OUT}" ])"
check "v2 auto：未验证宿主记录 applied=false" \
  "$(lastlog 'r["routing_version"] == 2 and r["decision"]["action"] == "select" and r["applied"] is False and r["host_pre_dispatch_apply"] is False')"
runv2 auto "${V2SIMPLE}"
check "v2 auto：已验证 Claude 宿主选择低成本 haiku" \
  "$(jsonq 'o["hookSpecificOutput"]["hookEventName"] == "PreToolUse" and o["hookSpecificOutput"]["updatedInput"]["model"] == "haiku"')"
check "v2 auto：已验证 Claude 编码不附带 permissionDecision" \
  "$(jsonq '"permissionDecision" not in o["hookSpecificOutput"]')"
check "v2 auto：已验证宿主只改 model，保留所有非路由字段" \
  "$(jsonq 'o["hookSpecificOutput"]["updatedInput"]["description"] == "t" and o["hookSpecificOutput"]["updatedInput"]["prompt"].startswith("只读审查") and o["hookSpecificOutput"]["updatedInput"]["subagent_type"] == "nomodel" and o["hookSpecificOutput"]["updatedInput"]["run_in_background"] is False')"
check "v2 auto：已验证宿主的 updatedInput 输出可审计" \
  "$(lastlog 'r["routing_version"] == 2 and r["decision"]["action"] == "select" and r["host_pre_dispatch_apply"] is True and r["applied"] is True')"
runv2 auto "$(mk $'只读审查配置，禁止修改任何文件。\n验收：报告所有键名。' opus nomodel)"
check "v2 auto：调用显式 model 是 pin，不改写" "$(yn [ -z "${OUT}" ])"
check "v2 auto：pin 留下建议但 target 为空" \
  "$(lastlog 'r["routing_version"] == 2 and r["decision"]["action"] == "pinned" and r["decision"]["target"] is None and r["decision"]["recommended"]["model"] == "haiku" and r["applied"] is False')"
runv2 auto "$(mk $'只读审查配置，禁止修改任何文件。\n验收：报告所有键名。' - executor)"
check "v2 auto：agent frontmatter 的显式 model 也是 pin" "$(yn [ -z "${OUT}" ])"
check "v2 auto：frontmatter pin 不改写" \
  "$(lastlog 'r["routing_version"] == 2 and r["agent_model"] == "sonnet" and r["decision"]["action"] == "pinned" and r["applied"] is False')"
# frontmatter 的 inherit / default 表示「跟随父代理 / 用默认」，不是一次显式选择；
# 当成 pin 会让这类 agent 的派活整类不再被路由，而且是静默的。
runv2 auto "$(mk $'只读审查配置，禁止修改任何文件。\n验收：报告所有键名。' - inheritor)"
check "frontmatter 反：model=inherit 不算 pin，仍按任务选档" \
  "$(jsonq 'o["hookSpecificOutput"]["updatedInput"]["model"] == "haiku"')"
check "frontmatter 反：inherit 不记成 agent_model" \
  "$(lastlog 'r["agent_model"] is None and r["decision"]["action"] == "select"')"
runv2 auto "$(mk $'只读审查配置，禁止修改任何文件。\n验收：报告所有键名。' - defaulter)"
check "frontmatter 反：model=default 同样不算 pin" \
  "$(jsonq 'o["hookSpecificOutput"]["updatedInput"]["model"] == "haiku"')"
# fork 恒继承父代理、插件 agent 的 frontmatter 读不到：判不出是否 pin，auto 也不改写（spec「判不出，不提醒也不改写」）
runv2 auto "$(mk $'只读审查配置，禁止修改任何文件。\n验收：报告所有键名。' - fork)"
check "v2 auto：fork 判不出 pin → 不改写" "$(yn [ -z "${OUT}" ])"
check "v2 auto：fork 记 applied=false" "$(lastlog 'r["routing_version"] == 2 and r["applied"] is False')"
runv2 auto "$(mk $'只读审查配置，禁止修改任何文件。\n验收：报告所有键名。' - myplug:worker)"
check "v2 auto：插件 agent 判不出 pin → 不改写" "$(yn [ -z "${OUT}" ])"
check "v2 auto：插件 agent 记 applied=false" "$(lastlog 'r["routing_version"] == 2 and r["applied"] is False')"

# ── 宿主承认的第三个 pin 来源：CLAUDE_CODE_SUBAGENT_MODEL / _FORCE ──
# Claude Code 2.1.289 读这两个变量决定子代理模型（前者是默认，后者强制并让 model 参数被忽略）。
# 用户设了就是显式选择，auto 下绝不能覆盖。宿主自己把 inherit / default / 空值当作没设。
runv2env() {  # $1=profile $2=payload $3...=额外环境变量赋值
  local profile="$1" payload="$2"; shift 2
  OUT="$(printf '%s' "${payload}" | env HOME="${FAKEHOME}" CLAUDE_PROJECT_DIR="${PROJ}" \
          TIER_GUARD_LOG_DIR="${LOGD}" TIER_GUARD_MODE="${profile}" \
          TIER_GUARD_CONFIG="${V2_ROUTE_CONFIG}" "$@" /bin/bash "${HOOK}" agent)"
  RC=$?
}
runv2env auto "${V2SIMPLE}" CLAUDE_CODE_SUBAGENT_MODEL=opus
check "pin 来源：CLAUDE_CODE_SUBAGENT_MODEL 是 pin，不改写" "$(yn [ "${RC}" -eq 0 -a -z "${OUT}" ])"
check "pin 来源：env pin 记 pinned、requested 取该值、applied=false" \
  "$(lastlog 'r["decision"]["action"] == "pinned" and r["decision"]["requested"]["model"] == "opus" and r["decision"]["requested"]["pinned"] is True and r["applied"] is False')"
runv2env auto "${V2SIMPLE}" CLAUDE_CODE_SUBAGENT_MODEL_FORCE=sonnet
check "pin 来源：CLAUDE_CODE_SUBAGENT_MODEL_FORCE 也是 pin，不改写" "$(yn [ -z "${OUT}" ])"
check "pin 来源：FORCE 记 pinned" \
  "$(lastlog 'r["decision"]["action"] == "pinned" and r["decision"]["requested"]["model"] == "sonnet"')"
runv2env auto "${V2SIMPLE}" CLAUDE_CODE_SUBAGENT_MODEL=inherit
check "pin 来源反：env=inherit 不算 pin（宿主自己也忽略）" \
  "$(jsonq 'o["hookSpecificOutput"]["updatedInput"]["model"] == "haiku"')"
runv2env auto "${V2SIMPLE}" CLAUDE_CODE_SUBAGENT_MODEL=
check "pin 来源反：env 为空串不算 pin" \
  "$(jsonq 'o["hookSpecificOutput"]["updatedInput"]["model"] == "haiku"')"
runv2env auto "$(mk $'只读审查配置，禁止修改任何文件。\n验收：报告所有键名。' opus nomodel)" CLAUDE_CODE_SUBAGENT_MODEL=sonnet
check "pin 来源：tool_input.model 优先于 env" \
  "$(lastlog 'r["decision"]["requested"]["model"] == "opus"')"
runv2 auto '{"tool_name":"Agent","tool_input":{"subagent_type":"nomodel"}}'
check "v2：缺 prompt → 退出 0、stdout 空且不应用" "$(yn [ "${RC}" -eq 0 -a -z "${OUT}" ])"
check "v2：缺 prompt → fallback 可审计" \
  "$(lastlog 'r["routing_version"] == 2 and r["decision"]["action"] == "pass" and bool(r["decision"]["fallback"]) and r["applied"] is False')"

# ── v2 SubagentStop：只记宿主 transcript 里的实际模型，永不输出 ──
subtr() {  # $1=文件 $2=toolUseId $3=实际模型
  mkdir -p "$(dirname "$1")"
  python3 - "$@" <<'PY'
import json, sys
f, tid, model = sys.argv[1:4]
with open(f, "w", encoding="utf-8") as fh:
    fh.write(json.dumps({"type": "user", "message": {"role": "user", "content": "子任务原文 SECRET_PROMPT_TEXT"}}, ensure_ascii=False) + "\n")
    # 两条 assistant：模型取第一条（同一子代理内不变），usage 必须累加而不是只取第一条
    fh.write(json.dumps({"type": "assistant", "message": {"role": "assistant", "model": model,
        "content": [{"type": "text", "text": "ok"}],
        "usage": {"input_tokens": 10, "cache_creation_input_tokens": 100,
                  "cache_read_input_tokens": 1000, "output_tokens": 5}}}) + "\n")
    fh.write(json.dumps({"type": "assistant", "message": {"role": "assistant", "model": model,
        "content": [{"type": "text", "text": "ok2"}],
        "usage": {"input_tokens": 1, "cache_creation_input_tokens": 20,
                  "cache_read_input_tokens": 300, "output_tokens": 7}}}) + "\n")
json.dump({"agentType": "general-purpose", "toolUseId": tid}, open(f[:-len(".jsonl")] + ".meta.json", "w", encoding="utf-8"))
PY
}
stopp() { python3 -c 'import json,sys; print(json.dumps({"session_id":"s","hook_event_name":"SubagentStop","agent_transcript_path":sys.argv[1],"last_assistant_message":"ok"}))' "$1"; }
c_silent() { [ "${RC}" -eq 0 ] && [ -z "${OUT}" ]; }
subtr "${TMP}/sub/agent-a.jsonl" u claude-haiku-4-5
runv2 audit "$(stopp "${TMP}/sub/agent-a.jsonl")" subagent-stop
check "v2 SubagentStop：退出 0、stdout 空" "$(yn c_silent)"
check "v2 SubagentStop：按 meta 的 toolUseId 记录 transcript 里的实际模型，effort 未知即 None" \
  "$(lastlog 'r["event"] == "subagent-stop" and r["routing_version"] == 2 and r["tool_use_id"] == "u" and r["actual_execution"] == {"model": "claude-haiku-4-5", "reasoning_effort": None}')"
check "v2 SubagentStop：不记子任务原文、不伪造路由决策" \
  "$(lastlog '"SECRET_PROMPT_TEXT" not in json.dumps(r, ensure_ascii=False) and "decision" not in r and len(r["prompt_sha256"]) == 64')"
# 宿主对某些子代理种类根本不写 transcript（实测：同一会话里 Agent 工具派的有、其它没有，
# 且全盘搜不到）。那是正常的宿主状况，不是守卫出错：记录必须保留、且不得占用 fallback 这个
# 诊断位——否则 fallback 会被这类事件淹没，真正的守卫异常就看不见了。
runv2 audit "$(stopp "${TMP}/sub/missing.jsonl")" subagent-stop
check "v2 SubagentStop：transcript 不存在 → 退出 0、stdout 空" "$(yn c_silent)"
check "v2 SubagentStop：transcript 不存在 → 记录保留，不记成 fallback" \
  "$(lastlog 'r["event"] == "subagent-stop" and "fallback" not in r and r["transcript_status"] == "missing"')"
check "v2 SubagentStop：transcript 不存在 → 仍保留 session_id 与路径，可归因" \
  "$(lastlog 'r["session_id"] == "s" and r["agent_transcript_path"].endswith("missing.jsonl") and r["routing_version"] == 2')"
check "v2 SubagentStop：transcript 不存在 → 实际执行记为未知，不伪造" \
  "$(lastlog 'r["actual_execution"] is None and r["tool_use_id"] is None')"
runv2 audit "$(stopp "${TMP}/sub/agent-a.jsonl")" subagent-stop
check "v2 SubagentStop：读到 transcript 时标记为 ok（与 missing 可区分）" \
  "$(lastlog 'r["transcript_status"] == "ok" and r["actual_execution"]["model"] == "claude-haiku-4-5"')"
# 宿主在 transcript 里给了 usage，tier-guard 之前没取。记原始 token 数、不记成本：
# 价格会变且按账号不同，把价格表写进仓库就是一个会过期却被当成事实的东西。
check "v2 SubagentStop：记录宿主给出的 token 用量（跨多条 assistant 累加）" \
  "$(lastlog 'r["usage"] == {"input_tokens": 11, "cache_creation_input_tokens": 120, "cache_read_input_tokens": 1300, "output_tokens": 12}')"
check "v2 SubagentStop：usage 与 actual_execution 并列，不改后者的形状" \
  "$(lastlog 'set(r["actual_execution"]) == {"model", "reasoning_effort"}')"
runv2 audit "$(stopp "${TMP}/sub/missing.jsonl")" subagent-stop
check "v2 SubagentStop：读不到 transcript 时 usage 记为未知，不伪造 0" \
  "$(lastlog 'r["transcript_status"] == "missing" and r["usage"] is None')"
# 另一条路径：transcript 读得到，但宿主一条 usage 都没给。同样记未知 ——
# 一串 0 会被读成「真的没花 token」，比缺字段更有害。
python3 - "${TMP}/sub/nousage.jsonl" <<'PY2'
import json, sys
f = sys.argv[1]
with open(f, "w", encoding="utf-8") as fh:
    fh.write(json.dumps({"type": "user", "message": {"role": "user", "content": "x"}}) + "\n")
    fh.write(json.dumps({"type": "assistant", "message": {"role": "assistant",
        "model": "claude-haiku-4-5", "content": []}}) + "\n")
json.dump({"toolUseId": "u-nousage"}, open(f[:-len(".jsonl")] + ".meta.json", "w", encoding="utf-8"))
PY2
runv2 audit "$(stopp "${TMP}/sub/nousage.jsonl")" subagent-stop
check "v2 SubagentStop：transcript 有但宿主没给用量 → usage 记未知，不是一串 0" \
  "$(lastlog 'r["transcript_status"] == "ok" and r["actual_execution"]["model"] == "claude-haiku-4-5" and r["usage"] is None')"
# 宿主把同一条 assistant 消息（同一 message.id）写成多行：每个 content block 一行，流式过程中还会再写。
# 用量必须按 id 去重，否则 input / 缓存按行数成倍虚高（实测 109 份 transcript：input 1.97×）。
iddup() {  # $1=文件名 $2..=每行一个 "id|input|cache_write|cache_read|output"（id 为 - 表示没有 id）
  local f="${TMP}/sub/$1"; shift
  python3 - "${f}" "$@" <<'PY'
import json, sys
f, specs = sys.argv[1], sys.argv[2:]
with open(f, "w", encoding="utf-8") as fh:
    fh.write(json.dumps({"type": "user", "message": {"role": "user", "content": "x"}}) + "\n")
    for spec in specs:
        mid, i, cw, cr, o = spec.split("|")
        msg = {"role": "assistant", "model": "claude-haiku-4-5", "content": [],
               "usage": {"input_tokens": int(i), "cache_creation_input_tokens": int(cw),
                         "cache_read_input_tokens": int(cr), "output_tokens": int(o)}}
        if mid != "-":
            msg["id"] = mid
        fh.write(json.dumps({"type": "assistant", "message": msg}) + "\n")
json.dump({"toolUseId": "u-" + f}, open(f[:-len(".jsonl")] + ".meta.json", "w", encoding="utf-8"))
PY
}
iddup dup-same.jsonl "m1|10|100|1000|5" "m1|10|100|1000|5"
runv2 audit "$(stopp "${TMP}/sub/dup-same.jsonl")" subagent-stop
check "usage-dedup：同一 message.id 写两行、用量相同 → 只算一次" \
  "$(lastlog 'r["usage"] == {"input_tokens": 10, "cache_creation_input_tokens": 100, "cache_read_input_tokens": 1000, "output_tokens": 5}')"
iddup dup-grow.jsonl "m1|10|100|1000|10" "m1|10|100|1000|40"
runv2 audit "$(stopp "${TMP}/sub/dup-grow.jsonl")" subagent-stop
check "usage-dedup：同一 id 流式增长（output 10 → 40）→ 取 40，不是 50 也不是 10" \
  "$(lastlog 'r["usage"]["output_tokens"] == 40 and r["usage"]["input_tokens"] == 10')"
iddup dup-grow-rev.jsonl "m1|10|100|1000|40" "m1|10|100|1000|10"
runv2 audit "$(stopp "${TMP}/sub/dup-grow-rev.jsonl")" subagent-stop
check "usage-dedup：较大的行排在前面也取最大（不是取最后一行）" "$(lastlog 'r["usage"]["output_tokens"] == 40')"
iddup dup-two.jsonl "m1|10|100|1000|5" "m2|1|20|300|7"
runv2 audit "$(stopp "${TMP}/sub/dup-two.jsonl")" subagent-stop
check "usage-dedup：两个不同 id → 相加" \
  "$(lastlog 'r["usage"] == {"input_tokens": 11, "cache_creation_input_tokens": 120, "cache_read_input_tokens": 1300, "output_tokens": 12}')"
iddup dup-anon.jsonl "-|10|100|1000|5" "-|10|100|1000|5"
runv2 audit "$(stopp "${TMP}/sub/dup-anon.jsonl")" subagent-stop
check "usage-dedup：两行都没有 id（用量相同）→ 各算各的，不合并" \
  "$(lastlog 'r["usage"] == {"input_tokens": 20, "cache_creation_input_tokens": 200, "cache_read_input_tokens": 2000, "output_tokens": 10}')"
check "usage-dedup：有用量时记 usage_basis=message-id-dedup" "$(lastlog 'r["usage_basis"] == "message-id-dedup"')"
runv2 audit "$(stopp "${TMP}/sub/nousage.jsonl")" subagent-stop
check "usage-dedup：用量未知（None）时不写 usage_basis" "$(lastlog 'r["usage"] is None and "usage_basis" not in r')"
runv2 audit "$(stopp "${TMP}/sub/missing.jsonl")" subagent-stop
check "usage-dedup：transcript 不存在时不写 usage_basis" "$(lastlog 'r["transcript_status"] == "missing" and "usage_basis" not in r')"
# env=off 会被薄壳快速路径拦下，这里走状态文件，才真正测到 python 这一侧
OFFD="${TMP}/v2-off"; mkdir -p "${OFFD}"; printf 'off\n' > "${OFFD}/mode"
printf '%s' "$(stopp "${TMP}/sub/agent-a.jsonl")" | env -u TIER_GUARD_MODE HOME="${FAKEHOME}" TIER_GUARD_LOG_DIR="${OFFD}" \
  TIER_GUARD_CONFIG="${ROOT}/config/routing.catalog.v2.json" /bin/bash "${HOOK}" subagent-stop >/dev/null
check "v2 SubagentStop：状态文件 off → 不留日志" "$(yn [ ! -e "${OFFD}/decisions.jsonl" ])"
# Phase 9 D7：off 下路由走了兜底（空 prompt 等）时，决定里没有 profile，旧代码会把它记进日志
printf '%s' "$(mk "" - nomodel)" | env -u TIER_GUARD_MODE HOME="${FAKEHOME}" TIER_GUARD_LOG_DIR="${OFFD}" \
  TIER_GUARD_CONFIG="${ROOT}/config/routing.catalog.v2.json" /bin/bash "${HOOK}" agent >/dev/null
check "v2 Agent：状态文件 off + 路由兜底 → 仍不留日志" "$(yn [ ! -e "${OFFD}/decisions.jsonl" ])"

# ── v2 主代理预路由提醒（Task 10）：判据在 route_decide.nudge_decision，这里只测薄壳编码 ──
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
        return text.startswith(rd.NUDGE_REMIND_TEXT) and rd.catalog_summary(cfg, "claude-code") in text
    def deny_ok(text):
        return text.startswith(rd.NUDGE_DENY_TEXT) and rd.catalog_summary(cfg, "claude-code") in text
    def all_models_ok(text):
        own = {c["model"] for c in rd.catalog_candidates(cfg, "claude-code")}
        other = {c["model"] for c in rd.catalog_candidates(cfg, "codex-cli")}
        return all(m in text for m in own) and not any(m in text for m in other)
    print("yes" if eval(sys.argv[1]) else "no")
except Exception:
    print("no")
PY
}
NUDGE_TASK=$'只读审查配置，禁止修改任何文件。\n验收：报告所有键名。'

rm -rf "${NLOGD}"
runnudgeprod audit "$(mksess s0 "${NUDGE_TASK}" - nomodel)"
check "nudge：生产目录 claude-code.dispatch_nudge=true，audit + 未 pin → 只提醒（不 deny、不改写）" \
  "$(nudgeq 'remind_ok(o["hookSpecificOutput"]["additionalContext"]) and "permissionDecision" not in o["hookSpecificOutput"] and "updatedInput" not in o["hookSpecificOutput"]' "${ROOT}/config/routing.catalog.v2.json")"
check "nudge：生产目录 audit 提醒 → 记 nudge=reminded" "$(lastnudgelog 'r["nudge"] == "reminded"')"
runnudgewith audit "$(mksess s0off "${NUDGE_TASK}" - nomodel)" "${V2_ROUTE_CONFIG}" "${NLOGD}"
check "nudge：关掉 claude-code.dispatch_nudge 的目录，audit + 未 pin → stdout 空" "$(yn [ "${RC}" -eq 0 -a -z "${OUT}" ])"
check "nudge：闸门关闭 → 记 nudge=none" "$(lastnudgelog 'r["nudge"] == "none"')"

runnudge audit "$(mksess s1 "${NUDGE_TASK}" - nomodel)"
check "nudge：gate 开 + audit + 未 pin → stdout 只有 additionalContext（常量开头 + 候选摘要）" \
  "$(nudgeq 'o["hookSpecificOutput"]["hookEventName"] == "PreToolUse" and remind_ok(o["hookSpecificOutput"]["additionalContext"]) and "updatedInput" not in o["hookSpecificOutput"] and "permissionDecision" not in o["hookSpecificOutput"]')"
check "nudge：audit 提醒记 nudge=reminded，applied=false" \
  "$(lastnudgelog 'r["nudge"] == "reminded" and r["applied"] is False')"
check "nudge：提醒文案含 claude-code 全部候选 model，不含 codex-cli 候选 model" \
  "$(nudgeq 'all_models_ok(o["hookSpecificOutput"]["additionalContext"])')"

runnudge audit "$(mksess s2 "${NUDGE_TASK}" sonnet nomodel)"
check "nudge：gate 开 + audit：显式 model 是 pin → stdout 空" "$(yn [ -z "${OUT}" ])"
check "nudge：显式 model pin → 记 nudge=none" "$(lastnudgelog 'r["nudge"] == "none"')"
runnudge audit "$(mksess s3 "${NUDGE_TASK}" - executor)"
check "nudge：gate 开 + audit：agent frontmatter 的 model 是 pin → stdout 空" "$(yn [ -z "${OUT}" ])"
check "nudge：frontmatter pin → 记 nudge=none" "$(lastnudgelog 'r["nudge"] == "none"')"
runnudge audit "$(mksess s4 "${NUDGE_TASK}" - plugin:x)"
check "nudge：gate 开 + audit：带冒号的插件 agent 判不出 pin → stdout 空" "$(yn [ -z "${OUT}" ])"
check "nudge：插件 agent 判不出 → 记 nudge=none" "$(lastnudgelog 'r["nudge"] == "none"')"
runnudge audit "$(mksess s5 "${NUDGE_TASK}" - fork)"
check "nudge：gate 开 + audit：fork 判不出 pin → stdout 空" "$(yn [ -z "${OUT}" ])"
check "nudge：fork → 记 nudge=none" "$(lastnudgelog 'r["nudge"] == "none"')"

runnudge auto "$(mksess A "${NUDGE_TASK}" - nomodel)"
check "nudge：gate 开 + auto + session A 第一次未 pin → deny（原因以 route_decide 的 deny 常量开头 + 候选摘要）" \
  "$(nudgeq 'o["hookSpecificOutput"]["hookEventName"] == "PreToolUse" and o["hookSpecificOutput"]["permissionDecision"] == "deny" and deny_ok(o["hookSpecificOutput"]["permissionDecisionReason"]) and "updatedInput" not in o["hookSpecificOutput"]')"
check "nudge：deny 记 nudge=denied，applied=false" "$(lastnudgelog 'r["nudge"] == "denied" and r["applied"] is False')"

runnudge auto "$(mksess A "${NUDGE_TASK}" - nomodel)"
check "nudge：同一 session A 第二次未 pin → 不再 deny，updatedInput 与 additionalContext 同框" \
  "$(nudgeq '"permissionDecision" not in o["hookSpecificOutput"] and o["hookSpecificOutput"]["updatedInput"]["model"] == "haiku" and remind_ok(o["hookSpecificOutput"]["additionalContext"])')"
check "nudge：session A 第二次记 nudge=reminded" "$(lastnudgelog 'r["nudge"] == "reminded"')"

runnudge auto "$(mksess B "${NUDGE_TASK}" - nomodel)"
check "nudge：不同 session B 第一次未 pin → 仍然 deny（按 session 各算一次）" \
  "$(nudgeq 'o["hookSpecificOutput"]["permissionDecision"] == "deny"')"
check "nudge：session B 第一次记 nudge=denied" "$(lastnudgelog 'r["nudge"] == "denied"')"

runnudge auto "$(mksess - "${NUDGE_TASK}" - nomodel)"
check "nudge：auto 但 payload 没 session_id → 只 remind，不 deny" \
  "$(nudgeq '"permissionDecision" not in o["hookSpecificOutput"] and remind_ok(o["hookSpecificOutput"]["additionalContext"])')"
check "nudge：无 session_id → 记 nudge=reminded" "$(lastnudgelog 'r["nudge"] == "reminded"')"

# env=off 会被薄壳快速路径拦下，这里走状态文件，才真正测到 python 这一侧
NOFFD="${TMP}/nudge-off"; mkdir -p "${NOFFD}"; printf 'off\n' > "${NOFFD}/mode"
OUT="$(printf '%s' "$(mksess C "${NUDGE_TASK}" - nomodel)" | env -u TIER_GUARD_MODE HOME="${FAKEHOME}" CLAUDE_PROJECT_DIR="${PROJ}" \
        TIER_GUARD_LOG_DIR="${NOFFD}" TIER_GUARD_CONFIG="${V2_NUDGE_CONFIG}" /bin/bash "${HOOK}" agent)"; RC=$?
check "nudge：状态文件 off → 退出 0、stdout 空" "$(yn [ "${RC}" -eq 0 -a -z "${OUT}" ])"
check "nudge：状态文件 off → 不留日志" "$(yn [ ! -e "${NOFFD}/decisions.jsonl" ])"

# ── deny 标记：目录名 64-hex，不含原始 session id，文件本身是空标记 ──
check "nudge：deny 标记文件名都是 64 位十六进制，且不含原始 session id" \
  "$(python3 - "${NLOGD}/nudge-denied" <<'PY'
import os, re, sys
d = sys.argv[1]
names = os.listdir(d)
raw_ids = ["A", "B"]
ok = bool(names) and all(re.fullmatch(r"[0-9a-f]{64}", n) for n in names) \
    and not any(rid in n for n in names for rid in raw_ids)
print("yes" if ok else "no")
PY
)"
check "nudge：deny 标记文件本身为空（只当存在性标记用）" \
  "$(python3 - "${NLOGD}/nudge-denied" <<'PY'
import os, sys
d = sys.argv[1]
print("yes" if all(os.path.getsize(os.path.join(d, n)) == 0 for n in os.listdir(d)) else "no")
PY
)"

# ── 标记写不进去（nudge-denied 被占成普通文件）→ 降级成 remind，不能真 deny，退出仍是 0 ──
NLOGD_FAIL="${TMP}/nudge-log-fail"; mkdir -p "${NLOGD_FAIL}"
: > "${NLOGD_FAIL}/nudge-denied"
runnudgewith auto "$(mksess D "${NUDGE_TASK}" - nomodel)" "${V2_NUDGE_CONFIG}" "${NLOGD_FAIL}"
check "nudge：标记目录被占用 → 退出 0" "$(yn [ "${RC}" -eq 0 ])"
check "nudge：标记写不进去 → 降级为 remind，不 deny，仍带候选摘要" \
  "$(nudgeq '"permissionDecision" not in o["hookSpecificOutput"] and remind_ok(o["hookSpecificOutput"]["additionalContext"])')"

# ── prompt 原文不出现在 remind / deny 的 stdout 或日志里 ──
SECRET_TOKEN="NUDGE_SECRET_TOKEN_9f3a1c"
out_lacks_token() { case "${OUT}" in *"${SECRET_TOKEN}"*) return 1 ;; esac; return 0; }
runnudge audit "$(mksess se1 "只读检查一遍。${SECRET_TOKEN}" - nomodel)"
check "nudge：remind 的 stdout 不含 prompt 原文" "$(yn out_lacks_token)"
check "nudge：remind 的日志不含 prompt 原文" "$(lastnudgelog '"'"${SECRET_TOKEN}"'" not in json.dumps(r, ensure_ascii=False)')"
runnudge auto "$(mksess se2 "只读检查一遍。${SECRET_TOKEN}" - nomodel)"
check "nudge：deny 的 stdout 不含 prompt 原文" "$(yn out_lacks_token)"
check "nudge：deny 的日志不含 prompt 原文" "$(lastnudgelog '"'"${SECRET_TOKEN}"'" not in json.dumps(r, ensure_ascii=False)')"

# ── guard（默认 profile，Task 14）：拦一次、之后提醒；pre_dispatch_apply=true 也从不改写参数 ──
runnudge guard "$(mksess G1 "${NUDGE_TASK}" - nomodel)"
check "guard：gate 开 + 新会话未 pin → deny（常量开头 + 候选摘要），不带 updatedInput" \
  "$(nudgeq 'o["hookSpecificOutput"]["permissionDecision"] == "deny" and deny_ok(o["hookSpecificOutput"]["permissionDecisionReason"]) and "updatedInput" not in o["hookSpecificOutput"]')"
check "guard：deny 记 profile=guard、nudge=denied、applied=false" \
  "$(lastnudgelog 'r["decision"]["profile"] == "guard" and r["nudge"] == "denied" and r["applied"] is False')"
runnudge guard "$(mksess G1 "${NUDGE_TASK}" - nomodel)"
check "guard：同会话第二次未 pin → 只提醒；claude-code pre_dispatch_apply=true 也不带 updatedInput" \
  "$(nudgeq '"permissionDecision" not in o["hookSpecificOutput"] and "updatedInput" not in o["hookSpecificOutput"] and remind_ok(o["hookSpecificOutput"]["additionalContext"])')"
check "guard：第二次记 nudge=reminded、applied=false" "$(lastnudgelog 'r["nudge"] == "reminded" and r["applied"] is False')"
runnudgeprod guard "$(mksess G2 "${NUDGE_TASK}" - nomodel)"
check "guard：生产目录（claude-code.dispatch_nudge=true）新会话未 pin → deny，不带 updatedInput" \
  "$(nudgeq 'o["hookSpecificOutput"]["permissionDecision"] == "deny" and deny_ok(o["hookSpecificOutput"]["permissionDecisionReason"]) and "updatedInput" not in o["hookSpecificOutput"]' "${ROOT}/config/routing.catalog.v2.json")"
runnudgewith guard "$(mksess G3 "${NUDGE_TASK}" - nomodel)" "${V2_ROUTE_CONFIG}" "${NLOGD}"
check "guard：关掉 claude-code.dispatch_nudge 的目录 → 退出 0、stdout 空（不改写、不提醒）" "$(yn [ "${RC}" -eq 0 -a -z "${OUT}" ])"

# ── 并发：同一轮并行派出的多个 Agent 会并发跑 hook，都读到「没 deny 过」──
# 用 python 把这个时序固定下来（已 deny 检查恒为 False），只有抢到 O_EXCL 标记的那次能 deny。
NRACED="${TMP}/nudge-race"
nudge_race() {
  env HOME="${FAKEHOME}" CLAUDE_PROJECT_DIR="${PROJ}" TIER_GUARD_LOG_DIR="${NRACED}" \
    python3 - "${ROOT}/hooks" "${V2_NUDGE_CONFIG}" "$(mksess R "${NUDGE_TASK}" - nomodel)" <<'PY'
import json, sys
sys.path.insert(0, sys.argv[1])
import claude_hook as ch
import route_decide as rd
import tier_state
cfg, sha = rd.load_config_with_fingerprint(sys.argv[2])
payload = json.loads(sys.argv[3])
tier_state.nudge_already_denied = lambda session_id: False
outs = [ch.on_agent_v2(payload, cfg, "auto", {"origin": "environment", "sha256": sha})[1] for _ in range(3)]
hso = [(o or {}).get("hookSpecificOutput", {}) for o in outs]
denies = sum(1 for h in hso if h.get("permissionDecision") == "deny")
reminds = sum(1 for h in hso if h.get("additionalContext", "").startswith(rd.NUDGE_REMIND_TEXT) and "permissionDecision" not in h)
print("yes" if denies == 1 and reminds == 2 else "no")
PY
}
check "nudge：并发抢标记 → 同一会话 3 次只有 1 次 deny，其余 2 次只提醒" "$(nudge_race)"

# ── Task 18：上游档位字段进审计日志，且日志不漏 reason / 任务原文 ──
# 独立日志目录：「整个目录里找不到」才有意义，不能和别的断言写进同一个目录。
TG18LOG="${TMP}/tg18-log"; rm -rf "${TG18LOG}"
TG18_REASON="TG18-REASON-SENTINEL-7f3a"; TG18_TASK="TG18-TASK-SENTINEL-c91e"
run18() {  # $1=profile $2=payload → OUT / RC（日志写进 TG18LOG）
  OUT="$(printf '%s' "$2" | env HOME="${FAKEHOME}" CLAUDE_PROJECT_DIR="${PROJ}" \
          TIER_GUARD_LOG_DIR="${TG18LOG}" TIER_GUARD_MODE="$1" \
          TIER_GUARD_CONFIG="${V2_ROUTE_CONFIG}" /bin/bash "${HOOK}" agent)"
  RC=$?
}
rec18() {  # $1=下标（-2 倒数第二条 / -1 最后一条）$2=python 表达式（r = 该条日志）
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
run18 guard "$(mk "${TG18_TASK} 只读审查配置，禁止修改任何文件。"$'\n验收：报告所有键名。\n'"<!-- tier-guard: tier=L2 reason=${TG18_REASON} -->" - nomodel)"
check "tier18：合法标记 → 记录里 tier_source=upstream，upstream_tier 已接受且 reason_present=true" \
  "$(rec18 -1 'r["decision"]["tier_source"] == "upstream" and r["decision"]["upstream_tier"]["status"] == "accepted" and r["decision"]["upstream_tier"]["tier"] == "L2" and r["decision"]["upstream_tier"]["reason_present"] is True')"
check "tier18：合法标记 → 记录里只有 reason 的 sha256，且没有 tier_conflict 键" \
  "$(rec18 -1 'len(r["decision"]["upstream_tier"]["reason_sha256"]) == 64 and "tier_conflict" not in r["decision"]')"
run18 guard "$(mk "${TG18_TASK} 完成后 git push 到 origin。"$'\n验收：远端分支可见。\n'"<!-- tier-guard: tier=L1 reason=${TG18_REASON} -->" - nomodel)"
check "tier18：伪造 tier=L1 的不可逆任务 → 记录 tier_conflict={upstream:L1,floor:L3}" \
  "$(rec18 -1 'r["decision"]["tier_conflict"] == {"upstream": "L1", "floor": "L3"}')"
check "tier18：伪造 tier=L1 的不可逆任务 → 记录 tier_source=floor，目标是 opus" \
  "$(rec18 -1 'r["decision"]["tier_source"] == "floor" and r["decision"]["target"]["model"] == "opus"')"
check "tier18：日志目录里找不到 reason 原文和任务原文" "$(logdir_free_of "${TG18_REASON}" "${TG18_TASK}")"

# ── Task 20：L2 第二次失败 → 收回 deny / remind（判据在 route_decide.reclaim_decision）──
# 独立日志目录；闸门开的目录用 V2_NUDGE_CONFIG（claude-code.dispatch_nudge=true，pre_dispatch_apply=true）。
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
r20_deny_json='o["hookSpecificOutput"]["hookEventName"] == "PreToolUse" and o["hookSpecificOutput"]["permissionDecision"] == "deny" and "第二次失败" in o["hookSpecificOutput"]["permissionDecisionReason"] and "2 次" in o["hookSpecificOutput"]["permissionDecisionReason"] and "重新界定" in o["hookSpecificOutput"]["permissionDecisionReason"] and "updatedInput" not in o["hookSpecificOutput"]'
reason_lacks_sentinels() { case "${OUT}" in *TG20-*) return 1 ;; esac; return 0; }
runnudgewith guard "$(mksess R20S "${R20_TASK}" - nomodel)" "${V2_NUDGE_CONFIG}" "${TG20LOG}"
check "tier20：guard + L2 失败 2 次 → deny，原因点明第二次失败、带失败计数、要求重新界定，不带 updatedInput" "$(jsonq "${r20_deny_json}")"
check "tier20：收回 deny 的输出不含任务原文和 reason 原文" "$(yn reason_lacks_sentinels)"
check "tier20：收回 deny 记 reclaim_output=deny、nudge=none、applied=false" \
  "$(rec20 'r["reclaim_output"] == "deny" and r["nudge"] == "none" and r["applied"] is False and r["decision"]["reclaim"] == {"tier": "L2", "consecutive_failures": 2}')"
check "tier20：收回 deny 没有创建 nudge 标记（既不检查也不消耗）" "$(yn [ ! -e "${TG20LOG}/nudge-denied" ])"
runnudgewith guard "$(mksess R20S "${R20_TASK}" - nomodel)" "${V2_NUDGE_CONFIG}" "${TG20LOG}"
check "tier20：同会话带同样失败计数重派 → 再次收回（不受每会话一次限制）" "$(jsonq "${r20_deny_json}")"
runnudgewith guard "$(mksess R20S "${NUDGE_TASK}" - nomodel)" "${V2_NUDGE_CONFIG}" "${TG20LOG}"
check "tier20：收回之后同会话的普通未 pin 派活仍拿到第一次 nudge deny" \
  "$(jsonq 'o["hookSpecificOutput"]["permissionDecision"] == "deny" and "第二次失败" not in o["hookSpecificOutput"]["permissionDecisionReason"]')"
check "tier20：该次记 nudge=denied，且没有 reclaim_output" "$(rec20 'r["nudge"] == "denied" and "reclaim_output" not in r')"
runnudgewith auto "$(mksess R20A "${R20_TASK}" - nomodel)" "${V2_NUDGE_CONFIG}" "${TG20LOG}"
check "tier20：auto + pre_dispatch_apply=true → 仍是 deny，不带 updatedInput" "$(jsonq "${r20_deny_json}")"
check "tier20：auto 的收回 deny 记 host_pre_dispatch_apply=true、reclaim_output=deny、applied=false" \
  "$(rec20 'r["host_pre_dispatch_apply"] is True and r["reclaim_output"] == "deny" and r["applied"] is False')"
runnudgewith guard "$(mksess - "${R20_TASK}" - nomodel)" "${V2_NUDGE_CONFIG}" "${TG20LOG}"
check "tier20：payload 没有 session_id → 收回 deny 照样成立（不依赖 session_id）" "$(jsonq "${r20_deny_json}")"
runnudgewith audit "$(mksess R20U "${R20_TASK}" - nomodel)" "${V2_NUDGE_CONFIG}" "${TG20LOG}"
check "tier20：audit → 只提醒（additionalContext），不 deny、不改写" \
  "$(jsonq '"第二次失败" in o["hookSpecificOutput"]["additionalContext"] and "permissionDecision" not in o["hookSpecificOutput"] and "updatedInput" not in o["hookSpecificOutput"]')"
check "tier20：audit 收回提醒记 reclaim_output=remind、nudge=none" "$(rec20 'r["reclaim_output"] == "remind" and r["nudge"] == "none"')"
runnudgewith guard "$(mksess R20P "${R20_TASK}" sonnet nomodel)" "${V2_NUDGE_CONFIG}" "${TG20LOG}"
check "tier20：pin 的派活 → 不收回、stdout 空" "$(yn [ "${RC}" -eq 0 -a -z "${OUT}" ])"
check "tier20：pin 的派活只记录：决策里有 reclaim，但没有 reclaim_output" "$(rec20 '"reclaim" in r["decision"] and "reclaim_output" not in r')"
runnudgewith guard "$(mksess R20G "${R20_TASK}" - nomodel)" "${V2_ROUTE_CONFIG}" "${TG20LOG}"
check "tier20：dispatch_nudge 闸门关闭 → 不收回、stdout 空" "$(yn [ "${RC}" -eq 0 -a -z "${OUT}" ])"
check "tier20：闸门关闭只记录：决策里有 reclaim，但没有 reclaim_output" "$(rec20 '"reclaim" in r["decision"] and "reclaim_output" not in r')"
TG20OFF="${TMP}/tg20-off"; mkdir -p "${TG20OFF}"; printf 'off\n' > "${TG20OFF}/mode"
OUT="$(printf '%s' "$(mksess R20O "${R20_TASK}" - nomodel)" | env -u TIER_GUARD_MODE HOME="${FAKEHOME}" CLAUDE_PROJECT_DIR="${PROJ}" \
        TIER_GUARD_LOG_DIR="${TG20OFF}" TIER_GUARD_CONFIG="${V2_NUDGE_CONFIG}" /bin/bash "${HOOK}" agent)"; RC=$?
check "tier20：状态文件 off → 不收回、stdout 空、不留日志" "$(yn [ "${RC}" -eq 0 -a -z "${OUT}" -a ! -e "${TG20OFF}/decisions.jsonl" ])"
check "tier20：收回全过程的日志目录里找不到任务原文和 reason 原文" "$(dir_free_of "${TG20LOG}" "${TG20_REASON}" "${TG20_TASK}")"

# ── 性能：单次 < 100ms（实测中位数）──
MS="$(python3 - "${HOOK}" "${IRR}" "${FAKEHOME}" "${LOGD}" <<'PY'
import os, subprocess, sys, time
hook, payload, home, logd = sys.argv[1:5]
env = dict(os.environ, HOME=home, TIER_GUARD_LOG_DIR=logd, TIER_GUARD_MODE="auto",
           TIER_GUARD_CONFIG=os.path.join(os.path.dirname(os.path.dirname(hook)), "config", "routing.default.json"))
ts = []
for _ in range(15):
    t = time.perf_counter()
    subprocess.run(["/bin/bash", hook, "agent"], input=payload, capture_output=True, text=True, env=env)
    ts.append((time.perf_counter() - t) * 1000)
print(int(sorted(ts)[len(ts) // 2]))
PY
)"
check "性能：单次执行中位 ${MS}ms < 100ms" "$(yn [ "${MS}" -lt 100 ])"

echo ""
echo "  总计 ${PASS} 通过 / ${FAIL} 失败"
[ "${PASS}" -gt 0 ] && [ "${FAIL}" -eq 0 ]
