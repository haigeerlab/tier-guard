# 主代理预路由提醒：真实宿主端到端（Task 10 / 11）

> 历史记录：本文的版本、默认模式、型号、价格、路径和发布状态以记录日期为准。当前使用说明见 [README](../../README.md)，现行宿主能力及限制见 [兼容性](../compatibility.md)。原始实验结果保留。

> 运行：2026-09-13 15:46–15:54 +0800
>
> 宿主：Claude Code CLI `2.1.270`（`claude -p`）；Codex CLI `0.154.0`（tmux 交互式 TUI）
>
> 被测：工作树（Task 9–11 已验收）。Claude 经 `--plugin-dir` 加载；Codex 装临时快照
> `tier-guard@tier-guard-e2e` `0.1.1+codex.20260913154558`（目录指纹 `1ccfb63d…`，`codex_hook.py`
> 与工作树同为 `51b964d1…`）。生产目录未改，两个宿主的 `dispatch_nudge` 只在临时目录里为 `true`。

## 方法

- 提示词与 [`Claude CLI v2 e2e`](2026-09-13-claude-cli-v2-e2e.md) 的「自然」版相同：三件事（核对逗号分隔项、写
  `add(a, b)`、比较生产库 schema 变更的风险/成本/回滚），不出现 tier-routing、模型、成本或类别词；child
  一律禁止工具、只回复固定文本。
- 判据只用 hook 日志、父会话转录 / rollout、Claude 子代理转录和 Codex `state_5.sqlite` 回执，不看模型自述。
- Claude：父模型 `sonnet`，临时目录 `claude-code.dispatch_nudge=true`（指纹 `66206321…`），已安装的 0.1.1
  经 `--settings` 停用。
- Codex：父模型 `gpt-5.6-terra / high`；hook 审核页逐条核对来源与命令路径后，只信任
  `tier-guard@tier-guard-e2e` 这一条。

## Claude Code CLI

| 场景 | session | 派活（按顺序） | hook `nudge` | 实际模型 |
|---|---|---|---|---|
| audit | `8bac593f-2c5f-415c-8e5a-bbe4ec2dcd62` | 3 次均未传 model | reminded ×3 | 3 个都是 `claude-sonnet-5`（继承） |
| auto | `cf7aa8d1-bcfa-408c-9b61-925d1ee8aed9` | ① 未传 model → **被拦**；② 调用 `Skill(tier-guard:tier-routing)`；③④⑤ 显式 `haiku` / `sonnet` / `opus` | denied ×1，之后 none ×3（pin） | `claude-haiku-4-5-20251001` / `claude-sonnet-5` / `claude-opus-5` |

- **audit 提醒：送达但未被采纳。** 父转录里有 3 条 `hook_additional_context` 附件（与每次派活同一时刻），
  所以宿主确实把提醒送进了主代理上下文；但提醒后的第 2、3 次派活仍然没有显式传 model。
- **auto 拦截：通过。** 被拦那次的工具结果即 deny 常量原文；主代理随即加载 tier-routing，重派三档全部显式、
  实际模型一致，同一会话之后没有再被拦。
- 新的 skill 描述（Task 9）在 Claude 自然使用下没有触发 skill 加载（audit 场景 0 次）。

## Codex CLI：自然使用下主代理已自行预路由

| 轮次 | 父线程 | child 实际参数（SQLite） | 原插件 hook | e2e hook |
|---|---|---|---|---|
| 信任前（作废，见下） | `01a099bd-299c-7f53-9d01-c25872582f6f` | `luna/medium`、`luna/medium`、`terra/xhigh` | 3 条，pinned | 未信任，未运行 |
| audit | `01a099c0-5f91-7ba0-a2c6-c0985ad8d989` | `luna/medium`、`luna/medium`、`terra/xhigh` | 3 条，pinned | 3 条，`nudge=none`（pin） |
| auto | `01a099c0-6eb8-79c3-8952-fdae450dd829` | `luna/medium`、`luna/medium`、`terra/xhigh` | 3 条，pinned | 3 条，`nudge=none`（pin） |

- 三轮里主代理都在派活前读取了 tier-routing（TUI 显示 `Read SKILL.md (tier-guard:tier-routing skill)`；rollout 里
  出现的 skill 路径指向 e2e 快照），9/9 次派活显式传了 model 与 reasoning_effort；取舍类的 C 均为
  `terra/xhigh`，没有被降档。对照：同一提示词在 12:38（只有旧描述的 0.1.1 插件）三个 child 全部继承
  `terra/high`。旧描述在这几轮的 rollout 里仍然可见，所以「新描述触发」是强关联而非唯一归因。
- 因为每次派活都已 pin，e2e hook 正确地不提醒、不拦截；**Codex 的提醒 / deny 编码在这三轮里没有被触发**，
  其宿主采纳情况需另测。

## 偏差：`-c` 没有停用原插件的 hook

测试以 `-c 'plugins."tier-guard@tier-guard".enabled=false'` 启动，意在只让 e2e hook 生效。实际上原插件
`tier-guard@tier-guard` 0.1.1 的 hook 照常运行（hook 审核页显示其为 Trusted、Active；日志里目录指纹
`fec0067b…`、没有 `nudge` 字段的记录就是它写的）。因此：

- 第一轮在 e2e hook 被信任之前就开始派活，只有原插件 hook 运行，该轮不计入 hook 结论；
- 之后各轮两份 hook 都运行，按目录指纹与 `nudge` 字段区分记录。原插件在 audit 下不输出，不影响提醒 / deny。

## Codex：禁止使用 skill 的对照（15:53–15:55）

为触发 Codex 的提醒 / deny 路径，在同一自然提示词前加一句「不要读取、加载或使用任何 skill」，再各跑一轮：

| 场景 | 父线程 | 主代理行为 | child 实际参数 | e2e hook |
|---|---|---|---|---|
| audit | `01a099c2-7566-7130-8d2d-3c10d698981a` | 仍读取 tier-routing，3 次显式传参（`fork_turns: "none"`） | `luna/medium`、`luna/medium`、`terra/xhigh` | `pinned=True`，`nudge=none` ×3 |
| auto | `01a099c2-80cb-7e81-80ba-8884a7e9fb3a` | 未读取 skill，3 次都**没有**传 model / effort（`fork_turns: "all"`） | 3 个都是 `terra/high`（继承） | `pinned=False`，但 `nudge=none` ×3——**应为第一次 deny、之后提醒** |

两轮 rollout 里 `Tool call blocked by PreToolUse hook`、deny 文本、提醒文本出现次数都为 0；spawn_agent 参数只取键名与
非正文字段核对，没有读取 message 原文。

## 缺陷：Codex adapter 把原生 `fork_turns` 当成「判不出 pin」

`hooks/codex_hook.py` 的 `_codex_nudge_pin` 规定：任何取值为真的 `fork_*` 参数 → 返回 `None`（判不出，永不提醒）。
真实 Codex 0.154.0 的原生 `spawn_agent` **每次都带 `fork_turns`**，取值是字符串 `"all"` 或 `"none"`，两者都为真，
所以在真实宿主上提醒和 deny 永远不会触发。单元测试没有发现，是因为测试夹具按假设构造了「无 fork 参数」的输入，
而不是按真实宿主的参数形状。修复前需先确认 `fork_turns` 的语义以及它能否与 model / effort 同时传入，
否则提醒会把主代理引向一个宿主不接受的调用。

**源码确认（`openai/codex` tag `rust-v0.154.0`，`codex-rs/core/src/tools/handlers/multi_agents_v2/spawn.rs`）：**

- `SpawnAgentArgs::fork_mode`（约第 290–325 行）：`fork_turns` 取值只能是 `none` / `all` / 正整数字符串，
  缺省或空串按 `all`；`fork_context` 在 V2 中一律报错 `fork_context is not supported in MultiAgentV2; use fork_turns instead`。
- `handle_spawn_agent`（约第 127–135 行）：`apply_requested_spawn_agent_model_overrides` 在区分 fork 模式之前无条件执行，
  所以显式 `model` / `reasoning_effort` 对 `none`、`all`、`N` 都生效；没有针对 fork 的拒绝或忽略。
- 未显式传参时，子代理继承父代理当前的 model 与 effort——与 auto 对照轮 SQLite 回执的 `terra/high` 一致。

因此 `fork_turns` 与是否 pin 无关：修复是去掉「带 `fork_*` 即判不出」这条规则，按普通未 pin 派活处理。

**修复（工作树，尚未在真实 Codex 上复测）：** `_codex_nudge_pin` 只看显式 `model` / `reasoning_effort`。
`hooks/test-tier-guard-codex.sh` 把旧的「带 fork 不提醒」断言换成真实形状 `fork_turns: "all"`：audit 提醒、auto 新会话
deny——修复前 3 条失败（77 / 3），修复后 80 / 0；`scripts/mutation-check.py` 用「重新引入 fork 规则」替换旧变异体并被抓到，
`--only nudge` 符合预期 19 / 不符 0 / 锚点失效 0；`scripts/validate.sh` 退出码 0。

## 修复后复测（16:11–16:14）

快照 `tier-guard@tier-guard-e2e` `0.1.1+codex.20260913161142`：`codex_hook.py` 指纹 `b5bb53e8…` 与修复后的工作树一致，
目录指纹仍为 `1ccfb63d…`。hook 文件内容未变，沿用已有信任，没有出现审核页。提示词与上面「禁止使用 skill」对照轮相同。

| 场景 | 父线程 | e2e hook | 父 rollout | child 实际参数（SQLite） |
|---|---|---|---|---|
| audit | `01a099d3-79a0-7931-b915-564080093ce3` | `pinned=False`，`nudge=reminded` ×3 | 提醒文本 3 次；无 deny | 3 个都是 `terra/high`（继承） |
| auto | `01a099d3-835d-7ce2-bb1f-bacad8cd4145` | 第 1 次 `denied`，之后 3 次 `pinned=True`、`nudge=none` | `Tool call blocked by PreToolUse hook` 1 次，deny 文本 1 次；TUI 显示 `Blocked by hook` 与 deny 原文 | 3 个都是 `luna/low`（显式） |

- **宿主采纳：通过。** Codex 0.154.0 接受了只带 `additionalContext` 的提醒输出，并把文本送进主代理上下文；接受了
  deny + 非空原因，拦下本次派活并把原因展示给主代理；主代理随后带显式参数重派，同一会话没有再被拦。
- audit 场景主代理没有按提醒显式传参；该轮提示词禁止使用 skill，与提醒要求冲突，不能据此判断提醒在自然使用下的效果。
- **新风险：deny 后不加载 skill 会降档。** auto 轮主代理遵守了「不用 skill」，没有读取候选目录，就给三个 child 都传了
  `gpt-5.6-luna / low`：该组合不在生产候选目录中，且 C 是取舍类任务，违反「取舍类任务 0 次被降档」。
  deny 原因只要求加载 skill、本身不含候选目录，是这一问题的直接原因。

## 恢复

`codex plugin remove tier-guard@tier-guard-e2e` 与 `codex plugin marketplace remove tier-guard-e2e` 已执行：
`codex plugin list` 只剩 `tier-guard@tier-guard 0.1.1`（已安装、已启用），其缓存目录指纹仍为 `fec0067b…`。
`plugin remove` 留下的空目录 `~/.codex/plugins/cache/tier-guard-e2e` 已用 `rmdir` 删除。`config.toml` 里
`tier-guard@tier-guard-e2e` 的 hook 信任条目经用户确认后清理：先备份整个文件，只删除该表（表头、`trusted_hash` 与一个空行），
原插件 `tier-guard@tier-guard` 的信任条目保持不变。

## 候选目录摘要复测（17:51 起）

被测：提交 `56de0e1`（提醒 / deny 文本附上本宿主候选目录摘要与「信息不足、取舍、跨模块或不可逆选高档」）。
两个宿主都用「不要读取、加载或使用任何 skill」+ 自然提示词，专门检验主代理拿不到 skill 时能否只凭文本选对档位。

### Claude Code CLI

| 场景 | session | 派活（按顺序） | hook `nudge` | 实际模型 |
|---|---|---|---|---|
| auto | `21fef527-8885-43cb-b32d-23249bdd5ca8` | ① 未传 model → 被拦（工具结果为 deny 常量 + 摘要）；② ③ ④ 未调用 skill，显式 `haiku` / `sonnet` / `opus` | denied ×1，之后 none ×3 | `claude-haiku-4-5-20251001` / `claude-sonnet-5` / `claude-opus-5` |
| audit | `7ef2567c-ea3c-4cf1-a2db-18f7df09849d` | 3 次均未传 model | reminded ×3 | 3 个都是 `claude-sonnet-5`（继承） |

- **auto：通过。** 主代理没有加载 skill，只凭 deny 原因里的摘要按三档显式传参，取舍类的 C 为 opus，没有降档。
- **audit：提醒仍未被采纳。** 父转录里 3 条 `hook_additional_context` 都带摘要，但后续派活没有显式传参。

### Codex CLI

快照 `tier-guard@tier-guard-e2e` `0.1.1+codex.20260913175121`（来自 `56de0e1`；`codex_hook.py` 指纹 `a0f1b0b1…`、
`route_decide.py` `adc7a83b…` 与工作树一致，目录 `1ccfb63d…`）。hook 信任先在一个只回复 `READY`、不派子代理的会话里
逐条核对后只信任 e2e 这一条，再开正式会话，避免信任前就开始派活。

| 场景 | 父线程 | e2e hook | 父 rollout | child 实际参数（SQLite） |
|---|---|---|---|---|
| audit | `01a09a31-b2b2-7c93-8993-437eecbaf097` | `pinned=False`，`nudge=reminded` ×3 | 提醒文本 3 次、摘要标记 3 次 | 3 个都是 `terra/high`（继承） |
| auto | `01a09a31-bd19-7380-8217-fa36102555a3` | 第 1 次 `denied`，之后 3 次 `pinned=True`、`nudge=none` | 被拦 1 次，deny 文本 1 次、摘要标记 1 次；TUI 的 `Blocked by hook` 原文带摘要 | 3 个都是 `luna/medium`（显式） |

- 摘要文本已送达主代理（两轮 rollout 都能找到摘要标记）。
- **auto：比上一轮好，但仍未达标。** 主代理不再使用目录外的 `luna/low`，而是目录内的 `luna/medium`；但取舍类的 C
  仍然被分到最低档（按目录应为 `terra/xhigh`），违反「取舍类任务 0 次被降档」。
- **归因不干净。** 本测试要求每个 child「不得使用工具、只回复固定文本」，C 的实际工作量是机械的，把三个都判为
  机械只读在语义上也说得通。同一提示词下 Claude 主代理把 C 判为 opus，而 Codex 没有。要区分「摘要不足以约束」
  与「测试任务本身是机械的」，需要让 child 真正执行取舍工作的对照测试。
- audit：提醒仍未被采纳（提示词禁止使用 skill）。

恢复：两个会话已关闭，e2e 插件与 marketplace 已删除，空缓存目录已 `rmdir`；`config.toml` 先备份，再只删除本轮新增的
e2e hook 信任表。`codex plugin list` 只剩 `tier-guard@tier-guard 0.1.1`，其目录指纹仍为 `fec0067b…`。

## 对照测试：child 真正执行取舍分析（18:05 起）

为区分「摘要不足以约束」与「测试任务本身是机械的」，把三个 child 换成真正要做的事，其余条件不变（auto、禁止使用 skill、
child 不得使用工具，被测代码仍为 `56de0e1`）：

- A：数出 `alpha,beta,gamma` 的逗号分隔项，只回复数字（机械只读）；
- B：写 `add(a, b)` 及两条 assert 测试，只回复代码（受限实现）；
- C：针对 24/7 流量的生产 PostgreSQL，从风险、成本、回滚比较一次性迁移与 expand-contract 迁移，至多五条，再给出推荐与一句理由（取舍）。

判据：主代理被拦后重派时，C 是否拿到高能力档。

### Claude Code CLI（2 轮）

| 轮次 | session | 被拦派活 | 重派显式参数（A / B / C） | 实际模型 |
|---|---|---|---|---|
| 1 | `3599d8dd-723f-40fd-a49b-d29e169118ac` | 1 次，工具结果为 deny 常量 + 摘要 | `haiku` / `sonnet` / `opus` | `claude-haiku-4-5-20251001` / `claude-sonnet-5` / `claude-opus-5` |
| 2 | `5ca4a659-b79e-47d5-9451-ee21304d5938` | 1 次，工具结果为 deny 常量 + 摘要 | `haiku` / `sonnet` / `opus` | `claude-haiku-4-5-20251001` / `claude-sonnet-5` / `claude-opus-5` |

两轮都没有调用 skill；取舍类 C 两次都是 opus，与候选目录一致。

### Codex CLI（2 轮）

快照同上（`0.1.1+codex.20260913175121`，`codex_hook.py` `a0f1b0b1…`）。hook 信任仍先在只回复 `READY` 的会话里逐条核对后
只信任 e2e 这一条，再开两个正式会话。

| 轮次 | 父线程 | 被拦 | 重派显式参数 = SQLite 实际参数（A / B / C） | 摘要送达 |
|---|---|---|---|---|
| 1 | `01a09a3f-c106-7220-a0fa-1b260fb2140e` | 1 次（`nudge=denied`） | `luna/medium` / `luna/medium` / `terra/xhigh` | rollout 中摘要标记 1 次 |
| 2 | `01a09a3f-ceae-7a53-bce2-935080ad7dcb` | 1 次（`nudge=denied`） | `luna/medium` / `luna/medium` / `terra/xhigh` | rollout 中摘要标记 1 次 |

### 结论

- **Codex 取舍类降档的原因是测试设计。** 当 C 真正需要做取舍分析时，Codex 主代理在不加载 skill 的情况下两轮都给了
  `terra/xhigh`；上一轮的 `luna/medium` 出现在 child 只回复固定文本、实际工作是机械任务的场景下。
- **候选目录摘要在两个宿主上都能在拿不到 skill 时约束选档**：取舍类任务 4/4 次拿到高能力档（Claude opus ×2、Codex `terra/xhigh` ×2），
  所有重派参数都在候选目录内。
- **次要观察：** 受限实现 B 在 Codex 上两轮都是 `luna/medium`，按目录应为 `terra/high`；Claude 两轮都是 sonnet。
  规约的硬门槛只约束取舍类任务，这一偏低选择留给 Task 12 的数据判断是否需要处理。

恢复：两个会话已关闭，e2e 插件与 marketplace 已删除，空缓存目录已 `rmdir`；`config.toml` 先备份，再只删除本轮新增的
e2e hook 信任表。

## Task 12 真实宿主评估（2026-09-13 18:40 起）

被测代码：`1432437`（提醒 / 拦截文本带候选目录摘要；`/tier-report` 带「主代理预路由提醒」统计）。
每个宿主 4 个会话：1、2 为 audit，3、4 为 auto；每个会话派 3 个真正干活的子代理（机械只读 / 受限实现 / 取舍各一，
题目各不相同，三类顺序在会话间轮换）。提示词为自然写法：不点名 skill，也不禁止 skill。门槛取自规约：
提醒或拦截之后的同会话派活 ≥80% 显式传参；取舍类任务 0 次被降档；pin 的派活 0 次被提醒或拦截。

### Claude Code CLI

会话：`0a2f7f89-26aa-489a-9857-fd8cfef7fe81`（audit）、`09e10d65-40bc-4846-9d49-5297570bff12`（audit）、
`c668f3b7-b907-4a00-89bc-fd2eb2017f97`（auto）、`c2622441-c2dd-4ff3-946f-d8bab91fd356`（auto）；`total_cost_usd` 合计约 1.36。

合并 4 轮日志后的报告：

```
提醒 4 次 / 拦截 2 次 / 未触发 8 次（共 14 次派活）。
提醒或拦截之后同会话派活 10 次，其中显式传参 8 次（8/10）。
pin 的派活被提醒或拦截 0 次（应为 0）。
```

| 会话 | mode | 类别 | 目录档 | 实际 | 显式传参 | 取舍类高档 |
|---|---|---|---|---|---|---|
| 1 | audit | 机械 | haiku | sonnet | 否 |  |
| 1 | audit | 实现 | sonnet | sonnet | 否 |  |
| 1 | audit | 取舍 | opus | sonnet | 否 | ❌ |
| 2 | audit | 取舍 | opus | sonnet | 否 | ❌ |
| 2 | audit | 机械 | haiku | haiku | 是 |  |
| 2 | audit | 实现 | sonnet | haiku | 是 |  |
| 3 | auto | 实现 | sonnet | sonnet | 是 |  |
| 3 | auto | 取舍 | opus | opus | 是 | ✅ |
| 3 | auto | 机械 | haiku | haiku | 是 |  |
| 4 | auto | 机械 | haiku | haiku | 是 |  |
| 4 | auto | 取舍 | opus | opus | 是 | ✅ |
| 4 | auto | 实现 | sonnet | sonnet | 是 |  |

- **显式传参比例 8/10，恰好达到 80% 门槛；pin 被打扰 0 次。**
- **取舍类 2/4 拿到高档，未达标。** auto 两轮全部正确；audit 两轮都没有。
  - 会话 1：提醒送达但三次派活都没有显式传参，全部继承父模型 sonnet。
  - 会话 2：取舍任务是会话里的第一次派活。audit 的提醒要在该次工具结果之后才送达，结构上无法影响第一次派活，
    所以它只能继承父模型；之后两次派活显式传参，但受限实现选了 haiku，比目录低一档。
- 结论：在 Claude 上，auto 的拦截能可靠地让取舍类任务拿到高档；audit 的提醒既可能被忽略，也对会话第一次派活无效。

### Codex CLI

快照 `tier-guard@tier-guard-e2e` `0.1.1+codex.20260913175121`（`codex_hook.py` `a0f1b0b1…`，目录 `1ccfb63d…`）；hook 信任仍先在
只回复 `READY` 的会话里逐条核对后只信任 e2e 这一条。父线程：`01a09a5d-e986…`（audit）、`01a09a5d-f5e6…`（audit）、
`01a09a5e-0059…`（auto）、`01a09a5e-0b82…`（auto）。原插件 0.1.1 的 hook 同时运行，统计只取目录指纹为 `1ccfb63d…` 的记录。

合并 4 轮日志后的报告：

```
提醒 0 次 / 拦截 0 次 / 未触发 12 次（共 12 次派活）。
提醒或拦截之后同会话派活：暂无样本。
pin 的派活被提醒或拦截 0 次（应为 0）。
```

| 会话 | mode | 类别 | 目录档 | 实际（SQLite） | 显式传参 | 取舍类高档 |
|---|---|---|---|---|---|---|
| 1 | audit | 机械 | luna/medium | luna/medium | 是 |  |
| 1 | audit | 实现 | terra/high | terra/high | 是 |  |
| 1 | audit | 取舍 | terra/xhigh | terra/xhigh | 是 | ✅ |
| 2 | audit | 取舍 | terra/xhigh | terra/xhigh | 是 | ✅ |
| 2 | audit | 机械 | luna/medium | luna/medium | 是 |  |
| 2 | audit | 实现 | terra/high | luna/medium | 是 |  |
| 3 | auto | 实现 | terra/high | luna/medium | 是 |  |
| 3 | auto | 取舍 | terra/xhigh | terra/xhigh | 是 | ✅ |
| 3 | auto | 机械 | luna/medium | luna/medium | 是 |  |
| 4 | auto | 机械 | luna/medium | luna/medium | 是 |  |
| 4 | auto | 取舍 | terra/xhigh | terra/xhigh | 是 | ✅ |
| 4 | auto | 实现 | terra/high | terra/high | 是 |  |

- **自然使用下主代理自行预路由：12/12 次派活显式传参**，因此提醒和拦截一次都没有触发；「提醒之后 ≥80% 显式传参」这一项
  没有样本，不是未达标。
- **取舍类 4/4 拿到 `terra/xhigh`；pin 被打扰 0 次。**
- 受限实现 2/4 为 `luna/medium`，比目录的 `terra/high` 低一档（与对照测试中的观察一致）。

### 评估结论

| 门槛 | Claude Code CLI | Codex CLI |
|---|---|---|
| 提醒或拦截之后 ≥80% 显式传参 | 8/10，达标（恰好） | 无样本（12/12 派活本来就显式传参） |
| 取舍类任务 0 次被降档 | **2/4，未达标**（均在 audit：一次提醒被忽略，一次是会话第一次派活） | 4/4，达标 |
| pin 的派活 0 次被提醒或拦截 | 0，达标 | 0，达标 |

- Claude 在 auto 下三项全部符合；在 audit 下提醒不可靠，且结构上无法影响会话第一次派活。
- Codex 在自然使用下已经依靠 skill 描述完成预路由，hook 的提醒与拦截在这批样本里没有被用到。
- 两个宿主都出现过「受限实现选低一档」（Claude 1/4、Codex 2/4），规约的硬门槛不覆盖这一类。
- 样本为每宿主 12 次派活，结论是初步的。按规约，Claude 不满足打开生产闸门的条件；是否只对 Codex 或只在 auto 下开启，
  需要另行决定。

## Task 15 guard 复评（2026-09-13 23:26 起）

被测代码：提交 `39108b5`（默认 profile 为 `guard`：每会话第一次未 pin 派活 deny 一次、之后提醒，从不改写参数）。
协议与 Task 12 相同——同一批 8 个自然提示词与任务顺序，唯一差别是 4 个会话全部为 `guard`。

### Claude Code CLI

会话：`6c4e2661-3054-462b-b87e-af92d406f1ce`、`b645320f-ec74-43b5-a650-fd78d0338f89`、`706298c5-54f1-41c7-8eba-06a59ceefeea`、
`4a71e3fb-e0bf-41f1-a977-1da271a7f18d`；`--plugin-dir` 加载工作树，临时目录 `claude-code.dispatch_nudge=true`（指纹 `f5a5a607…`）；
`total_cost_usd` 合计约 1.55。

合并 4 轮日志后的报告：

```
提醒 0 次 / 拦截 4 次 / 未触发 12 次（共 16 次派活）。
提醒或拦截之后同会话派活 12 次，其中显式传参 12 次（12/12）。
pin 的派活被提醒或拦截 0 次（应为 0）。
```

| 会话 | 类别 | 目录档 | 实际 | 显式传参 | 取舍类高档 |
|---|---|---|---|---|---|
| 1 | 机械 | haiku | haiku | 是 |  |
| 1 | 实现 | sonnet | sonnet | 是 |  |
| 1 | 取舍 | opus | opus | 是 | ✅ |
| 2 | 取舍 | opus | opus | 是 | ✅ |
| 2 | 机械 | haiku | haiku | 是 |  |
| 2 | 实现 | sonnet | sonnet | 是 |  |
| 3 | 实现 | sonnet | haiku | 是 |  |
| 3 | 取舍 | opus | opus | 是 | ✅ |
| 3 | 机械 | haiku | haiku | 是 |  |
| 4 | 机械 | haiku | haiku | 是 |  |
| 4 | 取舍 | opus | opus | 是 | ✅ |
| 4 | 实现 | sonnet | sonnet | 是 |  |

- **三项门槛全部达标**：显式传参 12/12，取舍类 4/4 拿到 opus，pin 被打扰 0 次。
- 对照 Task 12（audit / auto 各半）：取舍类从 2/4 提升到 4/4，显式传参从 8/10 提升到 12/12。
  每个会话的第一次派活都被拦下后带参重派，audit 下「第一次派活无法被提醒影响」的结构性缺口不再出现。
- 受限实现 1/4 选了 haiku（低一档），与此前观察一致，不在门槛内。

### Codex CLI

快照 `tier-guard@tier-guard-e2e` `0.1.1+codex.20260913232558`（目录默认 `mode: guard`，指纹 `9c2092d0…`；`codex_hook.py` `a0f1b0b1…`
与工作树一致）。hook 信任仍先在只回复 `READY` 的会话里逐条核对后只信任 e2e 这一条。父线程：`01a09b73-cd19…`、`01a09b73-d89a…`、
`01a09b73-e47f…`、`01a09b73-f247…`。原插件 0.1.1 的 hook 同时运行，统计只取目录指纹为 `9c2092d0…` 的记录。

合并 4 轮日志后的报告：

```
提醒 0 次 / 拦截 0 次 / 未触发 12 次（共 12 次派活）。
提醒或拦截之后同会话派活：暂无样本。
pin 的派活被提醒或拦截 0 次（应为 0）。
```

| 会话 | 类别 | 目录档 | 实际（SQLite） | 显式传参 | 取舍类高档 |
|---|---|---|---|---|---|
| 1 | 机械 | luna/medium | luna/medium | 是 |  |
| 1 | 实现 | terra/high | terra/high | 是 |  |
| 1 | 取舍 | terra/xhigh | terra/xhigh | 是 | ✅ |
| 2 | 取舍 | terra/xhigh | terra/xhigh | 是 | ✅ |
| 2 | 机械 | luna/medium | luna/medium | 是 |  |
| 2 | 实现 | terra/high | luna/medium | 是 |  |
| 3 | 实现 | terra/high | luna/medium | 是 |  |
| 3 | 取舍 | terra/xhigh | **luna/medium** | 是 | ❌ |
| 3 | 机械 | luna/medium | luna/medium | 是 |  |
| 4 | 机械 | luna/medium | luna/medium | 是 |  |
| 4 | 取舍 | terra/xhigh | terra/xhigh | 是 | ✅ |
| 4 | 实现 | terra/high | luna/medium | 是 |  |

- 主代理在自然使用下 12/12 次派活都自行显式传参，guard 的拦截与提醒一次都没有触发；「提醒之后 ≥80%」无样本。
- **取舍类 3/4，未达标。** 会话 3 的取舍任务被主代理显式分到 `luna/medium`；显式参数按规约是 pin，guard 不拦截、不改写，
  这次降档来自主代理自身的选档，而不是 hook 放过了未 pin 派活。Task 12 同一提示词下 Codex 为 4/4，说明存在运行间波动。
- 受限实现 3/4 为 `luna/medium`（低一档），比 Task 12（2/4）更频繁。
- pin 被打扰 0 次。

恢复：4 个会话已关闭，e2e 插件与 marketplace 已删除，空缓存目录已 `rmdir`；`config.toml` 先备份，再只删除本轮新增的
e2e hook 信任表。

### Task 15 结论

| 门槛 | Claude Code CLI（guard） | Codex CLI（guard） |
|---|---|---|
| 提醒或拦截之后 ≥80% 显式传参 | 12/12，达标 | 无样本（主代理 12/12 自行显式传参） |
| 取舍类任务 0 次被降档 | 4/4，达标 | **3/4，未达标**（主代理显式选错档，hook 按 pin 语义不干预） |
| pin 的派活 0 次被提醒或拦截 | 0，达标 | 0，达标 |

- guard 解决了 Claude 在 audit 下暴露的两个缺口（提醒被忽略、第一次派活无法影响），Claude 三项全部达标。
- Codex 的未达标不在 hook 的作用范围内：主代理已经在派活前显式选择，guard 按规约尊重显式参数。要改善它，需要作用于
  主代理的选档本身（例如 skill 文本或候选目录描述），而不是 hook 的拦截强度。
- 每宿主 12 次派活，结论仍是初步的。
