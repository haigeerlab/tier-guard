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

## 当前候选目录

<!-- candidate-table:begin -->
| 所需能力 | Claude Code | Codex CLI |
|---|---|---|
| mechanical + read_only | `haiku` | `gpt-6-luna` / `high` |
| implementation + bounded_change | `sonnet` | `gpt-6.1-sol` / `medium` |
| tradeoff + cross_cutting | `opus` | `gpt-6.1-sol` / `xhigh` |
<!-- candidate-table:end -->

这是候选能力目录，不是固定模板：路由器结合本次任务信号选择最低成本的合格行。

## 宿主边界

- 原生 Codex `collaboration.spawn_agent` 当前会在 hook 边界把 `message` 交付为不透明令牌；hook 无法安全地从中恢复任务语义。因此上面的**主代理明文预路由**是 Codex 的可用路径，hook 只负责审计与保护：遇到 `opaque_token` 时绝不擅自改写到高档。
- Claude Code CLI 与原生 Codex CLI：当前默认 profile 都是 `guard`：记录建议、不改写参数；宿主 `dispatch_nudge` 打开时，每个会话第一次未 pin 派活会被拦下一次，要求显式传参。Claude Code CLI
  `2.1.269` 已有真实 Haiku child 回执，故生产目录只为它开启宿主能力闸门；仍须显式进入 `auto`、通过
  质量门槛且未 pin 才会改写。Codex CLI 与 Desktop 的能力闸门仍关闭。
- `auto` 只在有真实宿主端到端质量证据后才可实际改写；目录中的
  `host_capabilities.<host>.pre_dispatch_apply` 是不可由环境变量绕过的闸门。
  当前 mode 命令也会拒绝持久开启它。
- Codex Desktop：在 26.908.40834 / 0.154.0-alpha.6.2 已端到端验证主代理明文预路由的三档实际派发：
  `luna / medium`、`terra / high`、`terra / xhigh`；每次同时留下 `opaque_token` 审计。仍无
  `updatedInput` 自动改写实际采纳的证据，因此不能宣称 hook 自动路由。
- agent-skills 可显式提供版本化的结构化信号；缺失或无效时核心仍按保守规则运行。

用 `/tier-report` 查看请求、选择、hook 是否输出 `updatedInput`，以及宿主是否回报实际执行参数。
前者不是后者的证明；日志不保存任务原文。
