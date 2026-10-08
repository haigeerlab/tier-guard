# Task 4b 真实宿主 smoke：Codex CLI

> 历史记录：本文的版本、默认模式、型号、价格、路径和发布状态以记录日期为准。当前使用说明见 [README](../../README.md)，现行宿主能力及限制见 [兼容性](../compatibility.md)。原始实验结果保留。

> 日期：2026-09-12　｜　宿主：codex-cli 0.153.4（TUI，交互式）　｜　被测：从 marketplace 装进 Codex 的 tier-guard 0.1.0

## 方法

`codex plugin marketplace add <本仓>` → `codex plugin add tier-guard@tier-guard`（装的是**安装时的快照**：
`~/.codex/plugins/cache/tier-guard/tier-guard/0.1.0`）。在 scratch 目录开交互式 TUI，用 tmux 驱动：
跳过版本更新提示 → 目录信任 → **hook 审核页逐条 review 后按 `t` 只信任这一条**（没有用 “trust all”）→
派一次 `spawn_agent`。判据是 Codex 侧数据目录里的日志，不看模型自述。

审核页显示的待信任内容（原样）：

```
Event     PreToolUse          Matcher   spawn_agent
Source    Plugin - tier-guard@tier-guard
Command   /bin/bash ".../plugins/cache/tier-guard/tier-guard/0.1.0/hooks/tier-guard-codex.sh"
Mode      Sync                Timeout   5s
```

## 结果：通过

会话模型 `gpt-5.3-codex-spark high`；派活参数 `model=gpt-5.6-terra`、`reasoning_effort=high`，
message 含不可逆动作词 `git push` 和一行验收。

`~/.codex/plugins/data/tier-guard-tier-guard/decisions.jsonl`（hook 自己写的，一条）：

| 字段 | 值 |
|---|---|
| `event` | `codex-spawn` |
| `text_source` | `message`（任务文本取对了字段） |
| `actual` | `{model: gpt-5.6-terra, effort: high}` |
| `decision.start_tier` → `tier` | `T1` → **`T2`**（命中 `R-IRREVERSIBLE`） |
| `decision.action` / `target_reasoning_effort` | `raise` / `xhigh`（slug 不变） |
| `mode` / `applied` | `dry-run` / **`false`** |

TUI 侧对照：`Spawned … (gpt-5.6-terra high)` —— dry-run 下守卫**只记不改**，子代理确实仍跑在 `high`。
子代理回复 `probe ok`；Codex 自述「实际传入 model=gpt-5.6-terra、reasoning_effort=high」，与日志一致。

## 两条被推翻 / 被坐实的前提

1. **`expose_spawn_agent_model_overrides` 不是必需的**（推翻 plan 的前置条件）。
   本次跑之前已把误加的两张 `[agents.*]` 表删掉（见下），配置里没有这个键，`spawn_agent`
   照样接受 `model` / `reasoning_effort`。0.153.4 上不需要它。
2. **`[agents.<name>]` 是「定义 agent 角色」的命名空间，不是多 agent 配置。**
   我先前把 `expose_spawn_agent_model_overrides` 追加成 `[agents.multi_agent_v2]` /
   `[agents.multi_agent]`，Codex 每次启动都报 `Ignoring malformed agent role definition:
   agent role ... must define a description`。已按原样删除该段，marketplace 与插件安装记录保留。
   这个键真正的位置仍未确定（`-c` 覆盖对嵌套表不做严格校验，探不出来），但既然不需要，就不再猜。

## 附带观察

- Codex 里工具的实际命名空间是 `multi_agent_v1.spawn_agent`，而 hook 的 `matcher: "spawn_agent"`
  照样命中 —— 与文档「matcher 用规范名」一致。
- 目录信任、hook 信任是两道独立的闸：前者问的是当前工作目录，后者才是插件 hook。
- 桌面版（ChatGPT.app）这一半**没跑**：那是原生 GUI，本会话驱动不了。plan 的验收要求 CLI 与桌面版各一次，
  所以 Task 4b 仍算部分完成。
