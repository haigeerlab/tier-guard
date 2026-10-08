# 项目文档基线

本表显式声明现有项目文档的职责与权威来源；启用 Spec Guard 文档基线和模块影响核验。
`target` 表示已确认的目标约束，仍允许实现或宿主验收未完成；`verified` 仅指该行说明的核对范围。
基线、文档声明检查和历史快照均不证明整个模块已经交付。

| Concern | Authority | Status | Rationale |
|---|---|---|---|
| product-direction | `spec/tier-guard.md` | target | 目标、用户、成功标准与边界已明确；Codex 上游阻塞和 v2 总验收仍开放。 |
| architecture | `tasks/tier-guard/plan.md` | target | 架构决策与依赖图已有，详细路由与接口约束见 Spec；尚未把全部目标宣称为完成。 |
| developer-entry | `AGENTS.md` | verified | Codex 入口已补齐，引用 CLAUDE.md 的共用约束；引用、声明块及本地完整回归已通过。 |
| consumer-guide | `docs/README.md` | verified | 当前使用文档与双语导航已建立，Phase 10 记录了链接、示例和帮助核对；本状态不代表重新完成真实宿主安装验收。 |
| integration-contract | `spec/tier-guard.md` | target | RouteRequest、Decision、上游标记和宿主能力边界已有契约；Codex hook 的独立自动路由仍受上游前置条件限制。 |

实现与验收记录统一见 `tasks/tier-guard/todo.md`。本次只声明现有指导来源，
不新增行为承诺，不将暂缓观察或上游阻塞改为完成。

历史账本的 legacy 导入只保存当前能力图快照：`at: imported` 和
`19700101T000000Z-0001` 是迁移标记与目录占位，不能解释为真实的项目创建时间。
迁移预览的状态保留 `unknown`，模块数组为空，不据此证明过去的模块状态或审批。
