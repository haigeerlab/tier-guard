# Codex 项目开发入口

开始任何项目工作前，先读取 `CLAUDE.md`。其中的已定决策、测试要求、开发约束和权限边界
同样适用于 Codex；本文件不重复维护这些规则。

再按顺序读取：

1. `spec/CAPABILITY-MAP.md`：模块责任与构建顺序。
2. 当前模块的 `spec/<module-id>.md`：需求、边界与验收标准。
3. `tasks/<module-id>/plan.md` 和 `tasks/<module-id>/todo.md`：实施计划与实际执行状态。
4. 与本次工作相关的 `docs/research/` 证据。

<!-- BEGIN:spec-guard-codex-convention -->
## Spec Guard 项目约定

- 本仓使用本地模块流程；活跃模块取自 `.agent/state.json` 的 `activeModule`。
- 每个模块独立使用 `spec/<module-id>.md`、`tasks/<module-id>/plan.md` 和 `tasks/<module-id>/todo.md`。
- `/build` 从活跃模块的 todo 取第一个未勾选项；遇到上游阻塞先报告，不自行将其标为完成。
- 阶段交接或停止时，读取 `spec-guard:spec-guard-ops` 的共享检查点规则，说明结果与下一步。
- Plan 检查点标为 `gate` 或 `report`；未标注按 `gate` 处理，已有授权不重复询问。
- 若项目已启用 Local 事项账本，动代码前按 `spec-guard:ticket` 查重并取得事项 ID。
- 远端事项后端与目标须明确选择，不凭 Git remote 或旧 state 推断。
- tier-guard 在 Codex 上仅提供预路由建议与审计，宿主自动改写能力仍以真实验收证据为准。
<!-- END:spec-guard-codex-convention -->
