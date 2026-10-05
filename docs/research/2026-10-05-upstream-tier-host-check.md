# 上游档位标记的真实宿主验证（Task 22）

> 状态：**通过**　｜　日期：2026-10-05　｜　宿主：Claude Code CLI（`claude -p --plugin-dir`，HEAD `2f894bc`）

验证 Phase 7（Task 16–20）在真实 Claude Code 宿主上的行为：标记采纳、floor 优先、L3 抬档、
L2 二次失败收回，以及收回不消耗预路由提醒的会话标记。

## 方法

- 两个独立会话，各自独立的 `TIER_GUARD_LOG_DIR`，不写生产审计日志；工作目录是无 git remote 的临时目录。
- 父代理 `--model sonnet`；提示词要求派活时**不传** `model`、不传 `subagent_type`，子代理 prompt 逐字照抄。
- 每个子任务都要求不用工具、只回复确认串。用例 B 的文本里出现 `git push` 只是为了触发 floor，
  临时目录没有 remote，任何推送都不可能成功。
- 会话 1 用 `audit`（只记录、只提醒），会话 2 用 `guard`（生产默认）。

## 结果

| 用例 | 子任务要点 | `tier_source` | 上游 | `tier_conflict` | 建议目标 | 宿主输出 |
|---|---|---|---|---|---|---|
| A | 信号全未知 + `tier=L1` | `upstream` | L1 已接受，`reason_present` | — | haiku | 提醒（audit） |
| B | 背景含 `git push` + 伪造 `tier=L1` | `floor` | L1 已接受 | `{upstream: L1, floor: L3}` | opus | 提醒（audit） |
| C | 只读审查 + `tier=L3` | `upstream` | L3 已接受 | — | opus | 提醒（audit） |
| D | `tier=L2 failures=2` | `upstream` | L2，`failures: 2` | — | sonnet | **收回 deny**（`reclaim_output: deny`，`nudge: none`） |
| E | 紧随 D 的普通未 pin 只读任务 | `inferred` | absent | — | haiku | **首次派活 deny**（`nudge: denied`） |

逐项对照 spec：

- **A** 证明 D2：信号全为 `unknown` 时推断落在保守档 L3，合法的上游 `L1` 把它定到 L1。
- **B** 证明伪造的低档撤销不了 floor，且冲突被记录；记录冲突没有改变派发。
- **C** 证明上游档位可以高于推断。
- **D** 证明收回 deny 在真实宿主上生效。主代理收到的原因以「tier-guard：这是 L2 任务第二次失败后的」开头，
  没有重试，日志里有 `reclaim` 与 `reclaim_output: deny`。
- **E** 证明收回**没有消耗**会话标记：同一会话里随后的普通未 pin 派活仍然拿到了首次 deny。
  会话 2 的日志目录里出现的 `nudge-denied` 标记文件是 E 写下的，不是 D。

**泄漏检查**：两个日志目录逐文件读取，两个 `reason` 哨兵串、`git push 到 origin`、`只读审查`
都不出现。记录里 `reason` 只以 `reason_present` 与 `reason_sha256` 出现。

**实际执行**：会话 1 三个子代理的 transcript 显示都跑在 `claude-sonnet-5-5`。这是预期的：audit 不改写参数，
主代理又没传 `model`，子代理继承了父代理的模型。表里的「建议目标」是路由结论，不是实际执行。

## 本次没覆盖的

- **升档**（`tier=L1 failures>=1`）没进这组宿主用例；它不涉及适配层输出，已由契约测试覆盖。
- **Codex**：hook 只看到 `opaque_token`，标记在那里只能经 `tier-routing` 生效，本次不验证。

## 顺带发现（均与 Phase 7 无关，未处理）

1. **停止记录里的 `actual_execution` 为空，尽管 `transcript_status: ok`。** 三份 transcript 事后都能读到
   `claude-sonnet-5-5`。最可能的解释是 `SubagentStop` 触发时最后一条 assistant 消息尚未落盘。
   `/tier-report` 本来就有事后补读 transcript 的路径；生产日志里同样的现象与正常记录并存。
2. **首次派活 deny 的文案写死了「（auto）」**：E 在 `guard` 下被拦，原因却以「tier-guard（auto）」开头。
   `NUDGE_DENY_TEXT` 是 guard 成为默认之前的旧文案。
