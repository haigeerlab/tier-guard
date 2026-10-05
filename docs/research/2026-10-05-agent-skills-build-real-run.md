# 真实开发流程里 tier-guard 有没有被触发：agent-skills `/build` 实测

> 状态：**结论明确——没有被触发**　｜　日期：2026-10-05　｜　agent-skills `0.6.11` · spec-guard `0.42.0` · tier-guard `0.2.4`

## 要回答的问题

tier-guard 写完了，但在一个真实的开发流程里它到底有没有起作用？用 agent-skills 跑一个实际开发任务时，流程里有没有
派子代理；派了的话，tier-guard 的路由逻辑有没有触发、子代理有没有按它分配的模型跑。

在此之前，所有验证都是**人为构造的派活**（让主代理照抄固定 prompt 去派），或是真实会话里主代理自己派活的统计
（Task 12/15）——没有一次是由 agent-skills 的开发流程驱动的。

## 方法

- **隔离用户配置**：`claude -p --setting-sources project,local`，不加载 `~/.claude/` 下的用户设置与全局 CLAUDE.md
  （其中有「`/build` 时把每个 task 派给 executor」的个人规则，会污染结论）；三个插件经 `--plugin-dir` 显式加载，
  模拟「只装了这三个插件的新用户」。先用探针确认：全局 CLAUDE.md 的特征词一个都不在上下文里，三个插件的 skill 都在。
- **真实项目**：按 spec-guard local 约定搭一个小项目（模块 `textkit`，约定块、能力图、模块 spec、plan、todo、
  `.agent/state.json`），plan 有两个带自动测试的任务。
- **真实流程**：`/build auto` → 停在 agent-skills 的计划确认 → `--continue` 回复 `approve` → 执行到底。
- tier-guard 用**默认 guard**，不加任何覆盖；审计写独立目录。父代理 `--model sonnet`。

## 结果

| 证据 | 结果 |
|---|---|
| 开发任务本身 | 两个任务完成，8 个测试通过，每个任务单独提交，todo 全部勾上 |
| 主代理的工具调用（读 transcript，与 hook 无关） | Skill 1、Bash 11、Write 2、Edit 4——**Agent 工具 0 次** |
| 子代理 transcript | **0 个** |
| tier-guard 审计日志 | **日志文件都没有生成** |
| 正向对照：同样参数下明确要求派一个子代理 | tier-guard 正常工作：首次未 pin 被拦 → pin 到 haiku 重派 → 实际 `claude-haiku-4-5-20251001` |

正向对照排除了「hook 坏了」：测试环境里 tier-guard 能工作，是 `/build` 全程**没给它机会**。

## 原因

agent-skills 的 `/build` 命令（44 行）里**没有任何派子代理的指示**，按设计在主会话里直接写代码、跑测试。主干开发
流程 `/spec → /plan → /build` 因此不会经过 tier-guard。agent-skills 里**会**派子代理的是 `/ship`（明确要求用 Agent
工具并行派 code-reviewer / security-auditor / test-engineer 三个专家），那条路径会被 tier-guard 接管。

本机生产日志里派活最多的 `executor`（198 次）主要来自用户全局 CLAUDE.md 的个人路由规则，换一个用户就不存在。

## 局限

- 只跑了一次，两个小任务。更大、更复杂的任务里主代理会不会自发派子代理，未测；但 `/build` 没有任何派活指示，
  可能性不大。
- 父代理用 sonnet；用户日常是 opus，行为可能有差异，同样理由大概率不改变结论。

## 结论与下一步

**缺口存在**：在主干开发流程里，tier-guard 没有被调用的入口。agent-skills 是第三方插件不能改，入口只能由我们自己的
spec-guard 提供——在它写入项目 CLAUDE.md 的约定块里引导主代理在 `/build` 时把 task 交给子代理，并带上档位标记。
需要权衡的是派子代理的固定开销（L2 实验里每次派活约 3–6 万 token 的缓存写），很小的任务派出去可能反而更贵。
