# spec-guard `build-task-dispatch` 验收：主干开发流程接上 tier-guard

> 历史记录：本文的版本、默认模式、型号、价格、路径和发布状态以记录日期为准。当前使用说明见 [README](../../README.md)，现行宿主能力及限制见 [兼容性](../compatibility.md)。原始实验结果保留。

> 状态：**接入成立；第三轮（`ac85154`）顺序规则在提交受阻场景下守住**　｜　日期：2026-10-05　｜　spec-guard PR haigeerlab/spec-guard-plugin#192
> （分支 `claude/build-task-dispatch`）　｜　agent-skills `0.6.11` · tier-guard `0.2.4`

## 背景

[真实测试](2026-10-05-agent-skills-build-real-run.md)确认 agent-skills 的 `/build` 从不派子代理，主干开发流程里
tier-guard 没有入口。应 tier-guard 会话的需求，spec-guard 新增可选的约定块规则段（`setup-convention.sh local --dispatch`，
默认关闭），引导主代理在 `/build` 时把每个非 Checkpoint task 交给一个子代理（只做 RED → GREEN → 回归 → 构建），
派活 prompt 另起一行写 tier-guard 档位标记；验收 diff、提交、勾选留给主代理。本文是 tier-guard 会话执行的两轮验收。

## 方法（两轮相同）

- `git archive <commit> plugins/spec-guard` 只读导出插件，不动 spec-guard 工作树。
- 两个一模一样的消费者项目，种子与真实测试相同（textkit 两个 task），约定块用 `setup-convention.sh local --dispatch` 安装。
- `claude -p --setting-sources project,local --model sonnet`，不加载用户级配置。**A** 加载 agent-skills + spec-guard +
  tier-guard；**B** 不加载 tier-guard。`/build auto` → `--continue` 回复 `approve`。
- 权限：`acceptEdits` + 白名单 `Bash(python3:*)`、`Bash(git:*)`（两轮保持不变）。
- 判定依据：主会话与子代理 transcript 的工具调用、tier-guard 审计日志、git 历史、测试结果；不采信主代理自述。

## 第一轮：`b200f39`

| 标准 | 结果 | 证据 |
|---|---|---|
| 1. 每个非 Checkpoint task 恰一次 Agent 派活 | ✅ | A、B 各 2 次，Task 1 / Task 2 各一次 |
| 2.（原文）`upstream_tier.status=accepted`，`tier_source` 为 upstream 或 floor | ⚠️ 字面不通过 | A：`accepted/L2`，但 `tier_source=pin`——主代理同时显式传了 `model: sonnet` |
| 3. 实际模型与档位对应 | ✅ | L2 → `claude-sonnet-5-5`（2/2） |
| 4. 每个 task 一次主代理提交，测试全过 | ✅（附说明） | 3 个提交、各只含该 task 文件；子代理零 git 命令；8 测试通过。主代理把「提交 Task 1」与「派 Task 2」放在同一轮，提交被白名单拦下后手动拆分 |
| 5. 不装 tier-guard 照常走完 | ✅ | B 2 次派活、3 个提交、测试全过 |

第 2 条是 tier-guard 会话写的标准有误：装了 `tier-routing` 的主代理会同时 pin，而 guard 下不 pin 的首次派活会被拦，
pin 几乎必然发生。spec-guard 方采纳改写为「请求的模型与标记档位对应，`tier_conflict` 若出现须由 floor 解释」，按此判通过。
另观察到 B 标 L1、A 标 L2：B 没有 `tier-routing`，档位无统一依据。

## 第二轮：`10717c8`（规则段补两处文字后，只复验第 4 条）

改动：第二项末尾加「上一个 task 提交、勾选完再派下一个」；档位括号内联三档定义（L1 机械只读；L2 单模块、验收明确；
L3 跨模块、有歧义、高风险或不可逆；有 `tier-routing` 时以它为准）。

**A（装 tier-guard）——第 4 条不通过：违反一次后自行纠正。** transcript 工具调用顺序（UTC）：

| # | 时间 | 调用 |
|---|---|---|
| 1 | 09:52:12 | Agent 派 Task 1（`tier=L2`，`model: sonnet`） |
| 2 | 09:52:32 | Bash `sed -i … todo.md && git add … && git commit …` —— **被拦**（复合命令中 `sed` 需审批） |
| 3 | 09:52:35 | **Agent 派 Task 2**——此时 Task 1 尚未提交、勾选 |
| 4 | 09:52:40 | TaskStop 停掉该子代理（未留改动） |
| 5 | 09:52:50–53 | Edit 勾选 Task 1 → git add → git commit |
| 6 | 09:52:57 | Agent 重新派 Task 2 |
| 7 | 09:53:14– | 勾选 → 提交 Task 2 → Checkpoint 勾选并提交 |

最终 3 个提交正确、8 测试通过；但 Task 2 实际有 2 次派活，第 1 条在 A 上也不再满足。tier-guard 记了 3 条派活
（均 `accepted/L2`、`requested=sonnet`、`tier_source=pin`、无冲突），被停的那次没有结束记录。

**B（不装 tier-guard）——第 4 条通过。** Task 1 完成后主代理以「spec 未定义 slugify 是否仅 ASCII」为停止条件在提交前
问人（测试操作者选「仅 ASCII」）；之后提交同样被 `sed` 拦下，改用 Edit 勾选再提交（09:53:54–57），**然后**才派 Task 2
（09:54:03）。3 个提交、8 测试通过。

**档位**：A 仍为 L2；B 两个 task 都标 L2（第一轮为 L1）——内联三档定义使无 tier-guard 时的判断与有时一致。

## 第三轮：`ac85154`（规则段再补一句后，复验第 4 条）

改动：第二项末尾改为「上一个 task 提交、勾选完再派下一个，**提交受阻时先解决提交或停下问人，不派下一个**」。
方法与白名单完全不变，目的就是复现「提交受阻」。

| 项目 | 拦截是否发生 | 被拦后的下一次工具调用（UTC） | Agent 派活 |
|---|---|---|---|
| A（装 tier-guard） | ✅ 10:05:00 提交命令被拦（`sed -i`） | 10:05:04 Edit 勾选 Task 1 → 10:05:06 git add → 10:05:09 git commit → **10:05:14 才派 Task 2**；无 TaskStop | 2（各一次） |
| B 第一次运行 | ❌ **未测到**：Task 1 的子代理跑测试时 Bash 被整体拒绝（10:04:34），子代理交回、主代理停下问人——符合规则，但停在提交之前 | — | 1（未走完） |
| B 重跑（全新项目，同一约定块与参数） | ✅ 10:07:41 提交命令被拦 | 10:07:44 Edit 勾选 → 10:07:47 git add → 10:07:51 git commit → **10:07:56 才派 Task 2**；无 TaskStop | 2（各一次） |

B 第一次运行未覆盖目标场景，**不计为通过**，故用全新项目重跑一次。B 重跑的主代理在总结里写「Blockers: None came up」，
与 transcript 中的拦截不符——再次说明只能以 transcript 为准。

tier-guard 日志（A）：两条派活 `upstream=accepted/L2`、`requested=sonnet`、`tier_source=pin`、无冲突；实际
`claude-sonnet-5-5`（2/2）。A 与 B 重跑均 3 个提交、8 测试通过；A、B 档位都为 L2。第 3、5 条无变化。

## 结论

- **接入成立**：在开启规则的项目里，`/build` 的每个 task 都经 Agent 工具派出、档位标记送达 tier-guard 并被采纳、
  实际执行模型与档位一致；不装 tier-guard 时流程照常。主干开发流程第一次真正用上了 tier-guard。
- **顺序规则**：第二轮（`10717c8`）里 A 在提交受阻后先派了下一个、事后用 TaskStop 纠正；第三轮（`ac85154`）把「提交受阻
  时先解决提交或停下问人，不派下一个」写进规则后，A 与 B（重跑）在提交被拦时都先勾选、提交，再派下一个，未再复现。
  每个场景仅一个样本，只能说本轮未复现，不能保证不再发生；spec-guard 方已决定若再犯则作为已知限制接受、不加 hook。
  受阻均由测试环境白名单触发（交互会话中会弹审批而非直接失败）。
- **对 tier-guard 的启示**：在开启规则的项目里，tier-guard 的价值主要体现为档位标记被记录、pin 与档位一致可审计；
  `tier_source` 几乎总是 `pin`，因为主代理会按 `tier-routing` 自行传参。
