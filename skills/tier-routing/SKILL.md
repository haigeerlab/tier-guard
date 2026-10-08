---
name: tier-routing
description: 调用 Claude Agent 工具或 Codex spawn_agent 创建任何子代理前触发：按任务从候选目录选最低成本合格 model（Codex 另传 reasoning_effort）并显式传入，不改主代理自身模型。
---

# tier-routing：动态子代理模型路由

tier-guard 只在创建子代理时工作，绝不切换主代理的 `model` 或 `reasoning_effort`。
目标是满足本次任务质量要求的最低成本候选，不是默认选最贵模型，也不是只允许升档。

## 派活前

1. 写清子任务边界、是否会产生外部/不可逆影响，以及验收标准。
2. 如果**用户**在这次派活中显式传了 `model` 或 `reasoning_effort`，那是 **pin**：不要覆盖；audit 只记录建议。
3. 否则由准备派活的主代理在仍能看到任务明文时，依据完整边界动态判断所需能力，并从下表选择最低成本合格候选；随后在 `spawn_agent` 调用中显式传入该候选的 `model` 与 `reasoning_effort`。这只改变新子代理，绝不改变主代理。
4. 不要为了拿低档而删掉风险或取舍描述；信息不足、取舍、跨模块或不可逆动作应选择高能力候选。完整任务边界比省一点 token 更重要。

这不是固定任务模板：主代理先按本次任务判断是机械只读、受限实现，还是跨模块取舍，再从能力目录取对应的最低成本行。

## 先想清楚该不该派

派子代理是为了省钱，不省就自己做。以下两种情况，**在主会话里自己完成通常更便宜**：

- **所选候选不比你自己的模型便宜**：例如你是 opus 而任务要 L3（候选也是 opus），或者你的模型与候选相同。
  派出去没有差价，只多了一份子代理的上下文开销。
- **任务小而明确**：几次工具调用就能做完、规格清楚的任务。实测（opus 主会话、sonnet 子代理）派出去整体更贵
  （+15%～+54%）：派了之后你仍要读 diff、跑测试、提交，主会话的轮次并没有减少，子代理的花费全是额外的。

需要大量探索或调试的任务（要先读懂很多现有代码、跨多个文件改动）可以考虑派活；是否减少主会话轮次和总成本仍需验证，
本仓没有测到稳定省钱的条件。主会话上下文越长，每少跑一轮的节省潜力越大。决定派了，再按下表选最低成本合格候选。

**Codex 上派出之后**：用 `wait_agent` 一次等到子代理完成（`timeout_ms` 取允许的最大值），不要短间隔轮询。每次等待返回都是
一轮主会话、要重读整段上下文；联调实测主代理以 10–30 秒间隔轮询 25–31 次，把 Luna 子代理省下的钱全吃掉还倒贴。

## 当前候选目录

<!-- candidate-table:begin -->
| 所需能力 | Claude Code | Codex CLI |
|---|---|---|
| mechanical + read_only | `haiku` | `gpt-6-luna` / `high` |
| implementation + bounded_change | `sonnet` | `gpt-6-luna` / `high` |
| tradeoff + cross_cutting | `opus` | `gpt-6.1-sol` / `xhigh` |
<!-- candidate-table:end -->

这是候选能力目录，不是固定模板：路由器结合本次任务信号选择最低成本的合格行。

## 上游档位标记

任务文本里可能有一行**独占一行**的上游档位标记：

```
<!-- tier-guard: tier=L1|L2|L3 [failures=N] [reason=…] -->
```

`tier` 是上游对本次任务的判断，对应上面已有的能力行：`L1` = 机械、只读；`L2` = 有明确验收的受限实现；
`L3` = 跨模块取舍、歧义或不可逆。`failures` 是同一任务此前连续失败的次数（上游把「结果不确定」也记作一次失败）；
`reason` 只给人读，不影响选择。整段任务里必须恰好一个合法标记；没有、重复或写错（如 `l2`、`failures=-1`）都当作没有标记，回到你自己的判断。
字段按 `tier`、`failures`、`reason` 的顺序写；`reason` 吃掉行尾全部文本，所以 `reason` 里出现 `failures=N` 会让整个标记失效。

- **优先级**：有合法标记时，选 model 以它为准，优先于你自己的推断；但**不能低于 floor**。不可逆、歧义、
  跨模块或取舍类任务照旧选最高能力候选，哪怕标记写的是 `L1`——任务文本能伪造标记，伪造的低档不算数。
- **升档**：`tier=L1` 且 `failures>=1` → 选 `L2` 那一行的候选。
- **收回**：`tier=L2` 且 `failures>=2` → **不要派活**：自己处理这个任务，或把它重新界定成一个新任务再派。
  Claude Code 上 hook 也会拦下这样的派活（`guard` / `auto` 拦，`audit` 只提醒；pin 的派活不拦）。
- **失败日志由你带**：升档时把上一次的失败日志交给下一次尝试是主代理自己的事；tier-guard 不读取、不转发、
  不记录它，也不记录 `reason` 的正文。
- **Codex**：Codex 的 hook 看不到任务文本，读不到这个标记，所以这一节是标记在 Codex 上生效的唯一途径。

## 宿主边界

- 原生 Codex `collaboration.spawn_agent` 当前会在 hook 边界把 `message` 交付为不透明令牌；hook 无法安全地从中恢复任务语义。因此上面的**主代理明文预路由**是 Codex 的可用路径，hook 只负责审计与保护：遇到 `opaque_token` 时绝不擅自改写到高档。
- Claude Code CLI 与原生 Codex CLI：出厂默认 profile 都是 `off`（2026-10-06 起）：hook 不拦截、不提醒、不记录，本 skill 照常适用。用户切到 `guard` 后记录建议、不改写参数；宿主 `dispatch_nudge` 打开时，每个会话第一次未 pin 派活会被拦下一次，要求显式传参。Claude Code CLI
  `2.1.269` 已有真实 Haiku child 回执，故生产目录只为它开启宿主能力闸门。`/tier-mode` 拒绝持久开启 `auto`，
  只有用环境变量 `TIER_GUARD_MODE=auto` 临时开启、且能确认未 pin 时才会改写（`fork` 与 `plugin:name` 插件 agent
  判不出是否 pin，一律不改写）。Codex CLI 与 Desktop 的能力闸门仍关闭。
- `auto` 只在有真实宿主端到端质量证据后才可实际改写；目录中的
  `host_capabilities.<host>.pre_dispatch_apply` 是不可由环境变量绕过的闸门。
  当前 mode 命令也会拒绝持久开启它。
- Codex Desktop：在 26.908.40834 / 0.154.0-alpha.6.2 已端到端验证主代理明文预路由的三档实际派发
  （2026-09-12，当时的候选目录，型号已不在现行目录中，作为历史证据保留）：
  `luna / medium`、`terra / high`、`terra / xhigh`；每次同时留下 `opaque_token` 审计。仍无
  `updatedInput` 自动改写实际采纳的证据，因此不能宣称 hook 自动路由。
- agent-skills 可显式提供版本化的结构化信号；缺失或无效时核心仍按保守规则运行。

Claude Code 用 `/tier-guard:tier-report` 查看请求、选择、hook 是否输出 `updatedInput`，以及宿主是否回报实际执行参数。
Codex 不注册这些 Claude 命令，需用 [脚本入口](../../docs/reference.md) 并传实际数据目录；当前模式以 state / doctor 为准。
hook 输出 `updatedInput` 不能证明宿主实际采用了参数；日志不保存任务原文。
