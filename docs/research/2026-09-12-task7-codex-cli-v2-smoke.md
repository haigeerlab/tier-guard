# Task 7：Codex CLI v2 自动路由冒烟（实际改写已验证；低成本样本待补）

> 历史记录：本文的版本、默认模式、型号、价格、路径和发布状态以记录日期为准。当前使用说明见 [README](../../README.md)，现行宿主能力及限制见 [兼容性](../compatibility.md)。原始实验结果保留。

> 说明：本文早期“无审计记录”的样本使用的 matcher 未覆盖扁平 V2 工具名；它们不再是
> “CLI 绕过 hook”的有效结论。文末 22:12–22:16 +0800 的受控交互式复测已验证
> `updatedInput` 被 CLI 采纳；该样本不是低成本候选，故不把它写成 Luna 路由通过。

> 运行：2026-09-12 17:49:28–17:51:45 +0800
> 宿主：交互式 Codex CLI `0.150.1`（tmux）
> 被测插件：`tier-guard@tier-guard` `0.1.1+codex.20260912094401`

## 目的与判据

验证一条无显式 `model` / `reasoning_effort` 的只读子任务是否在真正派发前被 v2
改写为低成本候选。唯一通过判据是：本次唯一日志目录出现一条 `routing_version: 2` 的
`codex-spawn` 记录、hook 输出 `updatedInput` 指向 `gpt-5.6-luna / medium`，且宿主可观察地启动
子代理并回报同一实际参数。`applied: true` 仅表示前一项（adapter 已输出），自身不构成通过。

## 准备

- 临时 Git 目录：`/private/tmp/tier-guard-v2-cli.A0L8VM`
- 唯一日志目录（环境变量）：`/private/tmp/tier-guard-v2-cli.A0L8VM/tier-logs`
- 环境：`TIER_GUARD_MODE=auto`；以 `--dangerously-bypass-hook-trust` 跳过仅本次受控
  测试的 hook 信任页面。
- 子任务文本不在此记录保存；其 SHA-256 是
  `8a9d67c15c9af6a36b668c90e8571d8ddc3b732efa71e569a15fb91f6f6f48f4`。
- 已安装快照的 `hooks/codex_hook.py` SHA-256 是
  `bc68739c5335b73658f46334daf5ed227ea8df55fe039a773130546d44176ca6`，与工作区文件一致。

## 观察

TUI 显示 `Started /root/git_repo_check`、随后 `Completed /root/git_repo_check`，并最终回复
`done`，所以这不是“模型没有派子代理”的假阴性。

但本次唯一日志目录没有创建 `decisions.jsonl`。同时只读检查两个回退位置：

| 路径 | 结果 |
|---|---|
| 测试指定目录 | 不存在 |
| `~/.codex/plugins/data/tier-guard-tier-guard/decisions.jsonl` | 仍为 1 行，mtime `2026-09-12T14:05:55+0800` |
| `~/.local/state/tier-guard` | 不存在 |

## 结论

**未验证，不能启用 CLI 的 v2 `auto`。** 已证明的事实是：该版本 CLI 能派出子代理，且当前
安装快照正确；但这次派发没有触发 tier-guard 的 `PreToolUse` 审计 hook，或至少没有让 hook
写入任何可见数据目录。无论两者哪一种，`updatedInput` 都没有证据已经到达宿主，不能把离线
薄壳测试当作真实自动改写。

当时它与 Desktop 的缺记录样本表象相近，但本记录**不**把它断言为相同根因：后续复测发现两侧
旧 matcher 均遗漏扁平 V2 工具名，见本文末尾的有效复测。

## 后续条件

1. 保持默认 `audit`；不要把 v2 持久切到 `auto`。
2. 在启用 PreToolUse 的原生 CLI 版本重跑同一协议，并对照唯一日志的 `applied`、目标参数和子代理
   实际回执。
3. 若该版本仍无记录，向上游附上本记录中的版本、插件快照哈希、任务 fingerprint 与日志基线。

## 2026-09-12 18:24–18:27 +0800：重装后的无效重试

为验证最新安全闸门是否已进入实际安装快照，已把本地插件重装为
`0.1.1+codex.20260912102340`；快照 `hooks/codex_hook.py` 的 SHA-256 为
`728511d6a1500ba2dcc0cc258a4f463be4387e40379ee9bfd8775a88c7881d4e`。在新的隔离 Git
目录 `/private/tmp/tier-guard-v2-cli.rsMJnC` 中启动交互式 `codex-cli 0.150.1`，环境为
`TIER_GUARD_MODE=auto` 和唯一 `TIER_GUARD_LOG_DIR`。当前生产 catalog 的
`host_pre_dispatch_apply` 仍为 `false`，因此即使 hook 被调用，也只应写审计记录、不得改写。

会话成功进入 `gpt-5.6-terra / high` 提示符，并提交了一条要求创建单个无 pin、只读子代理的指令；
子任务文本只记录 SHA-256：
`54a85ac7fa88305f9eeeb68d92cabc22e008eb5036198e2ae5218df40fef2d26`。随后约 50 秒内没有模型
回复、没有 `Started …`、没有子代理完成回执。唯一日志目录仍为 0 个文件；默认插件日志仍为旧的
888 字节文件，mtime 未变（`2026-09-12T14:05:55+0800`）。为避免继续占用会话，测试 tmux 已停止。

**此样本无效，不更新 Task 7 结论。** 它只能证明最新本地快照已安装；因 CLI 没有实际执行这条
请求，不能把“无日志”归因为 hook 未触发，也不能作为自动路由的反证或正证。

## 上游相关证据（非本机版本结论）

已安装快照与工作区都声明 `PreToolUse.matcher = "spawn_agent"`。OpenAI Codex 仓库的公开
[issue #36519](https://github.com/openai/codex/issues/36519) 报告：MultiAgentV2 暴露的
`collaboration.spawn_agent` 在 0.146.0 与 0.147.0-alpha.4 未将 pre-tool payload 规范化为
`spawn_agent`，从而绕过该 matcher；该 issue 当前仍为 open。它与本项目 Desktop 及旧 CLI 的
“子代理创建成功、但没有 PreToolUse 日志”现象一致，也提出了运行时应修复的准确层级。

这只是**相邻版本的上游相关证据**，不是对本机 `0.150.1` 的替代验证：除非 0.150.1 的真实
子代理调用产生可检查的 hook 记录或上游给出该版本的修复归属，Task 7 仍保持未验证。

## 2026-09-12 18:49–18:52 +0800：0.154.0 有效复测

全局 CLI 已由 `0.150.1` 升至 `0.154.0`，插件保持
`tier-guard@tier-guard 0.1.1+codex.20260912103007`；安装快照的 `codex_hook.py` SHA-256 仍为
`728511d6a1500ba2dcc0cc258a4f463be4387e40379ee9bfd8775a88c7881d4e`。在新的隔离 Git 目录
`/private/tmp/tier-guard-v2-cli-0154.tqIkvw` 中以 `TIER_GUARD_MODE=auto` 和唯一日志目录启动
交互式 CLI。未 pin 的只读子任务指纹为
`faffd933424c9a8f15758fd6fa5dd7a2d3c1d309a56ef7ebc17ca79472355e93`。

这一次主会话画面明确显示 `Started /root/git_check`、`Completed /root/git_check` 和 `done`，
所以确认真实创建并完成了一个子代理。唯一日志目录仍为 0 个文件；默认插件日志仍是旧的 888 字节
文件（mtime `2026-09-12T14:05:55+0800`），没有新增 v2 `codex-spawn` 审计记录。

**结论：0.154.0 也未验证自动路由，不能打开 `host_pre_dispatch_apply`。** 这是有效的
“子代理已派发但 PreToolUse 无可观察记录”反证；它与上游 #36519 的 MultiAgentV2 matcher 绕过
机制一致，但仍不把 issue 本身当成对二进制内部实现的直接证明。测试会话已停止。

## 2026-09-12 19:00–19:03 +0800：命名空间 matcher 补救复测

针对 #36519 报告的名称规范化缺口，插件新增了与原有 `spawn_agent` 并存的
`PreToolUse.matcher = "collaboration.spawn_agent"`，并在薄壳中将这两个名字等价处理。离线
回归先由 36/38 失败（缺 matcher、原始名字不记日志），再由 38/38 通过；这验证了插件自身的
配置与解析路径，而非运行时投递。

安装快照为 `tier-guard@tier-guard 0.1.1+codex.20260912105710`，其
`codex_hook.py` SHA-256 为
`4a75ee9334d37edebaffc23fce8bb1e5b7da02ed80f31c0007ef535df37c7547`，与工作区一致；
`codex-hooks.json` SHA-256 为
`ca21267d80e708e47cfb5a9afc7aae85dc0e9aabb6a7e53c62d1d7694c188474`，快照中明确包含
`spawn_agent` 和 `collaboration.spawn_agent` 两个 matcher。
在隔离 Git 目录 `/private/tmp/tier-guard-v2-cli-namespaced.1B7wZ1`，以 CLI `0.154.0`、
`TIER_GUARD_MODE=auto` 和唯一日志目录重跑同一类无 pin、只读任务。任务 SHA-256 是
`4bf14ec56a5fb0b15a536e4bf30f67a7fa11ba98251058db8989c776b67f744c`。画面依次显示
`Started /root/git_check`、`Completed /root/git_check` 与 `done`。

唯一日志目录仍为 0 个文件；默认日志仍是 888 字节，mtime
`2026-09-12T14:05:55+0800`，无新增 `codex-spawn` 记录。**因此 namespaced matcher 本身并不能
使当前 0.154.0 的 `collaboration.spawn_agent` 进入插件 hook。** 补丁保留为兼容将来运行时按原始
名称投递事件的路径，但当前版本仍不得启用 `host_pre_dispatch_apply`。测试会话已停止。

## 2026-09-12 20:09 +0800：扁平 V2 matcher 有效复测

随后依据公开运行时的名称归一化行为，插件将 matcher 收敛为一个严格表达式，同时覆盖
`Agent`、`spawn_agent`、扁平名 `collaborationspawn_agent` 与带分隔符的 namespace 形式；安装
快照为 `0.1.1+codex.20260912195543`。在升级后的 CLI `0.154.0` 中，以无 pin、只读子代理
任务进行原生派活，宿主输出出现 `PreToolUse`，子代理回复 `probe-ok`。

默认数据目录新增一条 v2 `codex-spawn` 记录：时间 `2026-09-12T12:09:14+00:00`、session ID
`01a09585-73f3-75a0-a319-7c9d5380501d`、任务指纹
`50ebb154f7f8d0e6f58bfa15b677b7e581a90028e70b7e5ea45ee2bb795471bb`。记录为未 pin 的 audit
决定，建议 `gpt-5.6-terra / xhigh`，且 `applied=false`。

**当前结论：CLI 0.154.0 的原生子代理已能触发 audit hook；自动改写仍未验证。** 此样本没有
启用 `host_pre_dispatch_apply`，也没有让 hook 输出 `updatedInput`，不能据此开启 auto。

## 2026-09-12 21:33–21:37 +0800：受控 auto 与 audit 基线对照

为直接检验 `updatedInput`，在隔离 Git 目录
`/private/tmp/tier-guard-cli-auto-probe/repo` 内运行 `codex-cli 0.154.0` 的两次只读
`codex exec --json` 会话。两个会话都只要求主代理创建一名未 pin、不得调用工具的子代理；不把
任务原文写入本文。第一次临时安装的测试目录将 `codex-cli.pre_dispatch_apply` 设为 `true`，并以
`TIER_GUARD_MODE=auto` 运行；其唯一日志的 SHA-256 是
`5591657d490a930d1d7591ceb7ba4a9266bd3396901efc43c489e1e344c19c07`。

该 auto 记录确认 hook 已进入 `profile=auto`，`host_pre_dispatch_apply=true`，且 adapter 输出了
`updatedInput`（兼容字段 `applied=true`）；它建议 `gpt-5.6-terra / xhigh`。这条任务在工具输入中被父代理扩写，因而被
确定性分类器判为低置信度未知任务，不能当作 Luna 路由的正样本。

但这次会话的 JSON 事件只有 `collab_tool_call: wait`，其 `receiver_thread_ids=[]`；没有子代理
启动、完成或实际模型回执。为了排除是 `updatedInput` 破坏了派活，随即恢复生产目录
`pre_dispatch_apply=false`，安装版本 `0.1.1+codex.20260912213613`，以相同隔离目录运行一条
`audit` 基线。基线同样产生一条 `codex-spawn` 记录（`applied=false`），同时同样只有空的
`wait.receiver_thread_ids`；其唯一日志 SHA-256 是
`af423a03ff22ecbfec533e19a6edbbd8added9fe8dd25e268fa2e728e52b4ccf`。

**结论：这组 `codex exec` 非交互会话不能创建可观察的协作子线程，故不能作为 Task 7 的实际
子代理模型验收。** 它只证明 hook adapter 已输出 `updatedInput` 并将该动作标为 `applied=true`，
不证明 CLI 已采纳，也不证明子代理实际以目标模型开始执行；auto 与 audit 的空接收者基线排除了把该缺失归咎于
`updatedInput`。生产 catalog 已恢复为 `pre_dispatch_apply=false`，Task 7 继续保持未验证。

## 2026-09-12 22:12–22:16 +0800：交互式参数改写回执（CLI 0.154.0）

本次以真正交互式 `codex-cli 0.154.0` 重做协议，并将 hook 日志放到每次会话唯一的临时目录。
为排除“装了错误快照/读了错误目录”，v2 记录新增 `catalog_identity`：只存来源类别与实际被解析
字节的 SHA-256，不存目录路径、任务原文或环境变量值。

先用生产安全快照 `0.1.1+codex.20260912223001` 做 audit 基线：catalog 指纹为
`69d643d7de9a315928bad8d1fc7e8c1de077f6e5e75f8c43f10e34822ede0970`，
`catalog_identity.origin=default`、`host_pre_dispatch_apply=false`、`applied=false`。会话
`01a095f6-b029-7f10-8c29-0bdd16858d46` 的 SQLite 线程回执显示父与子均为
`gpt-5.6-terra / high`，证明 audit 没有改变派发参数。

随后只在临时测试快照中把 `codex-cli.pre_dispatch_apply` 设为 `true`，安装版本
`0.1.1+codex.20260912223501`。安装缓存与测试 catalog 的 SHA-256 均为
`7ea7f99ad6a397cc5d0b7140a49b0167f0f637cc6bde35f5bc113ead19597d6e`，故不是旧缓存。
在 `TIER_GUARD_MODE=auto` 下，交互会话
`01a095f9-bb9f-7ba1-b998-6169b7cdaed5` 的唯一 hook 记录为：

- `catalog_identity={origin: default, sha256: 7ea7…97d6e}`；
- `profile=auto`、`host_pre_dispatch_apply=true`、`applied=true`；
- adapter 输出目标 `gpt-5.6-terra / xhigh`；
- 本地 SQLite 的实际子线程回执为 `gpt-5.6-terra / xhigh`，父线程仍为
  `gpt-5.6-terra / high`，子线程 CLI 版本为 `0.154.0`。

TUI 显示 `Completed /root/auto_apply_receipt`，无宿主错误。因 hook 仅保存任务指纹，本文不记录
任务原文；该次任务指纹是
`9d76d8e6f4c0d991373f4cff1856c63a8399bc19b61d803a885e9b2963e1bb54`。

**结论（限定范围）：Codex CLI 0.154.0 已验证在真实交互式子代理派发前采纳
`updatedInput`，且不会改变父代理。** 这解决了此前“CLI 是否支持这种插件能力”的宿主能力疑问。
不过原生 `collaboration.spawn_agent` 在 hook 边界把子任务 `message` 替换成 204 字符的不透明宿主令牌，
并非可供分类的任务明文。守卫不尝试解码，故按低置信度未知任务的保守策略正确选择 `terra/xhigh`；
它不是实际选择 `luna/medium` 的低成本样本。因此 Task 7 的“低成本子代理实际执行”
验收仍未完成，不能据此声称动态降档质量已验证。

测试结束后立即恢复生产 catalog `pre_dispatch_apply=false`，并重装
`0.1.1+codex.20260912224001`；其安装缓存指纹已复核回安全值 `69d643…e0970`。

后续审计版本将这类输入标为 `task_visibility=opaque_token`，与普通可见文本的 `visible` 区分；
记录仍只保留长度和 SHA-256，不保存令牌或任务原文。

## 2026-09-13 00:54–00:55 +0800：真实 TUI 的主代理明文预路由三档验收

使用 `scripts/codex-cli-preroute-smoke.sh` 在隔离 Git 目录内启动持续交互式 `tmux` PTY 与
`codex-cli 0.154.0`；这不是 `codex exec`、CI 或短生命周期的非交互终端 harness。父线程
`01a0968a-d328-7960-8fa1-13d775958a59` 实际为 `gpt-5.6-terra / high`。TUI 逐一显示三个 child
的 `Started` 与 `Completed`，最终仅交回下列固定文本：

| child | SQLite 实际线程 | 实际参数 | 固定回执 | 审计指纹 |
|---|---|---|---|---|
| A | `01a0968b-0ca3-79c3-b6ec-257de402cc8e` | `gpt-5.6-luna / medium` | `CLI_PREROUTE_LUNA_OK` | `89cc51fcae7c39021e6c68addcc8f42eb3a9f2322b415944bffc20168882fa26` |
| B | `01a0968b-3085-75c1-8aaa-8133d990c874` | `gpt-5.6-terra / high` | `CLI_PREROUTE_TERRA_OK` | `a6b65e656a01b05eed028fc242390abaf638dfc1b97eb6bfb7d9a72764931394` |
| C | `01a0968b-512c-7a33-9d11-f57234e1bdaf` | `gpt-5.6-terra / xhigh` | `CLI_PREROUTE_XHIGH_OK` | `8991f0812e2851f0902c36190cf9cefe8259dd72b041b020b8899cd15f6cb6e6` |

唯一审计目录中恰有这三条 `codex-spawn` 记录：每条是显式 pin、
`task_visibility=opaque_token`、`host_pre_dispatch_apply=false`、`applied=false`，且 `requested`
恰为表中的实际参数。生产 catalog 的指纹保持 `69d643…e0970`，没有测试目录或临时 auto 配置泄漏。

**结论需要分开读：** CLI 的主代理明文预路由（包括最低成本的 `luna/medium`）已实际验证；这同时证明
原生 hook 在这条调用上可以审计 pin 而不改写它。Task 7 原定义要求 hook 在无 pin 的原生 V2 输入中
独立按语义选择低成本候选；由于输入仍是不透明令牌，该更强的验收仍受上游边界阻塞，不能把本节写成
hook 自动路由通过。
