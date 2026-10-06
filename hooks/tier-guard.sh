#!/bin/bash
# Claude 薄壳入口。PreToolUse(Agent) 判档；PreToolUse(Bash) 记 Codex 派活的「建议 vs 实际」。
#
# 铁律：**任何情况下退出 0**。stdout 只可能是 claude_hook.py 给的 hook 输出（auto 的 updatedInput、
# 预路由提醒、guard / auto 的 deny）；其余一律空 —— 空 stdout + 退出 0 等于没装这个 hook。
# 守卫坏了（python 不在、配置读不到、payload 怪）不能变成干活坏了。
set -uo pipefail
EVENT="${1:-agent}"
PAYLOAD="$(cat)" || exit 0

# off：python 都不起，与未装插件逐字节一致
[ "${TIER_GUARD_MODE:-}" = off ] && exit 0

# Bash 每条命令都会进来：不是派 Codex 就在这里退，纯 bash，不起 python
if [ "${EVENT}" = bash ]; then
  case "${PAYLOAD}" in *codex-exec.sh*) ;; *) exit 0 ;; esac
fi

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" 2>/dev/null && pwd)" || exit 0
OUT="$(printf '%s' "${PAYLOAD}" | python3 "${HERE}/claude_hook.py" "${EVENT}" 2>/dev/null)" || {
  # python 起不来 / 崩了：放行，并尽量留一条记录（目录解析照抄 tier_state.data_dir 的顺序）
  D="${TIER_GUARD_LOG_DIR:-${CLAUDE_PLUGIN_DATA:-${HOME}/.local/state/tier-guard}}"
  if [ -n "${D}" ] && { [ -d "${D}" ] || mkdir -p "${D}"; } 2>/dev/null; then
    printf '{"event":"%s","fallback":"tier-guard.sh: claude_hook.py 没跑起来"}\n' "${EVENT}" \
      >> "${D}/decisions.jsonl" 2>/dev/null
  fi
  exit 0
}
[ -n "${OUT}" ] && printf '%s\n' "${OUT}"
exit 0
