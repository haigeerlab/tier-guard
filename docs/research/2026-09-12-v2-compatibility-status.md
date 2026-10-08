# tier-guard v2 宿主兼容性状态

> 历史记录：本文的版本、默认模式、型号、价格、路径和发布状态以记录日期为准。当前使用说明见 [README](../../README.md)，现行宿主能力及限制见 [兼容性](../compatibility.md)。原始实验结果保留。

> 更新：2026-09-13。状态只依据可复现证据；“插件已安装”“离线薄壳测试通过”均不等于真实自动路由可用。

| 宿主 / 运行时 | v2 路由建议 | v2 自动改写 | 证据与限制 |
|---|---|---|---|
| Claude Code CLI 2.1.269 | **原生 audit 与低成本 auto 已验证** | **已验证（默认仍 audit）** | 官方 `--plugin-dir` 真实会话中，hook 收到可见 `Agent` 输入；临时受控 catalog 的 `applied=true` 由实际 `claude-haiku-4-5` 子代理回执确认。生产目录仅为 Claude 开放宿主能力闸门，`mode` 仍是 audit 且 auto 仍受质量门槛约束。 |
| Claude Code Cloud | 未验证 | **未验证** | 插件形态避免依赖本地 settings；尚无 v2 云端子代理派发证据。 |
| Codex CLI 0.153.4（历史） | v1 dry-run 已验证 | 仅 v1 历史证据 | 历史 smoke 证明该版本命中过 hook，但只验证了旧 T 档逻辑。 |
| Codex CLI 0.150.1（历史复测） | 可离线验证 | **未验证** | 已安装 v2 快照并真实完成无 pin 子代理；没有新增 `PreToolUse` 日志，见 Task 7 记录。 |
| Codex CLI 0.154.0 | **原生 audit 与三档明文预路由已验证** | **参数改写已验证；hook 独立语义自动路由受宿主输入边界阻塞** | 22:16 的交互式受控快照记录 `applied=true`，SQLite 回执为父 `terra/high`、子 `terra/xhigh`；真实参数采纳已证实。2026-09-13 的真实 TUI 预路由又回执子 `luna/medium`、`terra/high`、`terra/xhigh`。但原生 `collaboration.spawn_agent` 在 hook 边界提供不透明令牌而非子任务明文，守卫不能安全独立选择低成本候选。 |
| Codex Desktop 26.908.40834 / 0.154.0-alpha.6.2 | **原生 audit 与三档明文预路由已端到端验证** | **hook 自动改写未验证，当前不可开启** | 00:01–00:07 的原生 Desktop 任务同时新增 v2 审计记录；SQLite 回执覆盖子 `luna/medium`、`terra/high`、`terra/xhigh`，父保持 `terra/high`。hook 收到 `opaque_token`，故只审计、不改写；这验证预路由路径，不外推为 hook 自动路由。 |

## 默认与启用条件

- 默认 `audit`：记录建议，不改写子代理参数。
- 生产 catalog 已为真实验收通过的 Claude Code CLI 开放 `host_capabilities.claude-code.pre_dispatch_apply`；
  Codex 仍为 `false`。这只是宿主能力闸门：默认 `mode=audit` 不会改写，`auto` 仍必须经过运行时质量门槛。
- 不可仅因离线测试或界面上出现 “Spawned” 而切到持久 `auto`。
- 对每个宿主版本，只有同时观察到：PreToolUse 审计记录、`applied: true`、目标参数和子代理实际执行回执时，才可将该宿主标为自动路由已验证。
- 显式子代理 `model` 或 `reasoning_effort` 始终是 pin：即使未来某个宿主启用 auto，也只记录建议、不改写。
- 对原生 Codex 的 `opaque_token`，即便临时受控目录打开 `pre_dispatch_apply`，hook 也不输出
  `updatedInput`；无明文语义时自动升档会同时伤害成本与可解释性。

## 2026-09-13 Claude Code CLI 2.1.269：真实低成本 auto 回执

Claude 官方文档将 `Agent` 列为可被 `PreToolUse` matcher 匹配的内建工具，并将 `--plugin-dir` 列为
本地插件测试的正式入口。基于这两个契约，在隔离 Git 目录用 `--plugin-dir` 加载当前源码、唯一日志目录
与临时 catalog 运行真实 Claude CLI；临时 catalog 只把 `claude-code.pre_dispatch_apply` 设为 `true`，
生产 catalog 在测试期间没有修改。

第一条未 pin 子代理确认 hook 可见 `Agent` 的任务文本并输出 `updatedInput`；实际 tool input 没有命中
只读标记，故保守改写到 Opus，子代理 metadata 与转录均为 `claude-opus-5`。第二条明确包含只读标记的
未 pin 子代理留下 `profile=auto`、`task_visibility=visible`、`target=claude-haiku`、`applied=true` 的审计，
其 child metadata 是 `model=haiku`，实际转录模型为 `claude-haiku-4-5-20251001`，固定回执为
`CLAUDE_TIER_GUARD_AUTO_HAIKU_OK`。父会话未被改变。

因此 Claude 的 adapter 已证明可把可见任务的低成本选择实际送达 child；生产 catalog 现在只为该宿主打开
pre-dispatch 能力闸门，仍默认 audit。该结果不外推到 Claude Code Cloud，亦不绕过 pin 或 auto 的质量门槛。
完整受控记录见 [Claude CLI v2 smoke](2026-09-13-claude-cli-v2-smoke.md)。

## 上游需要提供的能力

Codex Desktop 仍需使 hook 的 `updatedInput` 影响实际派发参数。CLI 0.154.0 已有该能力的真实
回执；但要让 hook 独立按任务语义选择低成本候选，上游还需在派发前暴露任务明文、或提供可信的
结构化分类信号。在此之前，Codex 的可用路径是主代理在明文上下文中先按能力目录选择，再显式传入
子代理参数；Desktop 则仍需完整验证参数改写与实际执行，不能再把“有没有日志”当作自动路由判据。

2026-09-13 再核对 OpenAI 维护的 Codex 仓库后，公开 issue
[#33284](https://github.com/openai/codex/issues/33284) 对 Multi-Agent V2 的同一边界给出了独立的
受控复现：`PreToolUse` 在派发前收到的是 Fernet 形态的 `message`，而接收方仍可执行原始明文指令。
该 issue 提出的可接受修复是：在派发前向本地 policy 暴露明文，且把已审批的明文绑定到实际交付的
payload；单纯把明文缓存到本地、或派发后再读历史，都不能满足该绑定条件。当前主线
[`PreToolUse` 实现](https://github.com/openai/codex/blob/main/codex-rs/hooks/src/events/pre_tool_use.rs)
证明 hook 可以处理 `updatedInput`，但不构成 V2 `message` 已明文可见的契约。因此本插件不尝试
解码或旁路缓存，继续采用主代理明文预路由 + hook 审计保护；这条上游证据支持设计选择，但不能替代
本机各版本的端到端验收。

同日对公开 `main` 源码的复核也排除了“更新 matcher 或插件配置即可恢复明文”的可能：
[`communication_from_tool_message`](https://github.com/openai/codex/blob/main/codex-rs/core/src/tools/handlers/multi_agents_v2.rs)
只有运行时已标为 `DirectPlaintextMessage` 的调用才构造可读 `InterAgentCommunication`；其余路径直接调用
`new_encrypted`。这个 source 分类发生在插件 hook 之外，插件不能通过 matcher、`updatedInput` 或 catalog
把一个已加密的 V2 `message` 变为可信明文。故 Task 7 继续等待上游提供明文或与实际 child payload 绑定的
可信结构化标签，而不是等待另一轮本地配置尝试。

## 2026-09-12 Desktop 明文预路由探针

在 Desktop `0.154.0-alpha.6.2` 的当前会话中，主代理对一个“只读、禁止文件与工具操作、只回复固定
文本”的任务判为 `mechanical + read_only`，并在 `spawn_agent` 前显式传入
`gpt-5.6-luna / medium`。本地状态库回执：父线程
`01a09456-ae3f-7eb2-b935-62317ccbbb0f` 保持 `gpt-5.6-terra / high`，子线程
`01a09608-6894-7d41-aa6d-eed083418dd7` 实际为 `gpt-5.6-luna / medium`，且子代理交回预期固定文本。

本次调用通过协作代理 API 发起；该 API 按 Codex 宿主边界不进入 `PreToolUse`，因此会话回放没有 hook
事件、`tier-guard` 数据目录没有新增审计记录是预期行为，而不是未安装、未信任或会话未刷新的证据。
所以这条证据仅证明 Desktop 接受主代理显式选择的低成本子代理参数，**不证明**新安装快照的 hook 自动路由。
下一次 hook 验证必须从原生 Desktop 界面发起一条带唯一标记的子代理任务，并检查 hook 信任、日志、
`updatedInput` 和实际子代理参数四者。

## 2026-09-13 00:01 +0800 原生 Desktop 端到端预路由回执

在新的原生 Desktop 任务 `01a09626-a051-7ff0-930a-331e5f946969` 中，主代理按
`tier-routing` 将一个“无文件、命令和工具操作，只回复固定文本”的子任务归为
`mechanical + read_only`，显式传入 `gpt-5.6-luna / medium`。子线程
`01a0965a-7ac7-7db3-babe-2cd573eb37bd` 的 SQLite 回执为 `gpt-5.6-luna / medium`；父线程保持
`gpt-5.6-terra / high`，子代理回复 `TIER_GUARD_NATIVE_UI_OK`。

同一次原生调用新增 v2 `codex-spawn` 记录：`task_visibility=opaque_token`、生产 catalog 指纹
`69d643…e0970`、`host_pre_dispatch_apply=false`、`applied=false`。记录中的 `requested` 是
`luna/medium`，这证明 hook 没有改写主代理的预路由选择。由于 hook 边界没有任务明文，它的独立
建议仍是保守的 `terra/xhigh`；该建议不被应用，不能与实际的明文预路由混为一谈。

同一父任务随后以无文件/命令/工具访问的受限回复任务补齐另外两档：

| 任务语义 | 实际子代理回执 | 子代理回复 | hook 记录 |
|---|---|---|---|
| 仅单文件、可逆的受限实现 | `gpt-5.6-terra / high` | `TIER_GUARD_TERRA_OK` | `opaque_token`，`requested=terra/high`，`applied=false` |
| 跨方案比较与风险/成本/可回滚性取舍 | `gpt-5.6-terra / xhigh` | `TIER_GUARD_XHIGH_OK` | `opaque_token`，`requested=terra/xhigh`，`applied=false` |

这三条是受控的**模型选择与实际派发**证据，不是子任务产出质量的统计结论，也不意味着 hook 已能独立
读取任务语义或自动覆盖参数。

## 2026-09-13 00:54–00:55 +0800：CLI 真实 TUI 明文预路由三档回执

在隔离 Git 目录中，使用真实 `tmux` PTY 启动交互式 `codex-cli 0.154.0`，父线程
`01a0968a-d328-7960-8fa1-13d775958a59` 的实际参数为 `gpt-5.6-terra / high`。父代理在可读任务
上下文中按 `tier-routing` 分别显式 pin 三个 child；TUI 依次显示 `Started`、`Completed`，随后仅返回
约定的三个 sentinel。SQLite 实际线程回执为：

| child | 线程 | 实际参数 | 固定回执 |
|---|---|---|---|
| A | `01a0968b-0ca3-79c3-b6ec-257de402cc8e` | `gpt-5.6-luna / medium` | `CLI_PREROUTE_LUNA_OK` |
| B | `01a0968b-3085-75c1-8aaa-8133d990c874` | `gpt-5.6-terra / high` | `CLI_PREROUTE_TERRA_OK` |
| C | `01a0968b-512c-7a33-9d11-f57234e1bdaf` | `gpt-5.6-terra / xhigh` | `CLI_PREROUTE_XHIGH_OK` |

同一会话的唯一审计目录恰有三条 `codex-spawn` 记录，顺序与 child 对应。每条都标记
`task_visibility=opaque_token`、生产 catalog 指纹 `69d643…e0970`、`host_pre_dispatch_apply=false`
与 `applied=false`；其 `requested` 分别为上表的显式 pin。因此 hook 没有覆盖主代理的明文选择，也没有
把不透明令牌误判为可安全自动路由的文本。

这完成了 **Codex CLI 主代理明文预路由** 的端到端验证，证明 CLI 可按子任务向下和向上选择模型，且
不会改变父代理。它不完成“hook 独立低成本自动路由”：该 hook 仍不可读取任务明文，生产配置继续保持
`audit` 与 `pre_dispatch_apply=false`。

## 关联证据

- [CLI v2 冒烟（参数改写已验证，低成本样本待补）](2026-09-12-task7-codex-cli-v2-smoke.md)
- [Desktop 原生冒烟](2026-09-12-codex-desktop-native-smoke.md)
- [Codex CLI v1 历史冒烟](2026-09-12-task4b-codex-smoke.md)
