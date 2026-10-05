# tier-guard

为**新建子代理**按本次任务选择最低成本合格的 `model + reasoning_effort`。它不创建任务、
不改变主代理的模型，也不替代上游工作流对任务拆分、边界和验收标准的判断。

## 当前可用方式

主代理在仍能读取子任务明文时调用 `tier-routing`，完成任务判断后，在 `spawn_agent` 中显式传入
所选参数：

| 子任务需要的能力 | Codex 子代理 |
|---|---|
| 机械、只读 | `gpt-6-luna` / `high` |
| 有明确验收的受限实现 | `gpt-6.1-sol` / `medium` |
| 跨模块取舍、风险或不可逆影响 | `gpt-6.1-sol` / `xhigh` |

例如，向主代理明确提出：

> 使用 tier-routing，按子任务明文选择最低成本合格模型，然后创建一个子代理。

这会在创建 child 时选择参数；不会在主任务或 child 运行中切换模型。

`pin` 指这次派活时用户显式指定了 `model` 或 `reasoning_effort`。pin 是锁定选择：tier-guard
只记录建议，不会覆盖它。

## 已验证的 Codex Desktop 行为

在 Codex Desktop `26.908.40834 / 0.154.0-alpha.6.2`，原生派发已实际回执：

- 简单只读任务：Luna / medium；
- 受限实现：Terra / high；
- 方案取舍：Terra / xhigh；
- 父代理始终保持原模型与 effort。

详细证据见 [宿主兼容性记录](docs/research/2026-09-12-v2-compatibility-status.md)。

> 这是 2026-09-12 在**当时的候选目录**（`gpt-5.6-luna` / `gpt-5.6-terra`）下的实测记录，
> 保留原样作为证据。候选目录已于 2026-10-05 更新为上表，三档派发行为尚未在新目录下复验；
> 更新依据见 [模型目录更新](docs/research/2026-10-model-catalog-update.md)。

## 上游档位标记

上游工具（或你自己）可以为一次派活声明档位，写在任务文本里，**独占一行**：

```
<!-- tier-guard: tier=L2 failures=1 reason=按 spec 第 3 节实现，验收明确 -->
```

| 字段 | 含义 |
|---|---|
| `tier` | 必填，`L1` / `L2` / `L3`（大小写敏感）。L1 = 机械、只读；L2 = 有明确验收的受限实现；L3 = 跨模块取舍、歧义或不可逆 |
| `failures` | 可选，非负整数：同一任务此前连续失败的次数。写错会让整个标记失效 |
| `reason` | 可选，自由文本，写在最后；只给人读，不参与任何判定 |

整段任务里必须恰好出现一次。没有、重复、不独占一行、取值非法，都按「没有标记」处理，回到文本推断，核心不会因此失败。
也可以通过 `optional_context` 信封（`schema_version: 2`）传 `tier`；信封不带 `failures`。

**优先级：pin > floor > tier > 推断。** pin 照旧不改写。floor 是不可逆、歧义、跨模块或取舍类任务的下限，
上游 tier 只能在它之上生效：任务文本能伪造标记，所以一段写着 `tier=L1` 的不可逆任务仍然按最高档路由，
并在日志里记下这次冲突。没有 floor 时，tier 优先于推断，可以低于推断。

**升档与收回。** `tier=L1` 且 `failures>=1` 时按 L2 路由（仍不低于 floor）；`tier=L2` 且 `failures>=2` 时，
决策里记一条 `reclaim`，并按 profile 处理：

| profile | 收回时 |
|---|---|
| `guard`、`auto` | deny：原因说明这是第二次失败后的收回，要求主代理自己处理或重新界定任务；从不带 `updatedInput` |
| `audit` | 只输出提醒，派活照常放行 |
| `off`、pin 的派活、宿主 `dispatch_nudge` 闸门关闭 | 什么都不做 |

收回不依赖 `session_id`，也不受「每会话至多一次」限制；它不读写预路由提醒的会话标记。当前只有 Claude Code 的闸门是开的，
所以收回 deny 在 Claude Code 上已生效，Codex 不变。失败日志由主代理自己交给下一次尝试，tier-guard 不接触它。

**日志里有什么。** 每次派发记 `tier_source`（`pin` / `floor` / `upstream` / `inferred`）；低于 floor 时记 `tier_conflict`；
升档时记 `escalation`（`to` 是过 floor 之后的最终档）；收回有输出时记 `reclaim_output`（`deny` / `remind`）；
`reason` 只记是否存在和它的 SHA-256。**从不记录**任务原文、`reason` 正文、失败日志。

**Codex 的限制。** 目前 Codex 的 hook 在边界只看到不透明令牌，**读不到这个标记**，所以 hook 在 Codex 上不会采纳 tier、
也不会产生升档或收回；`tier-routing` skill 让主代理自己读标记并遵守同样的规则，是标记在 Codex 上生效的唯一途径。

## 安全边界

默认模式是 `guard`：写入最小化审计信息（任务长度和 SHA-256，不保存任务原文），不改写派发参数；宿主 `dispatch_nudge` 打开时，每个会话第一次未 pin 派活会被拦下一次、要求主代理显式传参。`audit` 仍可选作只提醒、不拦截。Claude Code CLI 的 `dispatch_nudge` 已开启（Codex 仍关闭），所以在 Claude 上默认每个会话第一次未 pin 的子代理派活会被拦下一次。

Claude Code CLI `2.1.269` 已验证能在 `PreToolUse` 接收可见子任务文本并采纳 `updatedInput`；一条未 pin 的
明确只读子任务实际以 Haiku 启动。Claude 的宿主能力闸门因此已开放，但默认仍是不改写参数的 `guard`，只有用户显式
启用并通过质量门槛的 `auto` 才会改写未 pin 子代理。

Codex Multi-Agent V2 当前会在 hook 边界把子任务变为不透明令牌。因此 hook 无法安全地自行理解任务
语义，也不会猜测后改写到更高或更低模型。可用流程仍是主代理的明文预路由；hook 负责审计和保护。

只有上游在派发前提供可验证的任务明文，或与实际 child payload 绑定的可信结构化能力标签后，hook
才可能独立自动选择模型。该前置条件记录在 [待办](tasks/tier-guard/todo.md)，背景见 OpenAI Codex
[#33284](https://github.com/openai/codex/issues/33284)。

## 开发验证

```bash
/bin/bash scripts/validate.sh
```

## License

Licensed under the [Apache License 2.0](LICENSE).

该命令覆盖路由合同、Claude/Codex adapter、模式与报告、审计和插件结构检查。

真实 Codex CLI 的三档主代理预路由验收必须在 Terminal/TUI 中运行，不能用 `codex exec` 代替：

```bash
/bin/bash scripts/codex-cli-preroute-smoke.sh
```

脚本建立隔离 Git 目录并保留审计日志与线程回执，结束后自行打印核对位置。
