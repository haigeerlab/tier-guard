# 当前兼容性与已知限制

[中文](compatibility.md) | [English](compatibility.en.md) · [返回 README](../README.md)

核对日期：2026-10-08；源码基线 0.2.7。生产目录是 `off`；Claude 的 `pre_dispatch_apply` 与 `dispatch_nudge` 为 true，Codex 的两项均为 false。表中的实测结果只覆盖所列版本、协议与配置，不是对所有新版本的承诺。

## 1. 宿主能力

| 宿主 | 已有证据 | 生产限制 |
|---|---|---|
| Claude Code CLI | 2.1.269 的可见任务、pin、受控 Haiku auto 回执；2.1.270 的提醒评估；2026-10-05 的三档与环境 pin 复验 | 默认 off；guard / audit 不改写；持久 auto 拒绝；具体别名由宿主解析 |
| Codex CLI | 0.154.0 的原生审计、明文预路由；0.160.0 的新目录派发和记录字段复验 | 原生任务为 opaque_token；主代理按 skill 显式选择；hook 不独立选语义、不自动改写、不提醒或 deny |
| Codex Desktop | 26.908.40834 / 0.154.0-alpha.6.2 的历史三档主代理预路由与原生审计 | 旧型号仅为机制证据；未证明生产 hook 自动改写，能力闸门关闭 |
| Claude Code Cloud | 无本仓 v2 真实子代理派发证据 | 不从 CLI 结果外推 |
| 原生 Windows shell | 无本仓验证 | hook 依赖 `/bin/bash`；不宣称直接支持 |

本次只按本机 Claude Code 2.1.291、Codex CLI 0.160.0 的 `--help` 核对安装、更新、卸载接口，没有重新运行真实宿主派活。macOS Bash 3.2 是仓库回归环境；其他 Unix 环境需自行验证宿主和 shell。

报告的当前模式始终读取现行配置，与日志是否为空或只含 v1 无关；默认配置为 `off`，环境变量和合法持久模式按既有优先级覆盖。v1 门槛结果仅解释历史数据，不代表当前 v2 可开启 auto。

## 2. 已知限制

- **自定义目录不自动同步**：hook 读 `TIER_GUARD_CONFIG`；state、doctor 和 report 均支持显式 `--config`。无参数时诊断仍读插件默认配置，不自动读取 hook 的配置环境变量。参考[配置优先级](reference.md#3-配置来源与优先级)。
- **skill 执行有宿主和模型差异**：安装 skill 不等于每次自然派活都加载它；显式传入参数属于 pin，hook 不纠正主代理选错的档位。
- **实际执行与用量有缺口**：Claude 依赖宿主写下的转录；报告会尝试回读。Codex 审计只记录派发参数，不能作为实际模型或总花费证明。
- **异常日志不是保证**：配置、解释器、目录权限等故障会尽量放行；无法写日志时，可能没有 fallback 记录。
- **成本不是实时账单**：目录的成本排名不查询当前定价；实验通过率和经济结论不能外推到所有任务或账号。

## 3. 验证证据

- [Claude CLI v2 受控 auto](research/2026-09-13-claude-cli-v2-smoke.md)
- [Claude 完整端到端与后续修复](research/2026-09-13-claude-cli-v2-e2e.md)
- [提醒与 guard 复评](research/2026-09-13-dispatch-nudge-e2e.md)
- [Codex CLI v2 受控参数改写与主代理预路由](research/2026-09-12-task7-codex-cli-v2-smoke.md)
- [Desktop 原生派活历史证据](research/2026-09-12-codex-desktop-native-smoke.md)
- [2026-10-05 候选目录与宿主复验](research/2026-10-05-catalog-rehost-verification.md)
- [Codex L2 Luna 任务实验](research/2026-10-05-codex-l2-luna-experiment.md)

旧 Codex CLI 受控快照采纳过 updatedInput，证明的是参数机制；它没有解决任务文本不透明的问题，不授权生产自动路由。上游问题背景见 [OpenAI Codex #33284](https://github.com/openai/codex/issues/33284)。

## 4. 支持声明的验收标准

主代理预路由要有明确派发参数和真实 child 回执；hook 自动路由要同时有派发前审计、`applied=true`、选中参数和实际执行回执。仅有安装、离线测试、Spawned 文本或事后日志不能代替这些证据。新宿主支持应先形成方案，再在隔离配置中验证，最后评审能力闸门变更。
