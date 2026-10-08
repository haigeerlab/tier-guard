# Claude Code CLI v2 端到端验收：实际执行未入账

> 历史记录：本文的版本、默认模式、型号、价格、路径和发布状态以记录日期为准。当前使用说明见 [README](../../README.md)，现行宿主能力及限制见 [兼容性](../compatibility.md)。原始实验结果保留。

> 运行：2026-09-13 03:39 +0800（日志 UTC `2026-09-12T19:39`）
>
> 宿主：Claude Code CLI，父会话 `claude-opus-5`，session `b306a907-703f-4854-93ba-460743e0e91d`
>
> 被测插件：marketplace 安装的 `0.1.1`（`be1ecb3`）

## 结论

- Claude Code 完整验收**未通过**，不能据此把 A/B/C/D 判为自动路由成功。
- 产品缺陷：v2 路径直接跳过 `SubagentStop`，报告的「实际执行」恒为「未观测」。已在工作树修复，尚未发布。
- 这一轮没有发生改写：报告的 mode 是 `audit`（来源：环境变量 `TIER_GUARD_MODE`），5 条记录 `applied` 全为 `false`。
- A/B 被保守建议为 Opus，原因是任务文本没有命中目录标记；日志信号不支持「父提示词污染」这一假设。

## 方法

一个父会话依次派出 4 个 `general-purpose` 子代理：A/B/C 未传 `model`，D 显式传 `model: "sonnet"`。
判据只用 `decisions.jsonl`、父会话 transcript、子代理 transcript 与 `.meta.json`，不看模型自述。
下表只保留长度与指纹，不保存任务原文。

## 观测

| 子代理 | `tool_use_id` | 字数 / sha256 前 16 位 | 信号 | confidence | 建议 | pinned | applied | 实际模型（子代理 transcript） |
|---|---|---|---|---|---|---|---|---|
| A | `toolu_01Nhnbm4ZViYbXhkmqst4a5f` | 49 / `9fca6306a3a1e6b0` | 全部 `unknown` | low | opus | false | false | `claude-opus-5` |
| B | `toolu_01S3PRvLSs3xfRwBQmcDSJRC` | 172 / `e9b5e0988b36b2d3` | 仅 `decision_load=implementation` | low | opus | false | false | `claude-opus-5` |
| C | `toolu_01HYP5AfKrDNCEZ9AbPXE41j` | 62 / `c0af94712e1aafce` | `cross_cutting` + `tradeoff` | medium | opus | false | false | `claude-opus-5` |
| D | `toolu_01N23XHgkJ6geHafwRmTXdie` | 39 / `a264f69a23a765a2` | 全部 `unknown` | low | opus（raise） | true | false | `claude-sonnet-5` |
| 额外 | `toolu_01Cg5FmD9mTPaAABYyEa8kNT` | 62 / `c0af94712e1aafce` | 同 C | medium | opus | false | false | 无对应子代理 |

## 发现

1. **v2 跳过 SubagentStop。** `hooks/claude_hook.py` 的 v2 分支只处理 `agent` 事件；
   `hooks/tier_report.py` 读的是 agent 记录上从不存在的 `actual_execution`。
   Task 6 的「Reports separate selected, requested and actual」对 Claude v2 实际没有数据来源。
2. **额外记录不是第 5 个任务。** 它的任务指纹与 C 完全相同，但 `tool_use_id` 既不在父会话 transcript，
   也不在 4 份子代理 transcript 中：宿主为同一次 C 派发触发了一次 `PreToolUse`，该 `tool_use` 没有落盘，
   也没有产生子代理。结论按指纹与 id 得出，不按时间推断。
3. **分类保守是因为文本没命中标记。** A 的「只读任务」「不得读写文件」都不在 `readonly_markers` 中；
   B 有「实现」，但没有「只动」，且「验收」不在行首。两者都走 low 置信的保守分支。
   如果是父提示词污染，信号里应出现 `tradeoff` / `cross_cutting`，实际没有。
4. **mode 来源。** 报告显示 `audit`，来源是环境变量 `TIER_GUARD_MODE`，所以即使宿主闸门为 `true` 也不会改写。

## 修复（工作树，未发布）

- `hooks/claude_hook.py`：新增 `on_subagent_stop_v2`。model 只取子代理 transcript 中宿主写下的值；
  宿主不提供 effort，记 `None`；按 `.meta.json` 的 `toolUseId` 关联；只记 prompt sha256；
  不写 decision；永不输出；mode 为 `off` 时不记。
- `hooks/tier_report.py`：「实际执行」只按 `tool_use_id` 严格关联 SubagentStop 记录。
- 回归：`hooks/test-tier-guard.sh` 新增 6 条，`hooks/test-tier-commands.sh` 新增 2 条（先红后绿）；
  `scripts/mutation-check.py` 新增 5 个变异，全部被抓到；`scripts/validate.sh` 退出码 0。
- 真实数据回放：把本轮 4 份子代理 transcript 喂给修复后的 hook，只写入临时数据目录。
  报告「实际执行」为 A/B/C=`claude-opus-5`、D=`claude-sonnet-5`，额外记录仍为「未观测」。

## 重测前提

- 被测代码必须包含上述修复：用 `--plugin-dir` 加载工作树，或发布新版本后更新安装。
- 新会话以 `TIER_GUARD_MODE=auto` 启动，先用 `/tier-guard:tier-mode` 确认来源为环境变量，再派子代理。
- 每个子代理的任务文本必须逐字命中生产目录的标记。以下由 `route()` 对生产 v2 目录核对（中英文各一版结果相同）：

| 样本 | 必须命中 | auto 下的决定 | confidence |
|---|---|---|---|
| A | 只读标记（如「禁止修改任何文件」/ `read-only task`）+ 行首「验收」/ `Acceptance` | select haiku | high |
| B | 实现标记（「实现」/ `implement`）+ 范围标记（「只动」/ `only touch`）+ 行首验收 | select sonnet | high |
| C | 取舍词（如「取舍」/ `tradeoff`） | select opus | medium |
| D | 同 A，且显式 `model=sonnet` | pinned，不改写，建议 haiku | high |

## 2026-09-13 12:38–12:44 +0800 复测：主代理预路由与自然触发

### 方法

- Claude Code CLI `2.1.270`，`claude -p`：用 `--plugin-dir` 加载含修复的工作树，
  `--settings '{"enabledPlugins":{"tier-guard@tier-guard":false}}'` 停用已安装的 0.1.1 快照；清掉父会话的
  `CLAUDE_*` 会话变量；`TIER_GUARD_MODE=audit`，每轮使用独立日志目录；工具只放行 `Agent,Skill,Read`。
  父模型用 `sonnet`：A 必须显式降档、C 必须显式升档，才能和继承父模型区分开。
- Codex CLI `0.154.0`：沿用 `scripts/codex-cli-preroute-smoke.sh` 的交互式 TUI 协议，在 tmux PTY 中运行已安装快照；
  父模型 `gpt-5.6-terra / high`，`TIER_GUARD_MODE=audit`。
- 「点名」提示词与 Codex 既有 smoke 逐句对齐：点名 tier-routing，并写明每个 child 的能力类别。
  「自然」提示词只描述三件事——核对逗号分隔项、写 `add(a, b)`、比较两种生产库 schema 变更的风险/成本/回滚——
  不出现 tier-routing、模型、成本或类别词。所有 child 都禁止使用工具、只回复固定文本。
- 探针（session `5aa9c2e7-97dd-45e3-90f9-bc49dbcddfb9`）确认：每个 `tool_use_id` 只有一条 agent 记录
  （已安装快照确实停用）、catalog 指纹等于工作树、SubagentStop 记录可以入账。

### Claude：点名 tier-routing 的主代理预路由 —— 通过

| 轮次 | session | child | 主代理显式传入 | hook（audit） | 实际模型 |
|---|---|---|---|---|---|
| 1 | `51f28c42-10ba-4369-8b0e-22caabcc8e1e` | A `toolu_01Q7ymbwyD2fmFv8NLBLizA7` | `haiku` | pinned，建议 haiku | `claude-haiku-4-5-20251001` |
| 1 | 同上 | B `toolu_01Uj3oUDwXEoDFVsiKvSjcy7` | `sonnet` | pinned，建议 opus（raise） | `claude-sonnet-5` |
| 1 | 同上 | C `toolu_01ECM2SF3pFSFQqLTGYVS76C` | `opus` | pinned，建议 opus | `claude-opus-5` |
| 2 | `f30ad206-8436-4938-afae-c20cd4d16933` | A `toolu_01RKCi8ABeTXgMUKNwHmoTAe` | `haiku` | pinned，建议 haiku | `claude-haiku-4-5-20251001` |
| 2 | 同上 | B `toolu_01MkiBHt2SZ9kLrLLoa3y54X` | `sonnet` | pinned，建议 opus（raise） | `claude-sonnet-5` |
| 2 | 同上 | C `toolu_01DDdtLDwvH84jFJFSobZ2GZ` | `opus` | pinned，建议 opus | `claude-opus-5` |

两轮父代理都先调用了 `Skill(tier-guard:tier-routing)`，再逐个显式传 model；父代理始终是 `claude-sonnet-5`。
hook 把显式 model 视为 pin，一律不改写。B 的 raise 建议来自 hook 的字面标记分类（任务文本没有「只动」类标记），
与主代理按 skill 做的语义判断不一致；pin 语义保证了主代理的选择不被覆盖。

### 自然触发（不点名 tier-routing）—— Claude 与 Codex 均未通过

| 宿主 | 父代理 | child 请求参数 | 实际参数 | skill 是否被调用 |
|---|---|---|---|---|
| Claude（session `f8ecbf92-c282-49e6-89bf-d74fc26f66e6`） | `claude-sonnet-5` | 三次都没传 model | 三个都是 `claude-sonnet-5`（继承） | 否 |
| Codex（父线程 `01a0990f-82c6-7290-901f-e6231c833b53`） | `gpt-5.6-terra / high` | 未传 | 三个 child `01a0990f-adf9…`、`01a0990f-d4ea…`、`01a0990f-f764…` 都是 `gpt-5.6-terra / high`（继承） | 否 |

Claude hook 对三条都记 `select opus`、置信度 low（文本没命中标记）；Codex hook 三条都是 `opaque_token`，
建议 `terra/xhigh`，`applied=false`。两边的 child 都完成了固定回复。

**结论：** 目前的动态路由依赖主代理主动使用 tier-routing。被明确要求时，两个宿主都能按任务降档、保持或升档；
没被要求时两个宿主都不会自发使用，子代理一律继承父代理参数。Codex 此前的三档回执属于「点名」场景，
不能外推为自然使用下的满足。

### SubagentStop 竞态（真实宿主实测）与修复

首轮点名测试 3 条 stop 记录里有 2 条、自然测试里有 2 条的 hook 时刻实际模型为空，而事后读 transcript 都有 model。
规律：取不到的 transcript 只有一条 assistant 行（`text`）；取到的在 `text` 之前还有一条先落盘的 `thinking` 行；
stop 记录时间与 transcript 修改时间在同一秒。SubagentStop payload 本身不带 model
（字段见 [`p0 spike evidence`](2026-09-11-p0-spike-evidence.json)）。

修复：stop 记录增加 `agent_transcript_path`（只有路径，没有内容）；`hooks/tier_report.py` 遇到实际模型为空但有路径时，
在生成报告时回读同一 transcript。回归新增「触发时未落盘、事后补上」用例，先红后绿；变异测试新增 2 个，全部被抓到。
第 2 轮点名测试在真实宿主上再次出现 hook 时刻 2/3 为空，报告回读后三条实际执行全部为正确模型。

### 费用（`claude -p` 的 `total_cost_usd`）

探针 0.0685；点名第 1 轮 0.3641；自然 0.3046；点名第 2 轮 0.3266。Codex 本轮用量未从宿主取得，未知即未知。
