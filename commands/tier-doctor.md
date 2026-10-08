---
description: Claude Code 中只读诊断 tier-guard 的数据目录、日志与 Codex hook 可观察性
argument-hint: ""
allowed-tools: Bash
---

Claude Code 完整入口为 `/tier-guard:tier-doctor`。当前使用步骤见 [参考](../docs/reference.md)，宿主支持见 [兼容性](../docs/compatibility.md)。

运行下面的命令，把输出原样转告用户；不要根据“没有记录”猜测未安装或未信任。

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/hooks/tier_doctor.py" --data "${CLAUDE_PLUGIN_DATA}"
```

这是 Claude Code 的命令；Codex 桌面版不会因本文件获得 `/tier-doctor`。在普通 shell
诊断 Codex 时，运行安装快照中的 `hooks/tier_doctor.py`，并显式传入 Codex 数据目录
（本机安装为 `~/.codex/plugins/data/tier-guard-tier-guard`）。

它不能读取 Codex 的 hook 信任状态。`/hooks` 是 Codex CLI 的信任入口；不要把它作为一条
普通消息发送到桌面聊天中。验证桌面版时，先在 CLI 审核当前 hook 的信任记录，再从原生桌面
界面发起一条带唯一标记的子代理任务，并检查是否新增审计记录。协作代理 API 不进入 Codex
`PreToolUse` 管线，不能替代此验证。
