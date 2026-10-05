#!/bin/bash
# 在真实交互式 Terminal 中验收 Codex CLI 的主代理明文预路由。
# 历史：CLI 0.154 时 codex exec 的 collaboration wait 不会创建可观察 child，所以本脚本走交互式 TUI。
# 2026-10-05 更正：CLI 0.160.0 上 codex exec 能正常派子代理（线程表 source=exec 的主线程下有子线程，
# 子线程 source.subagent.thread_spawn.parent_thread_id 指向主线程）。本脚本仍用 TUI 以保持与既有证据一致。
set -eu

if [ ! -t 0 ] || [ ! -t 1 ]; then
  echo "请在真实交互式 Terminal 中运行；CI、管道和伪终端不能替代 Codex TUI。" >&2
  exit 2
fi
if ! command -v codex >/dev/null 2>&1; then
  echo "找不到 codex 命令。" >&2
  exit 2
fi

# 每次运行放在同一个固定 Git 仓库下的独立子目录。Codex 按 Git 根判定信任，所以只有首次运行
# 会弹信任提示，~/.codex/config.toml 里也只留这一条；每次新建仓库则每次都弹、每次多一条。
# 实测 `-c 'projects."<dir>".trust_level="trusted"'` 不能免除提示，不是替代方案。
# 路径必须先解析符号链接：Codex 在线程表里记的是 /private/var/...，用 /var/... 去查会查空。
SMOKE_ROOT="$(cd "${TMPDIR:-/private/tmp}" && pwd -P)/tier-guard-cli-preroute"
mkdir -p "${SMOKE_ROOT}"
if [ ! -d "${SMOKE_ROOT}/.git" ]; then
  git -C "${SMOKE_ROOT}" init -q
  git -C "${SMOKE_ROOT}" config user.email tier-guard@example.invalid
  git -C "${SMOKE_ROOT}" config user.name tier-guard-probe
fi
SMOKE_DIR="$(mktemp -d "${SMOKE_ROOT}/run-XXXXXX")"
SMOKE_LOG_DIR="${SMOKE_DIR}/tier-logs"
mkdir -p "${SMOKE_LOG_DIR}"
CODEX_STATE_DB="${CODEX_HOME:-${HOME}/.codex}/state_5.sqlite"

PROMPT=$'Use the installed tier-routing skill. Create exactly three native child agents, one at a time, and wait for each. The parent may read the skill but must not modify the project. Do not tell me model choices before spawning.\n\nChild A is a mechanical read-only task; it must not use tools, read files, write files, or run commands, and must reply exactly CLI_PREROUTE_LUNA_OK.\n\nChild B is a bounded implementation task with explicit acceptance; it must not use tools, read files, write files, or run commands, and must reply exactly CLI_PREROUTE_L2_OK.\n\nChild C compares approaches involving risk, cost, and rollback tradeoffs; it must not use tools, read files, write files, or run commands, and must reply exactly CLI_PREROUTE_XHIGH_OK.\n\nFor each child, independently choose and explicitly pass the lowest-cost qualified model and reasoning effort according to tier-routing. After all three finish, report their replies only.'

echo "隔离工作目录：${SMOKE_DIR}"
echo "（信任只在首次运行时询问一次，作用于 ${SMOKE_ROOT}）"
echo "唯一审计目录：${SMOKE_LOG_DIR}"
echo "父代理：gpt-6.1-sol / high（不等于任何子代理目标，继承与路由不会混淆）。"
echo "本次用 TIER_GUARD_MODE=audit 强制覆盖；生产默认 profile 是 guard。"
echo "在 TUI 显示三个 child 回复后，退出 Codex 回到此脚本以打印只读证据。"

TIER_GUARD_LOG_DIR="${SMOKE_LOG_DIR}" TIER_GUARD_MODE=audit \
  codex -C "${SMOKE_DIR}" -m gpt-6.1-sol -c 'model_reasoning_effort="high"' \
  --no-alt-screen -s read-only -a never "${PROMPT}"

echo ""
echo "=== tier-guard 审计记录 ==="
if [ -f "${SMOKE_LOG_DIR}/decisions.jsonl" ]; then
  tail -n 3 "${SMOKE_LOG_DIR}/decisions.jsonl"
else
  echo "没有审计记录；不要据此宣布测试通过。"
fi

echo ""
echo "=== Codex 本地线程（仅此隔离 cwd） ==="
python3 - "${SMOKE_DIR}" "${CODEX_STATE_DB}" <<'PY'
import sqlite3
import sys
from urllib.parse import quote

cwd, db = sys.argv[1], sys.argv[2]
# 只读打开：这是取证，不该有任何写入 Codex 状态库的可能。
con = sqlite3.connect('file:' + quote(db) + '?mode=ro', uri=True)
print('id\tmodel\treasoning_effort\tcli_version\ttitle')
for row in con.execute(
    'select id, model, reasoning_effort, cli_version, title from threads where cwd = ? order by created_at',
    (cwd,),
):
    print('\t'.join('' if value is None else str(value) for value in row))
PY

echo ""
echo "通过条件：三个 child 回复、三条对应审计记录，且线程实际为 gpt-6-luna/high、gpt-6-luna/high、gpt-6.1-sol/xhigh（child B 是受限实现，2026-10-05 起 L2 也走 luna/high）。"
echo "父线程应保持 gpt-6.1-sol / high 不变；任何 child 出现 sol/high 即为继承而非路由；child B 若是 sol/medium 说明还在用旧目录。"
echo "保留上述目录作证据；本脚本不会删除它。"
