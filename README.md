# tier-guard

[中文](README.md) | [English](README.en.md)

Claude Code 与 Codex 的子代理模型路由插件。在主代理决定创建子代理后，按任务所需能力从候选目录中选择成本排序最低的合格模型；Codex 还选择 `reasoning_effort`。主代理的模型不变。

**已发布版本：0.2.8 · 出厂默认 `off`。** `tier-routing` skill 引导主代理显式选模型；hook 的审计、提醒、拦截和改写能力取决于模式与宿主。插件不创建任务，也不决定任务拆分和验收标准。

## 1. 项目定位

子代理可能继承主代理的模型。简单只读工作也使用高成本模型，会产生不必要的开销。tier-guard 提供候选目录、派发前判断和审计，帮助主代理为已决定派出的任务选择合格模型。

这里的“最低成本”指**当前候选目录内的 `cost_rank` 排序**，不是实时价格查询，也不保证整个任务最省钱。主代理仍负责界定任务、判断是否派活和验收结果。

本仓的小任务实验中，派活总成本增加 15%～54%；一次省钱结果复跑不稳定，Codex 使用长等待也仅与不派持平。详见[派活成本结论](docs/research/2026-10-06-dispatch-verdict.md)。这些是特定实验的结果，不是所有任务的普遍规律。

## 2. 使用场景与边界

适合已经需要上下文隔离或独立探索的子任务，以及需要观察子代理请求模型、路由建议和执行结果的开发者。几次工具调用就能完成的小任务，通常由主会话直接完成更合适。

当前候选来自 [v2 目录](config/routing.catalog.v2.json)：

| 所需能力 | Claude Code | Codex CLI / Desktop |
|---|---|---|
| L1：机械、只读 | `haiku` | `gpt-6-luna` / `high` |
| L2：有明确验收的受限实现 | `sonnet` | `gpt-6-luna` / `high` |
| L3：跨模块取舍、歧义或不可逆影响 | `opus` | `gpt-6.1-sol` / `xhigh` |

- 只在创建子代理前选择参数，不切换运行中的代理。
- 显式模型或 effort 是 **pin（锁定）**，hook 不改写。Claude 的环境变量和 agent 定义也可能构成 pin。
- Claude Code 的 hook 可看到任务文本；Codex 原生 hook 在已验证版本中只收到不透明令牌，不能独立判断任务语义。Codex 依靠主代理读取 skill 后显式传参。
- 运行时不依赖 agent-skills 或 spec-guard；它们是可选的上游工作流或开发工具。
- 当前没有外部语义 provider 实现；路由器不向外部分类服务发送任务文本。宿主自身的模型服务和网络行为由宿主管理。
- hook 会读配置、事件及必要的宿主转录，启用后会写本地审计和状态；详细范围见[数据与权限](docs/reference.md#5-数据与权限)。

Claude Code CLI 有真实派发证据；Codex CLI / Desktop 有主代理预路由证据。Claude Code Cloud 和原生 Windows shell 未经本仓验证，详见[兼容性](docs/compatibility.md)。skill 是主代理执行的指令，不能保证每次自然派活都会加载或遵循它。

## 3. 前置条件

- 已安装并完成宿主所需认证的 Claude Code 或 Codex；宿主支持插件、skills 和对应 hook 功能。
- `python3` 及 `/bin/bash`。本仓未声明经过验收的最低 Python 版本；完整变异测试使用 Python 3.7 起提供的接口。仓库检查针对 macOS Bash 3.2 兼容性；不依赖 `jq` 或第三方 Python 包。
- 安装 Git marketplace 时可访问 GitHub，并具备宿主安装所需的 Git 环境。
- 账号能使用目录中的候选模型和 Codex effort；候选目录不会自动发现账号可用模型。
- hook 执行、读取必要转录和写入插件数据目录的权限。Codex 的 hook 信任需要在 CLI 的 `/hooks` 中审核。

安装命令已按 Claude Code `2.1.291`、Codex CLI `0.160.0` 的本机帮助核对。这是文档核对版本，不是最低支持版本；真实行为的已测版本见兼容性文档。

## 4. 快速开始

### Claude Code

在终端安装：

```bash
claude plugin marketplace add haigeerlab/tier-guard
claude plugin install tier-guard@tier-guard
```

重启会话后，先在 Claude Code 中查看状态：

```text
/tier-guard:tier-mode
```

首次安装且没有配置覆盖时应显示 `off`。然后发送：

```text
使用 tier-routing，为一个只读审查子任务选择候选模型并解释原因；先不要创建子代理。
```

预期主代理说明任务边界、建议候选及是否值得派活。若希望观察实际 hook 行为，可切到审计模式，再明确要求一次范围和验收清楚的只读子任务：

```text
/tier-guard:tier-mode audit
使用 tier-routing，创建一个只读子代理：只检查 README 的章节标题，不修改任何文件。验收：返回缺少的章节及其理由。
/tier-guard:tier-report
```

真实派活会消耗宿主模型用量。若主代理决定应自己完成，则没有子代理审计记录，不能据此判定 hook 失效。

### Codex CLI / Desktop

在终端安装固定发布版本：

```bash
codex plugin marketplace add haigeerlab/tier-guard --ref v0.2.8
codex plugin add tier-guard@tier-guard
```

若已经登记同名 marketplace 的另一个 ref，先按[更新步骤](#7-更新与卸载)处理旧来源，不能直接重复 add 改 ref。

在 Codex CLI 中用 `/hooks` 审核当前插件 hook，开启新会话；Desktop 使用原生界面发起任务。`/hooks` 是 CLI 交互入口，不是普通桌面聊天消息。

发送同样的“选择模型，先不创建子代理”请求即可检查 skill。**Claude Code 的 `/tier-guard:tier-mode` 等命令不会因安装而出现在 Codex。** Codex 需要查看或设置模式时，使用[脚本入口](docs/reference.md#2-codex-与普通-shell-入口)，并传入实际插件路径及 Codex 数据目录。

默认 `off` 时 hook 不写日志。审计验证必须先设置 `audit`，再通过原生派活创建子代理；Codex 记录通常为 `task_visibility=opaque_token`、`applied=false`。这表示输入边界，不表示安装失败。

## 5. 使用入口、命令与参数

Claude Code 命令使用插件命名空间，避免与其他插件重名：

| 入口 | 参数与用途 |
|---|---|
| `/tier-guard:tier-mode` | 无参数查看模式和来源；`off`、`audit`、`guard` 持久切换；v2 拒绝持久 `auto` |
| `/tier-guard:tier-report` | 摘要；可加 `--share [天数]`，默认 7 天，仅统计 Claude 转录的 output token 占比 |
| `/tier-guard:tier-doctor` | 只读诊断路径、有效模式和 Codex hook 记录；不能证明 hook 信任状态 |
| `/tier-guard:tier-label <id> <fp\|tp\|reject\|accept>` | 用户人工标注 v1 历史记录；v2 不适用 |
| skill `tier-routing` | 派活前判断是否值得派、选择候选，并显式传入新子代理参数；可点名使用 |

| 模式 | Claude Code CLI | Codex CLI / Desktop（生产闸门） |
|---|---|---|
| `off`（出厂默认） | 不记录、提醒、拦截或改写；skill 仍可用 | 同左 |
| `audit` | 记录建议；未 pin 派活可收到提醒 | 审计；提醒闸门关闭 |
| `guard` | 不改参数；会话首次未 pin 派活拦一次，之后提醒；L2 连续失败收回另行判断 | 审计；提醒、拦截和改写闸门关闭 |
| `auto` | 受控临时模式，可对未 pin、可判断且宿主支持的输入改写；首次派活拦截仍适用 | 自动改写不可用；不透明输入不改写 |

`guard` 可能影响宿主自己创建的 Explore 等子代理，并增加一次重派轮次。出厂 `off` 不覆盖已经保存的模式。模式优先级为 `TIER_GUARD_MODE` → 数据目录中的 `mode` → 目录默认值。

`auto` 只能由用户明确选择临时试验；模式命令拒绝开启时，不应让代理改环境变量或状态文件绕过。更多参数、上游档位标记和配置限制见[使用与配置参考](docs/reference.md)。

## 6. 输出与验收

正常安装后的数据目录通常为：

- Claude Code：`~/.claude/plugins/data/tier-guard-tier-guard/`
- Codex：`~/.codex/plugins/data/tier-guard-tier-guard/`

宿主注入值或用户覆盖可改变路径，以 state / doctor 的输出为准。

| 验收对象 | 应核对的证据 |
|---|---|
| 安装 | 宿主插件清单中版本、启用状态和路径正确；开启新会话 |
| 默认状态 | state / doctor 显示 `off` 及来源；没有新增日志是预期行为 |
| 审计链路 | `audit` / `guard` 下原生派活新增 `decisions.jsonl`，事件为 `agent` 或 `codex-spawn` |
| 主代理预路由 | 派发参数显式包含所选模型；Codex 还包含 effort；实际回执需另核对 |
| 参数自动改写 | `applied=true` 仅表示 hook 输出了改写；必须同时核对宿主实际执行回执 |
| Claude 实际执行 | `SubagentStop` / 转录提供模型和 token；未观测不能解释为 0 用量 |

0.2.8 的 report 按现行配置显示当前模式，与空日志或 v1 记录无关，并保留 v1 历史统计；doctor/report 支持显式 `--config`。从 0.2.7 升级后需重启会话，并核对实际加载版本。详见[兼容性与已知限制](docs/compatibility.md)。

tier-guard 不换算金额。按模块统计主会话与子代理总成本，可选用 [spec-guard](https://github.com/haigeerlab/spec-guard-plugin) 的成本报告工具；两个插件运行时不读取彼此数据。

## 7. 更新与卸载

### Claude Code

```bash
claude plugin marketplace update tier-guard
claude plugin update tier-guard@tier-guard
```

更新后重启会话，核对版本和模式。现有持久模式及环境变量可能继续生效。

卸载并保留数据：

```bash
claude plugin uninstall tier-guard@tier-guard --keep-data
```

省略 `--keep-data` 会按宿主卸载策略处理持久数据；先备份需要保留的审计与标注。如果安装使用了 project / local scope，卸载时指定相同的 `--scope`。

### Codex

固定 tag 安装不会自动跟随新发布。CLI 0.160.0 将 ref 计入来源匹配，不能直接重复 add 改 ref。先备份需要保留的数据，移除旧 marketplace 登记，再以目标 tag 添加来源、安装插件并核对版本：

```bash
codex plugin marketplace remove tier-guard
codex plugin marketplace add haigeerlab/tier-guard --ref v0.2.8
codex plugin add tier-guard@tier-guard
```

以上是重新登记当前发布的示例；升级时替换 tag。移除来源到重新安装之间，该来源不可用。行为依据为 [Codex 0.160.0 来源匹配](https://github.com/openai/codex/blob/rust-v0.160.0/codex-rs/core-plugins/src/marketplace_add/metadata.rs)和[同名来源拒绝逻辑](https://github.com/openai/codex/blob/rust-v0.160.0/codex-rs/core-plugins/src/marketplace_add.rs)。对跟踪分支的 marketplace，可用 `codex plugin marketplace upgrade tier-guard` 刷新来源，然后重新安装；它不把固定 tag 改成最新发布。更新后重启，并重新检查 hook 信任。

```bash
codex plugin remove tier-guard@tier-guard
```

移除插件与移除 marketplace 是不同操作。卸载前备份数据；Codex remove 帮助只承诺卸载和清理插件缓存，不将它视为数据保留或彻底擦除的保证。需要清理数据时先确认实际目录，再自行删除该插件的数据；宿主转录不属于插件数据。

## 8. 故障排查

| 症状 | 检查与处理 |
|---|---|
| 没有日志 | 先看有效模式；`off` 本来不记录。再检查插件启用、新会话、数据路径、hook 信任及是否真的创建了子代理 |
| Codex 找不到 `/tier-mode` | 使用脚本入口；Claude 命令文件不会注册为 Codex slash 命令 |
| 切模式后仍是旧模式 | 检查 `TIER_GUARD_MODE`，它优先于持久文件；确认命令和 hook 使用同一数据目录 |
| 安装版 0.2.7 的 report 显示 `dry-run` | 旧报告的历史配置限制；用 state / doctor 核实。升级到 0.2.8 并重启会话后再核对 |
| Codex `opaque_token` / `applied=false` | 已测宿主的正常边界；使用主代理明文预路由，不修改能力闸门来强行自动路由 |
| guard 首次派活被拒绝 | 预期行为；主代理按目录写明模型后重派。L2 二次失败收回不受每会话一次限制 |
| 模型不可用或 effort 被拒绝 | 核对账号和宿主支持；候选目录不是账号可用性保证 |
| 审计存在但实际执行未知 | 核对宿主是否提供并保存转录；Codex 当前只审计请求参数 |
| hook 没输出且有 fallback | 检查 Python、JSON 配置、权限；异常尽量放行并留日志，不能保证日志始终可写 |

不要仅凭“没有记录”推断未安装或未信任。更详细的诊断步骤见[参考文档](docs/reference.md)。

## 9. 架构与文档导航

```text
主代理决定是否派活
  ├─ tier-routing skill：读取任务明文，选择候选并显式传参
  └─ 宿主 hook：PreToolUse → 适配层 → route_decide.py → 审计 / 提醒 / 改写
       └─ Claude SubagentStop：回读实际执行模型和用量
候选目录：config/routing.catalog.v2.json
本地数据：decisions.jsonl、mode、nudge-denied/、历史 labels.jsonl
```

判断顺序为 **pin → floor（能力下限）→ 合法上游档位 → 文本推断**。低档标记不能压过 floor；无法判断时保守选择。完整约束和只读豁免见[规约](spec/tier-guard.md)。

- [使用与配置参考](docs/reference.md)
- [当前兼容性与已知限制](docs/compatibility.md)
- [文档导航与历史证据](docs/README.md)
- [变更记录](CHANGELOG.md)

## 10. 开发、贡献与反馈

本地免费验证：

```bash
/bin/bash scripts/validate.sh
```

开发约束、定向测试、变异测试和真实宿主验证边界见[贡献指南](docs/contributing.md)。贡献时说明问题、影响、修改范围及验证证据。可通过 [GitHub Issues](https://github.com/haigeerlab/tier-guard/issues) 提交反馈，通过 [Pull Requests](https://github.com/haigeerlab/tier-guard/pulls) 提交修改。

### 报告 bug

1. 先查看上面的故障排查和[已知限制](docs/compatibility.md)，再搜索现有 Issues，确认是否已有相同问题。
2. 登录 GitHub，在 Issues 页面点击 **New issue**。标题写清具体症状，例如“audit 模式下原生派活未写审计日志”。
3. 在正文中提供最小复现步骤、预期行为、实际行为、插件版本、宿主名称与版本、操作系统、模式及来源；有相关日志时，只附必要且已脱敏的片段。即使不能稳定复现，也请说明发生条件和频率。

可附上相关事件类型，方便定位派发或观测链路。不要公开密钥、完整任务原文、原始转录或未经检查的日志。

## 11. 许可

本项目采用 [Apache License 2.0](LICENSE)。完整条款以 LICENSE 为准。
