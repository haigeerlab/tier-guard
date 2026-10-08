---
description: tier-guard 路由摘要：v2 请求/选择/派发/实际观测，以及历史 v1 记录
argument-hint: "[--share [天数]]"
allowed-tools: Bash
---

参数：`$ARGUMENTS`

这是 Claude Code 插件命令，完整入口为 `/tier-guard:tier-report`。`--share` 统计 Claude 转录，不统计 Codex 总用量。空日志或仅 v1 记录时报告可能显示历史配置的模式；核实当前模式用 `/tier-guard:tier-mode` 或 doctor。详见 [参考](../docs/reference.md) 与 [已知限制](../docs/compatibility.md)。

跑下面这条命令，把输出（已经是 markdown）原样给用户，不要改数字、不要补结论。
参数里有 `--share` 就原样追加到命令末尾（会扫 `~/.claude/projects` 下的 transcript 算子代理占比，只读，较慢）：

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/hooks/tier_report.py" --data "${CLAUDE_PLUGIN_DATA}"
```

「待标注」列表里的条目只能由用户判定。用户给出判定后用 `/tier-label`，不要替用户标。
