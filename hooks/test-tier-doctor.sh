#!/bin/bash
# /tier-doctor 的回归：只报告可观察到的事实，绝不把“没有日志”伪装成“hook 未安装”。
set -uo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TMP="$(mktemp -d)"
trap 'rm -rf "${TMP}"' EXIT
PASS=0; FAIL=0
check() { if [ "$2" = yes ]; then printf '  ✅ %s\n' "$1"; PASS=$((PASS+1)); else printf '  ❌ %s\n' "$1"; FAIL=$((FAIL+1)); fi; }
yn() { if "$@"; then echo yes; else echo no; fi; }
has() { case "$1" in *"$2"*) return 0 ;; *) return 1 ;; esac; }
doctor() { HOME="${TMP}/home" python3 "${ROOT}/hooks/tier_doctor.py" --data "$1"; }

EMPTY="${TMP}/empty"
OUT="$(doctor "${EMPTY}")"; RC=$?
empty_ok() {
  [ "${RC}" -eq 0 ] && has "${OUT}" "Codex spawn hook 记录：0" && \
    has "${OUT}" "不能区分未安装、未信任或调用绕过 hook" && \
    has "${OUT}" "先在 Codex CLI 用 /hooks 审核当前 hook 信任记录" && \
    has "${OUT}" "协作代理 API 不会进入 Codex PreToolUse hook"
}
check "空日志：给出正确的桌面信任与原生派活边界，不猜测根因" "$(yn empty_ok)"

OUT="$(HOME="${TMP}/home" python3 "${ROOT}/hooks/tier_doctor.py")"; RC=$?
default_dir_ok() {
  [ "${RC}" -eq 0 ] && has "${OUT}" "调用进程未提供数据目录" && \
    has "${OUT}" "显式传 --data"
}
check "默认目录：提醒普通 shell 显式指定宿主数据目录" "$(yn default_dir_ok)"

mkdir -p "${TMP}/data"
printf '%s\n%s\n' \
  '{"ts":"2026-09-12T06:05:55+00:00","event":"codex-spawn"}' \
  'not json' > "${TMP}/data/decisions.jsonl"
OUT="$(doctor "${TMP}/data")"; RC=$?
seen_ok() {
  [ "${RC}" -eq 0 ] && has "${OUT}" "Codex spawn hook 记录：1" && \
    has "${OUT}" "最后一次 Codex spawn：2026-09-12T06:05:55+00:00" && \
    has "${OUT}" "坏记录：1 行"
}
check "有记录：报告次数、最近时间与坏行数" "$(yn seen_ok)"

# Phase 9 D4：模式文件里是 v2 不认的旧值时，hook 回退目录默认值（2026-10-06 起为 off）；doctor 必须报同一个值
mkdir -p "${TMP}/legacy"; printf 'dry-run\n' > "${TMP}/legacy/mode"
OUT="$(env -u TIER_GUARD_MODE HOME="${TMP}/home" python3 "${ROOT}/hooks/tier_doctor.py" --data "${TMP}/legacy")"
legacy_ok() { has "${OUT}" "当前 mode：off" && ! has "${OUT}" "当前 mode：dry-run"; }
check "旧模式文件 dry-run：doctor 与 hook 一致报目录默认值 off" "$(yn legacy_ok)"

# 方案 A：配置显式选择；环境配置不自动同步；诊断不得写入数据。
DIAGDATA="${TMP}/config-readonly"
DIAGPERSIST="${TMP}/config-persist"
mkdir -p "${DIAGPERSIST}"
printf 'guard\n' > "${DIAGPERSIST}/mode"
python3 - "${ROOT}/config/routing.catalog.v2.json" "${TMP}" <<'CATALOG'
import json, pathlib, sys
cfg = json.loads(pathlib.Path(sys.argv[1]).read_text())
for mode in ("audit", "guard"):
    cfg["mode"] = mode
    pathlib.Path(sys.argv[2], mode + ".json").write_text(json.dumps(cfg))
pathlib.Path(sys.argv[2], "invalid.json").write_text('{"schema_version":2,"mode":"audit"}')
pathlib.Path(sys.argv[2], "broken.json").write_text('not JSON')
CATALOG
diagnostic() { env -u TIER_GUARD_MODE TIER_GUARD_CONFIG="${TMP}/guard.json" python3 "${ROOT}/hooks/tier_doctor.py" --data "${DIAGDATA}" "$@"; }
diag_success() { [ "${RC}" -eq 0 ] && has "${OUT}" "$1"; }
OUT="$(diagnostic)"; RC=$?
check "config diagnostics：无参数不读取配置环境变量" "$(yn diag_success '当前 mode：off')"
OUT="$(diagnostic --config "${TMP}/audit.json")"; RC=$?
check "config diagnostics：CLI audit 配置优先于环境配置 guard" "$(yn diag_success '当前 mode：audit')"
OUT="$(env -u TIER_GUARD_MODE python3 "${ROOT}/hooks/tier_doctor.py" --data "${DIAGPERSIST}" --config "${TMP}/audit.json")"; RC=$?
check "config diagnostics：合法持久模式优先于自定义默认值" "$(yn diag_success '当前 mode：guard')"
OUT="$(env TIER_GUARD_MODE=off python3 "${ROOT}/hooks/tier_doctor.py" --config "${TMP}/audit.json" --data "${DIAGDATA}")"; RC=$?
check "config diagnostics：模式环境变量优先于自定义默认值" "$(yn diag_success '当前 mode：off')"
diag_error() { [ "${RC}" -ne 0 ] && has "${OUT}" "❌" && ! has "${OUT}" "当前 mode" && ! has "${OUT}" "Traceback"; }
for DIAGBAD in "${TMP}/missing.json" "${TMP}/broken.json" "${TMP}/invalid.json" "${ROOT}/config/routing.default.json"; do
  OUT="$(diagnostic --config "${DIAGBAD}" 2>&1)"; RC=$?
  check "config diagnostics：无效显式配置拒绝 ${DIAGBAD##*/}" "$(yn diag_error)"
done
diag_argument_error() { diag_error && has "${OUT}" "--config"; }
for DIAGARG in end flag duplicate; do
  case "${DIAGARG}" in
    end) OUT="$(diagnostic --config 2>&1)" ;;
    flag) OUT="$(diagnostic --config --unknown 2>&1)" ;;
    duplicate) OUT="$(diagnostic --config "${TMP}/audit.json" --config "${TMP}/guard.json" 2>&1)" ;;
  esac
  RC=$?
  check "config diagnostics：参数不完整或重复拒绝 ${DIAGARG}" "$(yn diag_argument_error)"
done
check "config diagnostics：不创建缺失的数据目录" "$(yn [ ! -e "${DIAGDATA}" ])"
check "config diagnostics：既有持久模式未被改写" "$(yn [ "$(cat "${DIAGPERSIST}/mode")" = guard ])"

echo ""
echo "  总计 ${PASS} 通过 / ${FAIL} 失败"
[ "${PASS}" -gt 0 ] && [ "${FAIL}" -eq 0 ]
