#!/bin/bash
# Codex 薄壳入口：PreToolUse(spawn_agent)。
#
# 铁律同 Claude 侧：**任何情况下退出 0**；stdout 只可能是 codex_hook.py 给的 hook 输出（Codex 编码：
# updatedInput 配 permissionDecision:"allow"；提醒；guard / auto 的 deny）。其余一律空。
set -uo pipefail
PAYLOAD="$(cat)" || exit 0

# off：python 都不起
[ "${TIER_GUARD_MODE:-}" = off ] && exit 0

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" 2>/dev/null && pwd)" || exit 0
OUT="$(printf '%s' "${PAYLOAD}" | python3 "${HERE}/codex_hook.py" 2>/dev/null)" || {
  # python 起不来 / 崩了：放行，并尽量留一条记录（目录解析照抄 tier_state.data_dir 的顺序）
  D="${TIER_GUARD_LOG_DIR:-${CLAUDE_PLUGIN_DATA:-${HOME}/.local/state/tier-guard}}"
  if [ -n "${D}" ] && { [ -d "${D}" ] || mkdir -p "${D}"; } 2>/dev/null; then
    printf '{"event":"codex-spawn","fallback":"tier-guard-codex.sh: codex_hook.py 没跑起来"}\n' \
      >> "${D}/decisions.jsonl" 2>/dev/null
  fi
  exit 0
}
[ -n "${OUT}" ] && printf '%s\n' "${OUT}"
exit 0
