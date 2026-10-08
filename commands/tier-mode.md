---
description: 查看或切换 tier-guard 的 mode（出厂默认 off；可切 audit / guard；auto 需真实宿主质量证据）
argument-hint: "[off|audit|guard|auto]"
allowed-tools: Bash
---

参数：`$ARGUMENTS`

这是 Claude Code 插件命令，完整入口为 `/tier-guard:tier-mode`。Codex 使用脚本并显式传数据目录；见 [使用与配置参考](../docs/reference.md)。已有环境变量优先于持久模式。

- 参数为空：查看当前 mode 和它的来源

  ```bash
  python3 "${CLAUDE_PLUGIN_ROOT}/hooks/tier_state.py" show --data "${CLAUDE_PLUGIN_DATA}"
  ```

- 参数非空：把参数原样作为 `<mode>` 切换

  ```bash
  python3 "${CLAUDE_PLUGIN_ROOT}/hooks/tier_state.py" set "<mode>" --data "${CLAUDE_PLUGIN_DATA}"
  ```

出厂默认是 `off`：hook 不拦截、不提醒、不记录，`tier-routing` skill 仍照常引导主代理显式选模型。想让 hook 工作就切到 `guard`（宿主开关打开时，每个会话第一次未 pin 的派活会被拦下一次、要求显式传参，从不改写参数）或 `audit`（只提醒不拦截）。

把输出原样转告用户。当前 `auto` 会被拒绝 —— 尚缺真实宿主端到端质量校准证据。
**不要替用户绕过**：不要改环境变量、不要直接编辑状态文件、不要换个说法再试。
