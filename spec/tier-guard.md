# Spec: tier-guard — 动态子代理模型路由

> 状态：**核心定位已于 2026-09-12 确认**。本文件取代旧的“默认 T2、只升不降”方向；
> 本地实现与回归已完成，宿主自动改写能力仍以兼容性记录中的真实端到端证据为准。
>
> 2026-09-13 增补「主代理预路由提醒」（用户已确认 audit 提醒与 auto 每会话一次 deny；待评审后实施）。
>
> 2026-09-13 Task 12 评估后用户确认：新增 `guard` profile 并设为默认（每会话第一次未 pin 派活拦一次、不改参数）。
>
> 2026-09-13 Task 15 guard 复评后用户确认：生产目录只为 Claude Code CLI 打开 `dispatch_nudge`；Codex 保持关闭。

## Objective

tier-guard 是一个在**创建子代理前**执行的动态模型路由插件。它根据本次子任务的目标、风险、
验收清晰度、工作范围与可用上下文，选择满足任务质量要求的最低成本 `model + reasoning_effort`。

它服务于 agent-skills 等上游工作流：上游负责识别何时应拆出子任务、定义边界与验收；
tier-guard 负责给已决定创建的子任务选择执行配置。

### Success criteria

- 主代理的 model 与 reasoning effort 在任务过程中不被 tier-guard 改写。
- 每个未 pin 的子代理都得到独立、可解释的路由决定：升档、降档或保持均可能发生。
- 路由选择的是当前候选中最低成本的合格配置，而非固定默认最高档。
- 每条决定可审计：输入特征来源、目标档、置信度、实际传入参数和最终可观察结果。
- 未安装 agent-skills 或 spec-guard 时，核心路由功能仍可运行。
- 任何宿主只有在派发前实际接收并应用参数改写时，才能被标为“自动路由已验证”。
- 自然使用（用户不点名 tier-routing）时，主代理在未 pin 派活上被提醒后显式选择参数：每个宿主至少 10 次
  自然派活评估中，同一会话第二次及以后的未 pin 派活有 ≥80% 显式传入 model（Codex 另含 effort），
  取舍类任务 0 次被降档，pin 的派活 0 次被提醒或拦截。

## Boundaries

### Always

- 只处理子代理创建事件；不切换主代理的模型、effort 或会话。
- 将用户显式指定的 `pin` 视作锁定：绝不自动改写。audit 仍记录相对起点的建议方向，但不提供可应用 target。
- 以硬约束过滤不合格候选；信息不足或低置信度时采用保守的更高档，并记录原因。
- 记录最小化的审计数据；默认不持久化任务原文。
- 将模型目录、路由策略、宿主 adapter 和可选上游集成分开维护。

### Ask first

- 启用会把任务文本发送给外部语义分类模型的 provider。
- 扩大自动候选模型集合、改变默认 pin 语义、或允许路由器覆盖 pin。
- 为新的宿主声明自动路由支持、安装或升级插件、访问网络或外部计费凭据。

### Never

- 不自行创建子代理，也不替代 agent-skills 的任务拆解与验收。
- 不读取、写入或依赖 `.agent/state.json`、spec-guard tracker、其日志或私有文件。
- 不把“模型更贵”当作复杂度证据，也不把短 prompt 自动当作简单任务。
- 不将 desktop 的建议式能力宣传为 pre-dispatch 强制路由。
- 不以事后日志、转录抓取或子代理回复伪造“派发前已路由”。

## Routing model

### Model catalog

模型目录是可配置的能力事实，而不是任务到模型的预设模板。每个候选至少声明：

- 宿主是否可用、是否允许自动选择；
- `model`、可用 `reasoning_effort`、成本和延迟观测值；
- 支持的工具与上下文限制；
- 经验证的能力标签与版本来源。

目录还必须为每个候选宿主声明 `host_capabilities.<host>.pre_dispatch_apply`。它是宿主版本的
实测闸门，不是模型能力或用户 mode：只有它为 `true`，`auto` 才可以输出参数改写；否则仍记录
相同决定但 `applied=false`。生产目录默认 profile 为 `guard`（与 `audit` 一样不改写参数）；能力闸门只在有对应真实端到端证据的宿主上
开启，不能靠临时环境变量绕过。当前 Claude Code CLI 已开启，Codex CLI 与 Desktop 保持关闭。

目录同时为每个宿主声明 `host_capabilities.<host>.dispatch_nudge`：只有宿主已实测支持在
PreToolUse 注入提醒上下文、且 deny 附原因会让主代理带参重派时才为 `true`；为 `false` 时不提醒、不 deny。
Claude Code CLI 2.1.270 的官方文档与 Codex CLI 0.154.0 的源码（tag `rust-v0.154.0`）已确认两种输出存在，
Claude Code CLI 已按 Task 15 guard 复评证据开启（2026-09-13 用户确认）；Codex CLI 取舍类未达标、Codex Desktop 未验证，均保持 `false`。

OpenAI 的公开描述可作为目录初始信息：Astra 面向最难的推理与编码，Terra 平衡能力与成本，
Luna 面向成本敏感、高吞吐任务；实际路由阈值必须用本工作负载的结果校准。

### Input

核心只接收标准化 `RouteRequest`：

```json
{
  "task": "仅在内存中的最小化任务文本",
  "host": "codex-cli",
  "requested": {"model": "…", "reasoning_effort": "…", "pinned": false},
  "signals": {
    "side_effect": "read_only|reversible_write|external_or_irreversible|unknown",
    "acceptance": "explicit|missing_or_ambiguous|unknown",
    "scope": "small|bounded|cross_cutting|unknown",
    "decision_load": "mechanical|implementation|tradeoff|unknown"
  },
  "optional_context": {
    "source": "agent-skills",
    "schema_version": 1,
    "signals": {
      "side_effect": "reversible_write",
      "acceptance": "explicit",
      "scope": "bounded",
      "decision_load": "implementation"
    }
  }
}
```

`optional_context` 只能由上游显式传入；core 不扫描上游文件来补齐它。当前只接受
`source=agent-skills`、`schema_version=1` 和恰好四个枚举信号。来源、版本、字段或值不符合时，
core 把它记为 `unavailable` 并按无上下文处理，不会让路由失败。显式 `signals` 优先于该信封，
该信封优先于文本推导信号。

默认文本分类的 `classification` 同时配置只读、验收、不可逆、取舍、实现和受限范围的标记。
“实现”和“受限范围”两类是可选的 v2 扩展字段：旧 v2 catalog 未声明它们仍保持可用、按未知任务保守处理。
“只读 + 小范围 + 机械”即使没有验收行也按只读候选处理；“实现 + 受限范围 + 明确验收”按
`implementation + bounded_change` 处理。其余文本仍保守地归为 `unknown`，不把词表当作通用语义模型。

### Decision

1. 验证 host、pin 和候选目录。
2. 汇总确定性信号与可选上游元数据。
3. 对明显任务直接分类；对灰区仅在用户配置并授权后调用轻量语义裁判。
4. 按安全、工具、上下文与宿主能力过滤候选。
5. 选择满足所需能力的最低成本候选，输出理由、置信度与 fallback 链。
6. audit 只记录；对 pin 保留 `raise` / `lower` / `keep` 的方向性审计、但 `target=null`。auto 仅在宿主已验证支持 pre-dispatch 改写且请求未 pin 时应用。

若原生宿主在 hook 边界只提供 `opaque_token` 而非任务明文，hook 不得根据猜测自动改写参数，即使
该宿主已验证接受 `updatedInput`。此时由创建子代理的主代理在加密前、仍可读取任务边界时执行同一
动态选择，并将选出的参数显式随 `spawn_agent` 传入；这是主代理对**新子代理**的预派发选择，不涉及
主会话切换。hook 只审计该事实。没有明文预路由能力时保持 audit，而不是为了“自动”把未知任务升档。

未 pin 且没有可识别起点时，v2 仍按任务做 `select`，因为它的职责就是为这次新派活选择候选；这不是继承主代理模型的改写。
显式 pin 即使不在候选目录中也绝不改写；audit 可记 `select` 及 `recommended`，但 `target=null`、`applied=false`。

#### pin 的来源

「显式选择」不限于本次派活的调用参数。Claude Code 侧必须把下面三类都算作 pin，按优先级取值：

1. 本次派活的 `tool_input.model`；
2. 该 `subagent_type` 的 agent 定义 frontmatter 中的 `model`；
3. 宿主配置的子代理模型环境变量 —— `CLAUDE_CODE_SUBAGENT_MODEL_FORCE`（强制，并使 `model`
   参数被宿主忽略）与 `CLAUDE_CODE_SUBAGENT_MODEL`（默认）。两者均在 Claude Code 2.1.289 中
   被实际读取。

空值与 `inherit` / `default` 不算设置过，这与宿主自身的判定一致；把它们当作 pin 会让整类任务
不再被路由。`fork` 恒继承父代理模型、插件 agent（名字带冒号）的 frontmatter 读不到，这两种情况
仍是「判不出」，不提醒也不改写。

漏掉第 3 类会在 `auto` 下覆盖用户用环境变量做出的显式选择，违反上面的 pin 不变量。
背景与核实过程见 [同类方案调研](../docs/research/2026-10-routing-prior-art.md)。

### 上游档位信号（tier）

上游（spec-guard 或任何按本约定发信号的工具）可以为一次派活声明档位。tier-guard **只接收推送，
绝不主动读取上游的文件、state 或 tracker**，这是「运行时零依赖」的直接推论：插件在用户机器上
可能根本没有装 spec-guard，也可能装了但版本不同。

#### 档位词汇

`L1` / `L2` / `L3` 是上游词汇，不是新的候选维度，映射到已有的能力标签：

| 上游 tier | 能力标签 | 含义 |
|---|---|---|
| `L1` | `mechanical` + `read_only` | 只读或机械性工作 |
| `L2` | `implementation` + `bounded_change` | 有明确验收、范围在单模块内的实现 |
| `L3` | `tradeoff` + `cross_cutting` | 跨模块取舍、需求有歧义、风险高或不可逆 |

#### 传输：prompt 内嵌标记

hook 在派发边界只能看到 `tool_input`，没有旁路元数据通道。因此档位随任务文本传递，格式为**独占一行**：

```
<!-- tier-guard: tier=L2 -->
```

可选附 `reason`：`<!-- tier-guard: tier=L2 reason=按 spec 第 3 节实现，验收明确 -->`

解析规则（任何一条不满足都降级为「无上游档位」，**绝不使核心失败**）：

- 整段任务文本中该标记**恰好出现一次**；出现 0 次视为未声明，出现 ≥2 次视为冲突 → `unavailable`。
- `tier` 取值必须恰为 `L1` / `L2` / `L3`，大小写敏感。
- 标记必须独占一行，前后允许空白。
- `reason` 是自由文本，**不参与任何判定**，只用于人读。

#### 与 `optional_context` 信封的关系

解析结果接到已有的 `optional_context` 信封上。信封当前为 `schema_version: 1`、字段严格等于
`{source, schema_version, signals}` 且 `signals` 恰好是四个确定性信号。本约定新增
`schema_version: 2`，在其上允许一个可选的 `tier` 字段；`schema_version: 1` 继续被接受，
不因新增而失效。信封校验失败时按既有语义记 `unavailable` 并走纯推断，不报错。

#### 优先级：pin > floor > tier > 推断

**上游档位不能撤销 floor。** 这是本节最重要的一条约束。

档位标记走任务文本传递，意味着任务文本**能够伪造它**。若允许 tier 覆盖 floor，一段写着
`tier=L1` 的不可逆任务就能被路由到最低档，直接打穿「不可逆、取舍、跨模块或信息不足不能被路由
到低能力候选」这条安全边界。因此：

1. **pin** —— 用户显式选择，一切照旧不改写。
2. **floor** —— `R-IRREVERSIBLE` / `R-AMBIGUOUS` / `R-TRADEOFF` 命中产生的下限。tier 只能在
   floor **之上**生效，不能把档位压到 floor 以下。
3. **tier** —— 上游声明。在不违反 floor 的前提下，优先于文本推断。
4. **推断** —— 没有上游信号时的既有路径。

tier 高于 floor 时按 tier 取；低于 floor 时**按 floor 取并记录该次冲突**，便于发现上游持续低估
或存在伪造。记录冲突不等于拒绝派发。

### 升档与收回

#### tier-guard 不自行判定失败

tier-guard 只有 `PreToolUse` 与 `SubagentStop` 两个观察点，看不到测试结果、验收结论或人工判断。
它**不引入验证器子代理**，也不解析子代理产出去推断成败——那是「派发后评估」职责，不属于
「创建子代理前选择参数」这个边界。

失败信号由上游或主代理给出，tier-guard 消费它：

- `consecutive_failures` —— 同一任务连续失败次数，沿用 v1 已有入参语义。
- `escalated` —— 既有的观测口径（子代理最后一条回复引用合同 ①–④ 并说交回 / 停止）。

> **更正（2026-10-05 实测）**：本节初稿写的是 `escalated`「当前仅计数、不参与定档」。
> 这句话描述的是 v1 路径。实情更弱一层，下面三条都在本机核实过：
>
> 1. **生产路径上它根本不被计算。** 默认目录是 `schema_version: 2`，走 `on_subagent_stop_v2`，
>    而该 handler **不写 `escalated` 字段**；只有 v1 的 `on_subagent_stop` 写它。
> 2. **真实日志里带 `escalated` 字段的记录为 0 条**（共 3034 条 `subagent-stop`）。
> 3. **观测通道本身当前不可靠**：3034 条 stop 记录里 **2601 条（85.7%）是 fallback**，
>    全部是同一个读不到子代理 transcript 的 `FileNotFoundError`。
>
> 另外该判据对否定句会误报：「我检查了③，不涉及不可逆动作，所以不需要停止」→ `True`
> （纯子串合取，不理解否定）。

把 `escalated` 接成失败信号的前置条件，因此比初稿写的苛刻得多，**按顺序**：

1. 先修 `SubagentStop` 的 `FileNotFoundError`，把 fallback 率降到个位数——在它修好之前，
   任何基于 stop 事件的统计都没有代表性，包括用来推翻现状的统计；
2. 再把 `escalated` 补进 v2 的 stop 记录，**仍然只进日志、不进定档**；
3. 积累到足够样本并人工标注，确认精度与召回；统计时必须**排除合同 ③**——「需要做不可逆的事
   所以停下交回」是闸二设计出来就要的正确行为，把它计成失败等于对正确行为罚款；
4. 最后才谈改默认，且改默认会正面触及本 spec 的 Non-goals「不解析子代理产出去推断成败」，
   属于「Ask first」级别的语义变更。

在此之前，**默认保持「仅观测」不是暂缓，是上述前置条件未满足的结果**。

#### 规则

- **L1 失败或结果不确定 → 升到 L2。** 「结果不确定」指上游明确给出的不确定信号，不是
  tier-guard 自行推测。
- **L2 连续失败两次 → 收回主会话。** 复用既有 deny 通道输出原因，不新增机制；deny 文本说明
  这是第二次失败后的收回，要求主代理自己处理或重新界定任务。
- 升档只升不降：升档后的档位不低于原档位，也不低于 floor。
- 收回之后不自动重试。再次派活是一次全新的 `RouteRequest`。

#### 失败日志由主代理携带

升档时把上一次的失败日志交给下一档是**主代理的职责**。tier-guard **不接触、不转发、不记录失败
日志正文** —— 日志里可能有密钥，而本仓既有规矩是不记 prompt 原文。tier-guard 只记录「这次是
升档、从哪档到哪档、失败计数是多少」。

同理，`reason` 字段不入日志正文，只记是否存在；需要关联时记其 SHA-256。

### 主代理预路由提醒

2026-09-13 实测：点名 tier-routing 时 Claude 与 Codex 主代理都能显式选对三档；不点名时两者都不加载 skill，
子代理全部继承父代理参数（证据：[`Claude CLI v2 e2e`](../docs/research/2026-09-13-claude-cli-v2-e2e.md)）。
因此插件在**子代理创建事件**上驱动主代理自己做预路由，hook 不做语义判断。

Task 12 真实宿主评估（同一证据文档）进一步显示：在 Claude 上，`audit` 的提醒会被忽略，且提醒在当次工具结果之后才送达，
结构上无法影响会话第一次派活；每会话拦一次的 deny 则让取舍类任务稳定拿到高能力档。所以默认 profile 为 `guard`：

- 触发条件：未 pin 的派活（PreToolUse `Agent` / `spawn_agent`），且宿主 `dispatch_nudge=true`。pin 的判定同上；
  无法解析是否 pin 的插件 agent（`plugin:name`）不提醒。
- `audit`：放行派活、不改参数，输出一条提醒上下文，要求主代理按 tier-routing 为之后的派活显式传参。
  两个宿主都在当前工具结果之后送达，所以提醒只影响后续派活。
- `guard`（默认）：同一 `session_id` 内第一次未 pin 派活返回 deny 并附原因，要求显式传参后重派；此后的未 pin 派活放行并附提醒。
  **从不输出 `updatedInput`**，由主代理按提醒 / deny 文本里的候选目录自行选择。没有 `session_id` 时不 deny。
- `auto`：与 `guard` 相同的 deny / 提醒；此外 `pre_dispatch_apply=true` 的宿主上，对未 pin 派活应用 `updatedInput`。
- 提醒与 deny 原因只引用 tier-routing 与候选目录，不包含任务原文。
- 任何异常一律放行、stdout 为空，日志写明 fallback 路径；审计记录新增 `nudge`：`none` / `reminded` / `denied`。

语义裁判只能输出受 schema 约束的任务类型、所需能力、复杂度和置信度；它不能直接输出任意
模型 ID，也不能绕过硬约束和候选目录。当前目录的 `semantic_provider.mode` 固定为 `disabled`：
没有 provider 实现、网络请求、凭据读取或任务文本外发；改变该模式需要单独用户授权和新版本契约。

### Profiles

| Profile | 行为 |
|---|---|
| `off` | 不分类、不记录、不改写。 |
| `audit` | 计算并记录建议，不改写参数；显式 pin 也保留方向性 action，但 `target=null`。未 pin 派活且 `dispatch_nudge=true` 时注入提醒。 |
| `guard`（默认） | 与 audit 同样记录、不改写参数；`dispatch_nudge=true` 时每个会话第一次未 pin 派活 deny 一次要求显式传参，之后未 pin 派活附提醒。 |
| `auto` | `guard` 的全部行为，外加对未 pin 请求应用决定（仅限已验证的 host adapter）。 |

`semantic` 不是独立 mode，而是 `audit` 或 `auto` 下的可选 classifier provider。默认关闭；
没有 provider 时，灰区任务以 `unknown` 处理并保守路由。

## Integrations

### agent-skills

agent-skills 是可选的上游信号提供者。它可提供工作阶段、任务类别、验收标准、变更边界和风险标签；
不能赋予 tier-guard 创建子代理的权限，也不能绕过 pin 或宿主能力检查。

### spec-guard

本仓开发过程使用 spec-guard 的 local 工作流（能力图、module spec/plan/todo 与阶段检查点）。
发布后的 tier-guard **运行时零依赖** spec-guard：不调用其命令、不读取其 state、不共享日志。

spec-guard 可以作为上游为每个 task 声明档位，走[上游档位信号](#上游档位信号tier)约定。
**方向是推送，不是拉取**：spec-guard 在生成任务文本时写入标记，tier-guard 在派发边界解析它。
tier-guard 不知道 spec-guard 是否存在，也不因它缺席而改变行为。

作为上游侧的参考（**这是 spec-guard 的职责，不是 tier-guard 的读取路径**），三种 tracker 模式下
档位的自然存放位置分别是：`local` 模式在 `tasks/<module-id>/todo.md` 的任务行；`GitHub/GitLab`
模式在 Issue 正文；两者共用的检查点快照在 `.agent/state.json` 的模块记录里。无论存在哪里，到达
tier-guard 的只有任务文本中的那一行标记。
若 spec-guard 在用户明确授权下创建只读预检子代理，该子代理仍可作为普通 `RouteRequest` 被路由；
tier-guard 不改变其只读边界。

## Host compatibility

| Host | 当前合同 |
|---|---|
| Claude Code CLI 2.1.269 | 已验证 `Agent` 的可见任务文本、pin 和 `updatedInput` 在派发前生效；明确只读的未 pin child 已实际以 Haiku 启动。生产目录为该宿主开启能力闸门与 `dispatch_nudge`；默认 profile 为 `guard`（不改写参数），每个会话第一次未 pin 派活会被拦下一次。Cloud 不从此结论外推。 |
| Codex CLI 0.154.0 | 已验证 `updatedInput` 在真实交互式子代理派发前被采纳，且不改变父代理；但原生 `collaboration.spawn_agent` 在 hook 边界交付不透明任务令牌，尚不能据此验证自动语义降档。生产目录仍保持建议式。 |
| Codex Desktop | 已验证原生 `collaboration.spawn_agent` 进入 audit hook；尚未验证 `updatedInput` 被实际派发采纳，因此只能建议式，不可标为自动路由。 |
| Codex Cloud | 独立验证；不从 CLI 或 Desktop 外推。 |

#### 别名解析是宿主运行时行为，不是 tier-guard 的承诺

Claude 候选写的是家族别名（`haiku` / `sonnet` / `opus`），因为 Agent 工具的 `model` 是四值枚举。
**别名解析到哪个具体型号，tier-guard 既不控制也不断言**：它由宿主在运行时根据远端拉取的
account-specific catalog（缓存在 `~/.claude/cache/model-catalog/`，TTL 约 59 分钟）、账号可用模型、
per-provider 覆盖和用户自己的会话模型设置共同决定。

2026-10-05 实测：同一次验收里 `haiku` → `claude-haiku-4-5-20251001`、`sonnet` → `claude-sonnet-5-5`、
而 `opus` → `claude-opus-5`（该账号的 catalog 里 `claude-opus-5-5` 同样可用，但会话模型被
`user_setting` 钉在 Opus 5）。

因此：审计记录里的 `actual_execution` 是宿主回报的事实，**不能反推成 tier-guard 选错了档**；
文档与候选目录都不得声称某个别名对应某个具体型号。

## Observability and calibration

每条 v2 审计记录至少包括：路由版本、模型目录的来源类别与内容 SHA-256 指纹（不记录目录路径）、任务指纹、
任务可见性（`visible` 或宿主不透明令牌 `opaque_token`）、信号来源、请求与目标参数、是否 pin、置信度、
`host_pre_dispatch_apply` 宿主能力状态和可观察的结果。`opaque_token` 只能走保守分类，守卫不尝试解码。
兼容字段 `applied=true` 仅表示 hook
adapter 已输出 `updatedInput`，不等于宿主接收或子代理实际执行；只有宿主明确给出时才记录
`actual_execution`、token/成本，未知即未知。

### 每次派发必记的档位字段

在既有字段之外，每条派发记录还必须能回答「这个档是怎么来的」和「这次是不是升档」：

| 字段 | 取值 | 说明 |
|---|---|---|
| `task_digest` | SHA-256 | 任务摘要哈希。既有 `prompt_sha256` 已满足，不新增字段 |
| `tier_source` | `pin` / `floor` / `upstream` / `inferred` | 本次档位的来源，对应优先级链 |
| `tier_conflict` | 对象或缺省 | 上游 tier 低于 floor 时记 `{upstream, floor}`；无冲突不写 |
| `requested` | 既有 | 请求的 model 与 reasoning_effort |
| `actual_execution` | 既有 | 宿主回报的实际模型；未知即未知，不推算 |
| `escalation` | 对象或缺省 | 升档时记 `{from, to, consecutive_failures}`；非升档不写 |

`tier_source` 与 `escalation` 是新增的；其余沿用既有字段，语义不变。

**不记录的东西**：上游 `reason` 的正文、失败日志正文、任务原文。需要关联时只记 SHA-256。

校准使用人工标注、验收结果、失败/回退率与受控抽样复跑。任何声称“节省 token 而质量未降”的结论
必须来自这类对照数据，不能从规则命中数推断。

## Non-goals

- 不做主会话模型切换、用量购买、账单代管或全局代理网关。
- 不承诺替代人工对架构、安全、不可逆动作的最终判断。
- 不训练分类器，除非后续已积累代表性标注数据并单独获得批准。
- 不自行判定子代理的成败，也不为此派验证器子代理：失败信号由上游或主代理给出。
- 不读取上游工具的文件、state 或 tracker，即使它们就装在同一台机器上。
- 不接触、不转发、不记录失败日志与上游 `reason` 的正文。

## Acceptance criteria

- 给定同一 `RouteRequest`、目录和策略版本，决定可重现并给出理由。
- 简单、明确、低风险的未 pin 子任务可以被建议或实际路由到低成本候选。
- 复杂、歧义或高风险任务不会被路由到不满足硬约束的候选。
- pin、低置信度、provider 不可用、host 不支持改写分别有可验证的行为。
- agent-skills/spec-guard 缺失或停用不会使 core 失败。
- 各宿主的“建议 / 自动 / 未支持”状态有独立端到端证据。
- 提醒与 deny 只出现在未 pin 的子代理创建事件；pin、`off`、宿主闸门关闭、无 `session_id`、异常分别有
  可验证的“不提醒 / 不 deny”行为；deny 每个会话至多一次。
- 自然触发评估在 Claude Code CLI 与 Codex CLI 上各自达到 Success criteria 的阈值，并有独立端到端证据。
- 默认 profile 为 `guard`；`guard` 下任何路径都不输出 `updatedInput`；`/tier-mode` 可直接持久设为 `guard`
  （不改写参数，不需要 auto 的质量门槛），`audit` 仍可选作只提醒、不拦截。
- 上游档位标记：恰好一次且取值合法时被采纳；0 次、≥2 次、取值非法、信封字段不符分别降级为
  `unavailable` 并走纯推断，核心不失败。
- **伪造的低档位撤销不了 floor**：一段命中 `R-IRREVERSIBLE` 的任务即使带 `tier=L1`，最终档位
  仍不低于 floor，且该次冲突被记录。这条必须有正反断言。
- `tier_source` 对 `pin` / `floor` / `upstream` / `inferred` 四种来源分别可验证。
- 升档：L1 失败按上游信号升到 L2；L2 连续失败两次产生带原因的 deny；升档后的档位不低于原档位
  也不低于 floor。
- 日志中不出现上游 `reason` 正文、失败日志正文与任务原文。这条用断言覆盖，不靠人工检查。
- 候选目录与文档都不声称某个 Claude 家族别名对应某个具体型号；`actual_execution` 与请求别名
  不一致时不得被判为路由错误。
- `SubagentStop` 的 fallback 率可从审计日志直接统计；在它降到个位数之前，任何基于 stop 事件的
  统计结论都标注为不具代表性。
