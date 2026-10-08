# Codex 桌面版原生 hook 冒烟：人工验收协议与结果

> 历史记录：本文的版本、默认模式、型号、价格、路径和发布状态以记录日期为准。当前使用说明见 [README](../../README.md)，现行宿主能力及限制见 [兼容性](../compatibility.md)。原始实验结果保留。

> 状态：**audit hook 已验证；自动参数改写未验证**　｜　插件：tier-guard 0.1.1　｜　日期：2026-09-12

> 本文保留 matcher 修正前后的历史冒烟证据与旧 C1 协议；当前 v2 宿主状态、Desktop 明文预路由
> 三档实际回执及不透明输入边界，以
> [v2 compatibility status](2026-09-12-v2-compatibility-status.md) 为准。下方 C1 的 T1→T2
> dry-run 字段属于 v1 历史协议，不能用于验证或描述当前“最低成本合格候选”路由。

## 2026-09-12 20:20 +0800：更正后的有效原生复测

此前的负向样本使用的 matcher 没有覆盖 Codex V2 投递的扁平工具名
`collaborationspawn_agent`，因此“没有记录”不能再被解释为 Desktop 绕过 hook。安装
`0.1.1+codex.20260912195543` 后，插件以一个严格 matcher 同时覆盖 `spawn_agent`、
`collaborationspawn_agent` 及带分隔符的 namespace 形式。

用户在 ChatGPT 桌面版 26.908.40834 / 内嵌 Codex 0.154.0-alpha.6.2 的原生界面发起一条
无 pin、只读子代理任务后，默认数据目录新增 v2 `codex-spawn` 审计记录：时间
`2026-09-12T12:20:06+00:00`、session ID `01a0958f-6112-7030-aaf9-7964c4282e8e`、任务
指纹 `fc799b5fc87287c1d37406a8eec81a9ae0ed2ad0db26c21fe166477f8de43f8b`。该记录没有保存
任务原文，`applied=false`，并按当前 catalog 记录了建议目标 `gpt-5.6-terra / xhigh`。

**当前结论：Desktop 的原生派活已进入 audit hook。** 这不能证明自动路由：本次没有让 hook
输出 `updatedInput`，也没有“实际子代理参数已被改写”的可观察回执。因此
`host_pre_dispatch_apply` 仍为 `false`，Desktop 仍只能建议式运行。

## 历史负向样本（已被 matcher 更正取代）

桌面版并非没有加载插件：`Codex Desktop/0.153.4` 的 `hooks/list` 返回 tier-guard
的命令 hook 为 `enabled: true`、`trustStatus: "trusted"`，并指向安装目录中的
`tier-guard-codex.sh`。

随后在同一 desktop app-server 会话中，使用 `gpt-5.6-terra` / `high` 发起一次真实
子代理派活。会话记录的函数调用是 `namespace: "collaboration"`、`name:
"spawn_agent"`，并产生了 `subAgentActivity`。但该调用前后没有 tier-guard 的
`PreToolUse` hook 事件，`decisions.jsonl` 的 `codex-spawn` 计数仍为 1（旧的 CLI
记录），没有新增记录。

当时的历史结论是：**桌面版会加载并执行插件 hooks，但其 collaboration 派活通道不经过
`PreToolUse`。** 此结论已被本文 20:20 的 matcher 修正复测推翻；它源于未覆盖扁平 V2
工具名，而不是安装、信任或路由器判据失败。

## 2026-09-12：桌面版 26.908.40834 有效复测

应用包版本经只读核对为 `26.908.40834`；其内置
`/Applications/ChatGPT.app/Contents/Resources/codex --version` 为 `0.154.0-alpha.6.2`。
这不是此前桌面证据中的旧运行时。内置 Codex 的插件清单将
`tier-guard@tier-guard 0.1.1+codex.20260912105710` 标为 `installed: true`、`enabled: true`；
其 PreToolUse hook 在本机配置中也为 `enabled: true` 且已有 trusted hash。

在该原生桌面会话中发起一次无 pin 的 `collaboration.spawn_agent`，任务带唯一标记
`TG-DESKTOP-26.908.40834-6ca9`，只要求只读判断当前目录是否为 Git 仓库。子代理实际回复
`yes`，因此派发已发生且完成。派发后只读检查
`~/.codex/plugins/data/tier-guard-tier-guard/decisions.jsonl`：仍为 **1 行**、888 字节，mtime
仍是 `2026-09-12T14:05:55+0800`；没有新增 v2 `codex-spawn` 记录。

**当时的初步结论：桌面 26.908.40834 / Codex 0.154.0-alpha.6.2 未向 tier-guard 的当时
matcher 投递可见 `PreToolUse`。** 该 matcher 后来证实遗漏了扁平 V2 工具名；此段已由本文
20:20 的有效复测取代，不能再作为 Desktop 绕过 hook 的证据。

## 已失效的 C1 协议（保留作历史记录）

验证 ChatGPT.app 的**原生** Codex 会话是否会在派活前调用 tier-guard 的
`PreToolUse` hook。唯一判据是数据目录新增的一条 `codex-spawn` 记录；界面文案、
子代理自述和模型回复都只是辅助记录。

下述协议反映的是 matcher 修正前的假设，**不得重跑或据此下结论**。当前已知事实是原生
`collaboration.spawn_agent` 可进入 audit hook，但其 `message` 对 hook 为不透明令牌；新验收
应按 [v2 compatibility status](2026-09-12-v2-compatibility-status.md) 的现行边界执行。

## 准备与基线

1. 确认已安装并启用当前 `tier-guard@tier-guard` 快照；不要假定固定版本号或缓存路径。
2. 在运行前记录 `~/.codex/plugins/data/tier-guard-tier-guard/decisions.jsonl` 的行数、
   修改时间和最后一条的 `ts`。不要编辑、清空或复制此目录中的文件。
3. 新建一个 ChatGPT.app 的 Codex 会话。测试目录由桌面应用决定；记录实际 cwd，不把
   它是否等于 scratch 目录当作 hook 判据。
4. 截图证据显示桌面命令菜单未列出 `/hooks`；官方文档把 `/hooks` 描述为 CLI 入口。
   这不足以推出桌面不支持或 hook 未信任。此前的 API 测试也不进入 `PreToolUse`，因此本协议
   仍等待能观察桌面原生 hook 事件的办法。

## 原生执行步骤

1. 若桌面存在 hook 审核入口，记录其原文并只信任 tier-guard 的 `PreToolUse` / `spawn_agent`
   项；不要使用 “trust all”。菜单未列 `/hooks` 时，先记录截图，不据此给出支持性结论。
2. 让该会话从**原生界面**调用一次 `spawn_agent`，并使用 `desktop-cases.md` 中的 C1
   message、`gpt-5.6-terra` 与 `high`。不要通过协作 API、任务 API 或外部编排层触发。
3. 记录界面 `Spawned …` 行原文、子代理最终回复、弹框错误（若有）和起止时间。
4. 只读核对日志：

   ```bash
   python3 "$HOME/.codex/plugins/cache/tier-guard/tier-guard/<当前快照>/hooks/tier_doctor.py" \
     --data "$HOME/.codex/plugins/data/tier-guard-tier-guard"
   ```

   再用 `desktop-expect.json` 的 C1 SHA-256 对照新增记录，不能用 prompt 原文或子代理
   自述替代这一步。

## 历史 C1 的期望事实（v1 dry-run，非当前 v2 判据）

| 日志字段 | 期望 |
|---|---|
| `event` | `codex-spawn` |
| `actual` | `gpt-5.6-terra` / `high` |
| `decision.start_tier` → `tier` | `T1` → `T2` |
| `decision.action` / `target_reasoning_effort` | `raise` / `xhigh` |
| `applied` | `false` |

因此，界面子代理仍应显示 `high`：dry-run 只留下建议，不改实际参数。

## 历史 C1 的失败分流（非当前验收）

| 观察到的事实 | 结论与下一步 |
|---|---|
| 桌面菜单没有等效信任入口 | 证据不足：记录截图并继续查桌面原生 runtime，不得用协作 API 作为补测。 |
| 有审核页但没有 tier-guard | 安装态或新会话加载有问题；记录页面，勿用协作 API 补测。 |
| 有 hook 但未被信任 | 不是路由器失败；仅信任该条后重开新会话。 |
| 已信任、原生 spawn 有活动、日志未新增 | 这是宿主调用链问题。保留时间、UI 文案、cwd、版本和日志基线，停止重试。 |
| 新增 C1 SHA 对应记录，字段如上 | 本条原生桌面 hook 验收通过。 |

任何结果都写入 `desktop-run.md`，只记录事实，不在执行记录中自行判定整体通过与否。
