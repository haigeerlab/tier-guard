# Claude Code CLI v2：真实 pre-dispatch 自动路由

> 历史记录：本文的版本、默认模式、型号、价格、路径和发布状态以记录日期为准。当前使用说明见 [README](../../README.md)，现行宿主能力及限制见 [兼容性](../compatibility.md)。原始实验结果保留。

> 运行：2026-09-13 01:30–01:34 +0800
>
> 宿主：Claude Code CLI `2.1.269`
>
> 被测插件：工作树通过官方 `--plugin-dir` 直接加载；不依赖用户已安装 marketplace 快照。

## 目的

验证 Claude v2 adapter 不仅能写审计，还能在 `PreToolUse` 阶段将未 pin 子代理的选型通过
`updatedInput` 实际交给宿主。生产 catalog 保持默认 `audit`；测试只在隔离临时 catalog 中为
`claude-code` 打开 `pre_dispatch_apply`，并以 `TIER_GUARD_MODE=auto` 运行。

## 官方契约

- Claude 将 `Agent` 列为内建工具，且工具名是 permission rule 与 hook matcher 所使用的精确字符串：
  <https://code.claude.com/docs/en/tools-reference>
- `PreToolUse` hook 可返回 `permissionDecision` 与 `updatedInput`，且 matcher 按工具名匹配：
  <https://code.claude.com/docs/en/agent-sdk/hooks>
- `--plugin-dir` 是 Claude 推荐的本地插件测试方式：
  <https://code.claude.com/docs/en/plugins>

## 审计基线

一次未 pin 子代理真实完成并返回 `CLAUDE_TIER_GUARD_AUDIT_OK`。唯一审计记录为 v2、
`task_visibility=visible`、`profile=audit`、`applied=false`；这证明 command hook 在真实 CLI 的
`Agent` 调用上被触发。模型没有被改写，符合 audit 的定义。

## 受控 auto 回执

临时 catalog 只将 `host_capabilities.claude-code.pre_dispatch_apply` 设为 `true`。首个 auto 样本的
实际 Agent 输入未包含目录定义的只读标记，因而分类器保守选择 Opus；审计 `applied=true`，child metadata
与实际转录均是 `claude-opus-5`，证明 CLI 会采纳 adapter 的 `updatedInput`。

第二个未 pin 样本明确包含 `This is a read-only task. Do not modify any file.`。其审计只保存以下最小
证据，不保存任务原文：

| 字段 | 观测 |
|---|---|
| parent session | `87284ebb-ba1f-4471-b787-3bc2b38fcc1a` |
| task fingerprint | `716be1406551e2673b53d12ff790f87a7489ad8e1a07f3d846a420369bbb56c4` |
| visibility / profile | `visible` / `auto` |
| selected target | `claude-haiku` |
| hook output | `applied=true` |
| child metadata | `model=haiku` |
| child actual model | `claude-haiku-4-5-20251001` |
| child fixed reply | `CLAUDE_TIER_GUARD_AUTO_HAIKU_OK` |

该子代理无工具、无文件读写；父会话仍是原来的 Opus。CLI 汇总还独立列出了 Haiku 的子代理用量。

## 结论与范围

Claude Code CLI `2.1.269` 已验证：可见的、未 pin 的机械只读子任务能在真实 `PreToolUse` 阶段被选择为
最低成本合格候选并实际以 Haiku 启动。因此生产 catalog 可以为 `claude-code` 打开
`pre_dispatch_apply`。默认 profile 仍是 `audit`，且 auto 仍受质量门槛控制；这个证据不授权覆盖 pin，
不外推 Claude Code Cloud，也不改变 Codex 的 `opaque_token` 边界。
