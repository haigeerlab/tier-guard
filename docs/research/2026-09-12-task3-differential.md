# Task 3 差分验收：Claude 薄壳真的把档位抬上去了

> 历史记录：本文的版本、默认模式、型号、价格、路径和发布状态以记录日期为准。当前使用说明见 [README](../../README.md)，现行宿主能力及限制见 [兼容性](../compatibility.md)。原始实验结果保留。

> 日期：2026-09-12　｜　宿主：Claude Code 2.1.268　｜　被测：本仓 `hooks/`（`--plugin-dir` 单次加载，未安装、未改 settings）

## 方法

照 [P0 spike](2026-09-11-p0-spike.md) 的差分做法：两次 `claude -p --model sonnet --plugin-dir <本仓>`，
**只差 `TIER_GUARD_MODE`**。主会话被要求调用一次 `Agent`，显式传 `model="sonnet"`，
子代理 prompt 含不可逆动作词 `git push` 和一行验收。各用一个空的 scratch 目录作 cwd
（无 git remote；`-p` 下 Bash 无授权，子代理也被要求不调用任何工具）。

判据取**子代理自己 transcript 里 assistant 消息的 `model` 字段**，不听模型自述。

## 结果

| | 主会话发出的 `Agent.model` | hook 日志 | 子代理实际模型 |
|---|---|---|---|
| 对照组 `dry-run` | `sonnet` | `start_tier=T1 → tier=T2`，`action=raise`，`applied=false` | `claude-sonnet-5` |
| 处理组 `auto` | `sonnet` | 同上，`applied=true` | **`claude-opus-5`** |

子代理 transcript（`~/.claude/projects/` 下，按 cwd 编码）：
- 对照组 `…-scratchpad-diff-control/fa77f026-…/subagents/agent-a1d27a90e5daf389a.jsonl`
- 处理组 `…-scratchpad-diff-treat/db2d208f-…/subagents/agent-ad9adcbd876fbdfce.jsonl`

## 附带坐实的一条

**Claude 侧 `updatedInput` 不需要配 `permissionDecision`。** 本仓输出只有
`{"hookSpecificOutput":{"hookEventName":"PreToolUse","updatedInput":{…}}}`，处理组照样生效。

spike 文档写过「Claude 侧无此约束」，但当时的探针**始终带着** `permissionDecision:"allow"`，
这一点并没被单独验过；官方文档对此也没写（2026-09-12 查证）。现在有了一手证据。
不带 `allow` 的意义：不顺手绕过用户的权限流程 —— 守卫只改档位，不改授权。
