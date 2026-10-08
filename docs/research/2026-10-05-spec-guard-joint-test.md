# tier-guard × spec-guard 联调（路径 1：经 Agent 工具的派活）

> 历史记录：本文的版本、默认模式、型号、价格、路径和发布状态以记录日期为准。当前使用说明见 [README](../../README.md)，现行宿主能力及限制见 [兼容性](../compatibility.md)。原始实验结果保留。

> 状态：**通过**　｜　日期：2026-10-05　｜　tier-guard `0.2.4`（默认 guard）·
> spec-guard `0.42.0`　｜　对方会话：「项目所有者角色」，工作目录 `spec-guard-plugin`

## 先说清楚这次验证的是什么

两个插件之间按设计有两条连接：

1. **派活经过 hook**：任何会话用 Agent 工具派子代理，都会经过 tier-guard 的 `PreToolUse`。
2. **上游档位标记**：spec-guard 在任务文本里写入 `<!-- tier-guard: tier=Lx -->`，tier-guard 解析
   （合同见 spec「上游档位信号」）。

联调前查了已安装的 spec-guard 0.42.0（166 个文件）：**没有任何地方提到 tier-guard，也不写档位标记，
它自己也不经 Agent 工具派子代理**——它的委派走 `session-delegation` / `session-routing`（另开会话或经
bridge 交给 Codex worker），那条路径 tier-guard 的 hook 本来就看不到。

所以本次只验证**连接 1**：在 spec-guard 项目的会话里，经 Agent 工具派出的活能否被 tier-guard 正确接管，
两个插件同时启用是否互不干扰。**连接 2 尚不存在，本次不覆盖。**

## 方法

由对方会话在 `spec-guard-plugin` 工作目录里依次派三个不用工具、只回复确认串的子代理；本会话读
tier-guard 生产审计日志中联调开始时刻（07:47:39 UTC）之后的记录逐条核对，不只采信对方的自述。

## 结果

对方会话 4 次派活、2 次结束全部入账，`session_id` 一致，transcript 路径都在 `spec-guard-plugin` 下。

| 步骤 | 对方报告 | 日志记录 | 判定 |
|---|---|---|---|
| A · 不传 model | 被拦，原因以「本会话第一次未 pin 的派活已被拦」开头 | `nudge: denied`，`tier_source: inferred` | ✅ |
| A · 重派 `haiku` | 放行，回复 `JT_A_OK` | `tier_source: pin`；结束记录实际 `claude-haiku-4-5-20251001`，`usage_basis: message-id-dedup` | ✅ |
| B · 带 `tier=L2 failures=2`，不传 model | 被拦，原因以「这是 L2 任务第二次失败后的收回」开头 | `upstream_tier: accepted`，`reclaim` 有值，`reclaim_output: deny`，`nudge: none` | ✅ |
| C · `haiku` | 放行，回复 `JT_C_OK` | `tier_source: pin`；实际 `claude-haiku-4-5-20251001`，`usage_basis` 在 | ✅ |

结论：在 spec-guard 项目的会话里，guard 首次拦截、上游档位解析、L2 二次失败收回、pin 放行、0.2.4 的
用量去重都照常工作；两个插件同时启用没有互相干扰。

## 观察（非故障）

- **A 的档位判断不一致。** 任务文本「不要使用任何工具，只回复 JT_A_OK」不含候选目录里的只读关键词，
  hook 判为信息不足、按保守档建议 opus；对方主代理判断为机械只读，选了 haiku。显式参数是 pin，hook
  只记录不改写。这是 todo 中「主代理比 hook 选得更低」观察项的又一个样本。
- **两条 `transcript_status: missing` 的结束记录**（对方会话与本会话各一条）属于宿主不写 transcript 的那类
  子代理，生产日志中约 85% 的结束记录如此，与联调无关。

## 下一步

连接 2 需要 spec-guard 侧实现：在交给子代理的任务文本里写入档位标记、重试时带 `failures=N`。合同要点已
发给对方会话评估（2026-10-05）；是否实现、如何实现由 spec-guard 项目决定。
