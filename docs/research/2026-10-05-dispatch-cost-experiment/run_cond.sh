#!/bin/bash
# 用法：run_cond.sh <ctx:small|large> <arm:inline|dispatch> <rep>
set -u
E="$(cd "$(dirname "$0")" && pwd -P)"; ctx=$1; arm=$2; rep=$3; name="$ctx-$arm-$rep"
A=/Users/vilin/.claude/plugins/cache/addy-agent-skills/agent-skills/0.6.11
SG=/Users/vilin/.claude/plugins/cache/spec-guard-marketplace/spec-guard/0.44.0
TG=/Users/vilin/.claude/plugins/cache/tier-guard/tier-guard/0.2.4
OLD=/private/tmp/claude-503/-Users-vilin-Documents-haigeerlab-tier-guard/3ba6c8c8-9b0e-445c-b83e-6cfb08d46361/scratchpad/rt-e2e/proj
P="$E/$name"; rm -rf "$P"; mkdir -p "$P"; cd "$P"
git init -q && git config user.email rt@example.invalid && git config user.name rt
mkdir -p spec tasks/textkit .agent textkit tests
for f in spec/CAPABILITY-MAP.md spec/textkit.md tasks/textkit/plan.md tasks/textkit/todo.md .agent/state.json; do git -C "$OLD" show 54e7ce6:"$f" > "$f"; done
printf '# textkit\n\n极小的文本工具库，用于联调测试。\n' > CLAUDE.md; touch textkit/__init__.py tests/__init__.py
flag=""; [ "$arm" = dispatch ] && flag="--dispatch"
CLAUDE_PROJECT_DIR="$P" /bin/bash "$SG/hooks/setup-convention.sh" local $flag >/dev/null 2>&1
git add -A && git commit -qm "chore: seed"
EXTRA=()
if [ "$ctx" = large ]; then
  { echo "nonce: $name-$(date +%s)-$RANDOM"; cat "$E/preload-100k.txt"; } > "$E/preload-$name.txt"
  EXTRA=(--append-system-prompt-file "$E/preload-$name.txt")
fi
COMMON=(--model opus --setting-sources project,local --plugin-dir "$A" --plugin-dir "$SG" --plugin-dir "$TG" ${EXTRA[@]+"${EXTRA[@]}"} --permission-mode acceptEdits --allowedTools "Bash(python3:*)" "Bash(git:*)" "Bash(sed:*)" "Bash(cat:*)" "Bash(ls:*)" "Bash(head:*)" "Bash(tail:*)" "Bash(wc:*)")
TIER_GUARD_LOG_DIR="$E/log-$name" claude -p "/build auto" "${COMMON[@]}" < /dev/null > "$E/$name-1.txt" 2>&1
TIER_GUARD_LOG_DIR="$E/log-$name" claude -p "approve" --continue "${COMMON[@]}" < /dev/null > "$E/$name-2.txt" 2>&1
echo "$name done: $(git -C "$P" log --oneline | wc -l | tr -d ' ') commits"
