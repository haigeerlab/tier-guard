# 同类路由方案调研：四个开源实现

> 历史记录：本文的版本、默认模式、型号、价格、路径和发布状态以记录日期为准。当前使用说明见 [README](../../README.md)，现行宿主能力及限制见 [兼容性](../compatibility.md)。原始实验结果保留。

> 状态：**调研完成；结论为设计输入，未实现任何改动**　｜　日期：2026-10-05

## 方法与证据口径

四个仓库以 `--depth 50` clone 到会话临时目录（**不进本仓**），每仓派一个 Codex 子代理只读阅读，
统一 `model=gpt-6-luna` / `reasoning_effort=high`、只读沙箱、禁止网络与运行项目代码。
提示词强制要求每条结论给 `文件:行号` 出处，并明确「仓库里没有就写未找到，不要推测」。

**两类证据必须分开看**：

| 口径 | 内容 | 本文是否提供 |
|---|---|---|
| A · L1 候选适用性 | `gpt-6-luna / high` 能否胜任真实只读调研任务 | ✅ 提供 |
| B · tier-guard 分档派发 | hook 在 child 创建前选对了档 | ❌ **不提供** |

B 口径在非交互环境**造不出来**：真正的 `spawn_agent` child 只在交互式 Codex TUI 里可观察
（见 `scripts/codex-cli-preroute-smoke.sh` 开头），而 `delegate-codex.sh` 启动的是顶层会话，
不经过 tier-guard 的 PreToolUse hook，不产生路由审计记录。B 口径留给阶段 4。

**A 口径结果**：四个子代理实际运行参数均为 `gpt-6-luna / high`（wrapper 回报），
四份产出都给出了 `文件:行号`，其中两份在读不到答案时如实写「未找到」而非编造
（claude-router 的日志格式、gearbox 的失败计数状态），一份主动指出目标插件已从 main 移除。
就这项任务而言，L1 候选**够用**。

**本文转述子代理结论时保留其出处，但我没有逐条回仓核对**；下文「本仓自行核实」一节例外，
那部分是我在本机直接验证的。

## 逐仓

### 1. `Adityaraj0421/gearbox` — MIT

许可证首行 `MIT License`（`LICENSE:1`）。MIT 与 Apache-2.0 兼容，复用需保留版权声明与许可证文本。

- 路由判据写在 `routing/routing.md`，按**范围 / 模糊度 / 影响范围**三维打分映射到档位
  （`routing/routing.md:43-45`）。是 Markdown 策略文本，不是代码判定；项目可放
  `.claude/routing.md` 覆盖默认（`README.md:53-55`）。
- 升档策略：同一根因失败两次后升一级，并把**完整失败报告**交给下一层
  （`routing/routing.md:46-50`、`agents/builder.md:14`）。
  ⚠️ **失败计数的存储位置、计数键与重置时机：子代理报告「未找到」** —— 仓库只写了策略要求，
  没有定义计数状态机制。
- 验证器 `gearbox:verifier` 用 Haiku。输入 = 原始任务 + 实现者的完成/升档报告 + 委派前的
  BASELINE git status，并自行检查 diff（`agents/verifier.md:7,13-21`）。
  输出以 `VERDICT: APPROVE` 或 `VERDICT: REJECT` 开头，说明 ≤150 词（`agents/verifier.md:32-44`）。
  REJECT → 交回同层重做一次；第二次 REJECT → 升一级（`routing/routing.md:115-116`）。
- JSONL 字段（`hooks/scripts/log-routing.py:63-80`）：`ts`、`delegation_id`、`session_id`、
  `tool_name`、`subagent_type`、`is_named_tier`、`fallback`、`model`、`prompt_head`、`cwd`、
  `cost_source`，`cost` 有数据才写。另有 verdict 日志（`log-verdict.py:157-164`）与升档日志
  （`log-escalation.py:37-44`，**实际写入字段中没有 `reason`**）。

### 2. `vimoxshah/claude-router` — MIT

许可证首行 `MIT License`（`LICENSE:1`）。

- **纯文档路由**：规则写在 `ROUTING.md`，由 `SKILL.md` 要求主代理照触发表执行
  （`ROUTING.md:27-36`、`SKILL.md:40-46`）。没有自动路由代码，也没有配置驱动引擎。
- 升档带失败日志：去 `hard-implementer` 时下一次派发包含「限定任务 + failure log」，
  且要求它先读前次失败日志（`ROUTING.md:33,47`、`agents/hard-implementer.md:14`）。
  ⚠️ **日志的内容格式与拼接位置：子代理报告「未找到」** —— 无法判断传的是完整日志、摘要还是
  错误类型。
- 「代码难」vs「设计难」按**问题性质**判断，不是关键词或长度规则：逻辑反复 / 推理密集 /
  顽固 bug → `hard-implementer`；阻碍是设计决策（接口选择、契约含糊、非平凡算法）→ 先咨询
  `advisor`（`ROUTING.md:47`、`agents/implementer.md:36`）。

### 3. `PremPrakashCodes/claude-code-plugins` 的 agent-router — MIT

许可证首行 `MIT License`（`LICENSE:1`）。插件在 `plugins/agent-router/`。

> ⚠️ 子代理主动报告：**main 的 CHANGELOG 记录该插件已被移除**（`CHANGELOG.md:10-12`），
> 下述内容依据本地历史中 PR #2 合并版本的文件。引用前请确认它是否仍是作者维护的方案。

四个仓库里**唯一的代码驱动实现**（判据在 `classifier.py` 的系统提示词中硬编码，
档位映射与置信度阈值可配置覆盖——混合方式：`classifier.py:38-52`、`config.py:20-33`）。

- **只降不升**：`data.py:23-24` 按模型家族定义价格等级；`hooks.py:162-185` 比较候选与会话模型，
  未知家族 / 候选更贵 / 同家族一律保留原输入，**只有候选更便宜才写入新 `model`**。
- **失败时保持原模型**：分类失败或无 tier 时记 fallback 并返回空改写；分类器把超时、执行错误、
  非零退出、坏输出都归为失败（`hooks.py:134-143`、`classifier.py:161-200`）。
- **pin 识别读三个来源**（`data.py:87-89,110-127`、`hooks.py:119-132`）：
  1. dispatch 的 `tool_input.model`（去空白后非空）
  2. agent 定义 frontmatter 的 `model`（排除 `inherit`）
  3. 非空的 **`CLAUDE_CODE_SUBAGENT_MODEL`** 环境变量

  命中即记 override 并保留，不调用分类器。

### 4. `Renga154/model-router` — MIT

许可证首行 `MIT License`（`LICENSE:1`）。

- **双宿主布局**：同一份 `SKILL.md` + `references/` + `scripts/` 链接到
  `~/.agents/skills/model-router/`（Codex）与 `~/.claude/skills/model-router/`（Claude Code）；
  项目级则复制到 `.agents/` 与 `.claude/`（`README.md:153-163`、`install/install.sh:48-58,93-110`）。
- **参数形状差异靠「预制档位」化解**，不靠在调用里传 effort：
  - Claude Code → `install/agents/route-{lite,std,deep}.md` 安装到 `.claude/agents/`，
    agent 定义的 frontmatter 带 `model:` 和 `effort:`（`install/agents/route-lite.md:1-5`）；
    调用时只选 `subagent_type`。
  - Codex → `install/codex/{lite,std,deep}.config.toml` 安装到 `~/.codex/`，各自设 `model` 与
    `model_reasoning_effort`；调用 `codex exec --profile lite|std|deep`
    （`references/platforms.md:5-16`、`install/codex/lite.config.toml:1-2`）。
- 判据分层：难度分级与硬规则在 `SKILL.md:10-32`；档位→宿主目标/模型/effort 的映射在
  `references/routing.md:1-25`，文档称其为单一来源的表格。
- **没有宿主或版本自动检测**；文档称宿主可从 system prompt 判断。Claude agent 定义缺失时回退到
  `general-purpose` 并显式指定 `model`（`references/platforms.md:3,7-8`、`references/routing.md:27`）。

## 横向观察

| | gearbox | claude-router | agent-router | model-router |
|---|---|---|---|---|
| 判据形态 | Markdown 策略 | Markdown 策略 | **代码 + 配置** | Markdown + 宿主配置 |
| 谁执行路由 | 主代理（含 hook 记日志） | 主代理 | **hook 自动改写** | 主代理 |
| 落参方式 | 具名档位 subagent | 具名 agent | 改写 `tool_input.model` | **预制 agent / profile** |
| 升档机制 | 有（2 次失败） | 有 | 无（只降不升） | 未报告 |

**四个里有三个不改写派发参数，而是让主代理选一个预先定义好的档位 agent。** 只有 agent-router
走 hook 改写 `tool_input.model`，也就是 tier-guard 现在的路线——而它恰好已从 main 移除。

## 本仓自行核实（我在本机直接验证，非子代理转述）

调研触发了三项对 Claude Code 2.1.289 安装文件的核实，结果直接影响本仓设计：

1. **agent 定义可以承载 `model` 与工具限制。** 本机 19 个 `~/.claude/agents/*.md` 全部带
   `model:`，其中 8 个带 `disallowedTools:`。Agent 工具的 `model` 参数描述也写明它
   "Takes precedence over the agent definition's model frontmatter"。
   因此**「Claude 侧没有工具限制通道」这个说法只对 Agent 工具的内联参数成立，对整个宿主不成立**
   （见 [模型目录更新](2026-10-model-catalog-update.md) 中的对应段落，该处表述偏窄）。
   agent 定义的 frontmatter 能否承载 reasoning effort：**未核实**，本机 19 个文件都带一个
   `level:` 键（取值 2/3/4），但没有证据表明 Claude Code 读它。

2. **`subagent_type` 在 Agent 工具的输入 schema 里**，所以 hook 改写它在架构上是可行的——
   这正是 gearbox 与 model-router 的落参方式。

3. **两个会让 tier-guard 改写静默失效的宿主开关**（均在 2.1.289 中实际存在）：
   - `CLAUDE_CODE_COORDINATOR_FORCE_WORKER_INHERIT_MODEL`
   - `CLAUDE_CODE_SUBAGENT_MODEL_FORCE`

   命中任一时宿主提示 "The model parameter is ignored on this session. Do not set it."
   本机两者均未设置。本仓 spec 的 Host compatibility 一节没有记录这条路径。

4. **tier-guard 的 pin 识别漏了一个来源。** `CLAUDE_CODE_SUBAGENT_MODEL` 在 Claude Code
   2.1.289 中出现 16 次、是被实际读取的配置；在本仓中出现 **0 次**。
   `hooks/claude_hook.py:175` 的 `pinned` 只看 `tool_input.model` 与 agent frontmatter。
   agent-router 把它算作 pin。本机未设置，当前默认 `guard` 也不改写，所以无实际损害；
   但一旦启用 `auto`，设了该变量的用户会看到自己的显式选择被覆盖，违反
   「显式 model 或 reasoning_effort 是 pin，绝不改写」。

## 可借鉴点 → tier-guard 改动建议

| # | 来源 | 可借鉴点 | 建议 |
|---|---|---|---|
| 1 | agent-router | pin 识别包含 `CLAUDE_CODE_SUBAGENT_MODEL` | **建议采纳。** 先定语义（配置级默认算不算 pin），再改 `claude_hook.py` 的 `pinned` 判定并补正反断言 |
| 2 | 本仓核实 | 两个 FORCE 开关会让改写静默失效 | **建议采纳。** 写进 spec 的 Host compatibility；可在审计记录里加一个宿主开关状态字段，避免把「改写被忽略」误记成「已应用」 |
| 3 | gearbox | 升档日志单独成条，字段含 `from_tier`/`to_tier` | **建议采纳形态，不照搬字段。** 本仓日志已有 `applied`/`actual`，升档宜单独一条便于统计 |
| 4 | gearbox | 日志记 `is_named_tier` / `fallback` 区分「按档位派发」与「兜底」 | **建议采纳。** 本仓已有 `fallback`，缺少「这次是否命中具名档位」 |
| 5 | model-router | 预制档位 agent / profile，调用方只选档位名 | **建议进入阶段 3 讨论，不急于采纳。** 它能绕开 Claude 无 effort 通道的限制，但会把 tier-guard 从「零安装依赖的 hook」变成「需要安装档位 agent 文件」，与本仓「交付形态必须是插件」的已定决策冲突 |
| 6 | gearbox | 独立验证器（Haiku）审查 diff，REJECT 两次才升档 | **建议进入阶段 3 讨论。** 与本仓「打回率」观测指标天然契合，但引入了 tier-guard 当前没有的「派发后评估」职责 |

## 明确不采纳

| 项 | 来源 | 不采纳原因 |
|---|---|---|
| 把判据改成 Markdown 策略文本 | gearbox / claude-router / model-router | 本仓已定决策：**判据只在 `hooks/route_decide.py`**，任何一方内联重写判据等于一条关不掉的假警报。Markdown 策略无法被 `--selftest` 和变异测试覆盖 |
| 「只降不升」作为硬规则 | agent-router | 与本仓安全边界冲突。本仓是「只升不降」：不可逆 / 取舍 / 跨模块 / 信息不足必须**升**到高能力候选。两者方向相反，不可混用 |
| LLM 分类器决定档位 | agent-router | `classifier.py` 用模型判断难度。本仓判据必须可离线自测、可变异验证；引入模型调用会让 hook 变慢、不确定，且违反「守卫任何异常路径一律放行」的可预测性要求 |
| 按关键词区分「代码难 / 设计难」 | claude-router | 它本身就不是关键词规则，而是让主代理按问题性质判断。本仓已有 `R-TRADEOFF` 词表承担类似职责，再加一层语义分类无新增信息 |
| 复制任何代码 | 全部 | 本阶段只借鉴思路。四仓均为 MIT，与 Apache-2.0 兼容，**若日后确需复用代码**，必须保留原版权声明与 MIT 许可证文本，并在本仓标注来源 |

## 本次调研的局限

- 每仓只派一个子代理读一遍，没有交叉复核；子代理给出的 `文件:行号` 我没有逐条回仓核对。
- 两处关键问题子代理报告「未找到」（gearbox 的失败计数状态、claude-router 的失败日志格式），
  若这两点要作为设计依据，需要人工再读一次。
- agent-router 已从其仓库 main 移除，它的方案可能已被作者本人否定；采纳其思路前宜先了解移除原因。
