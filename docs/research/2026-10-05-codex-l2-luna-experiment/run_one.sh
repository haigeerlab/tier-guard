#!/bin/bash
# 用法：run_one.sh <task> <arm> <model> <effort>
set -u
X="$(cd "$(dirname "$0")" && pwd -P)"; task=$1; arm=$2; model=$3; effort=$4
W="$X/runs/$arm/$task"; rm -rf "$W"; mkdir -p "$W"
command cp "$X/tasks/$task/task.md" "$X/tasks/$task/test_solution.py" "$W/"
git -C "$W" init -q
PROMPT="在当前目录实现 task.md 描述的功能，写在 solution.py 里。完成后运行 python3 test_solution.py 直到输出 PASS。不要修改 test_solution.py。只用 Python 标准库。完成后只回复 DONE。"
codex exec -m "$model" -c "model_reasoning_effort=\"$effort\"" --sandbox workspace-write --skip-git-repo-check -C "$W" "$PROMPT" </dev/null > "$W/.codex-out.txt" 2>&1
echo "$task $arm exit=$?"
