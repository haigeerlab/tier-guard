# v2 候选目录更新：Codex 换到 gpt-6 代

> 状态：**候选目录已更新；新目录下的宿主三档派发未复验**　｜　插件：tier-guard 0.2.1　｜　日期：2026-10-05

本文记录 2026-10-05 把 v2 候选目录的 Codex 列从 `gpt-5.6-*` 换到 `gpt-6` 代的依据、
实测的可用性证据，以及这次**没有**改动的东西和原因。

## 变更

| 所需能力 | Claude Code | Codex CLI（旧） | Codex CLI（新） |
|---|---|---|---|
| mechanical + read_only | `haiku`（未变） | `gpt-5.6-luna` / `medium` | `gpt-6-luna` / `high` |
| implementation + bounded_change | `sonnet`（未变） | `gpt-5.6-terra` / `high` | `gpt-6.1-sol` / `medium` |
| tradeoff + cross_cutting | `opus`（未变） | `gpt-5.6-terra` / `xhigh` | `gpt-6.1-sol` / `xhigh` |

候选 id 随之改名：`codex-luna-medium` → `codex-luna-high`、`codex-terra-high` →
`codex-sol-medium`、`codex-terra-xhigh` → `codex-sol-xhigh`。

## 依据（用户提供的 2026-10 公开数据，**本仓未独立核验**）

| 模型 | 输入 / 输出（每百万 token） | 智能指数 |
|---|---|---|
| `gpt-5.6-terra` | $2 / $12 | ≈ 42 |
| `gpt-6.1-sol` | $2 / $10 | ≈ 52 |
| `gpt-5.6-luna` | $0.20 / $1.20 | ≈ 37.5 |
| `gpt-6-luna` | $0.10 / $0.50 | ≈ 37 |

推论：

- **terra 移出目录** —— 比 sol 更贵（输出 $12 对 $10）且更弱（42 对 52）。同时被更便宜更强的
  候选支配，没有保留理由。
- **L1 换 luna 6** —— 价格是 5.6 代的一半，分数基本持平（37 对 37.5）。
- **L2 / L3 同 slug 只动 effort** —— 延续「升档只许动 effort，不许换 slug」的既有约束。

这些数字由用户在 2026-10-05 会话中提供，标注为公开数据。本仓**没有**对价格或智能指数做独立
核验，引用时请回到原始来源。本次改动中可核对的部分只有下面的可用性实测。

## 可用性实测（本仓实测，2026-10-05）

宿主：`codex-cli 0.160.0`，macOS，ChatGPT 账号（非 API key）。
方法：`~/.claude/scripts/delegate-codex.sh --model <slug> --effort <level>`，只读沙箱，
提示词为固定回声串。

**先建立探针有效性（反向对照）**：

| 输入 | 结果 |
|---|---|
| `gpt-9-doesnotexist` / `low` | `warning: Model metadata ... not found` + HTTP 400 `The 'gpt-9-doesnotexist' model is not supported when using Codex with a ChatGPT account.` |

不存在的 slug 会在产出任何内容前被服务端拒绝，因此下面三次成功回复可以作为「服务端接受了该
组合」的证据。

| 组合 | 结果 |
|---|---|
| `gpt-6-luna` / `high` | ✅ 回 `PROBE_L1` |
| `gpt-6.1-sol` / `medium` | ✅ 回 `PROBE_L2` |
| `gpt-6.1-sol` / `xhigh` | ✅ 回 `PROBE_L3` |

旁证：已装的 `codex-cli 0.160.0` 二进制字符串表中包含 `gpt-6-luna` 与 `gpt-6.1-sol`
（另有 `gpt-6-sol`、`gpt-6-astra`、`gpt-6-pro`）。

**这组证据的边界**：wrapper 走 ephemeral 会话，不落 rollout 文件，因此**无法独立核对服务端
实际采用的 reasoning effort**，只能确认它没有拒绝该取值。

## Claude 侧为什么一个字都没改

目标表原本要求 Claude 列用完整 ID、L2 带 `effort medium`、L1 限制为只读工具。实测后三条都
不成立或已满足：

> **更正（2026-10-05 实测后）**：本节初稿写过「别名已经指向目标模型」，并贴了一张从安装文件
> grep 出来的映射表。**那是错的，而且错在性质上。** 详见下面的「别名解析不是可断言的属性」。

**Agent 工具的输入 schema 只有 6 个字段**（从 2.1.289 安装文件提取）：

```js
u({ description, prompt, subagent_type,
    model: enum(["sonnet","opus","haiku","fable"]).optional(),
    run_in_background, team_name, cwd })
```

由此：

- **完整 ID 不能写进目录** —— `model` 是严格四值枚举，写 `claude-sonnet-5-5` 会让 hook 产出
  schema 非法的 `updatedInput`。目录里只能写别名。
- **没有 effort 通道** —— schema 里不存在 `reasoning_effort` / `effort` / `thinking` 字段。
  Claude 候选的 `reasoning_effort` 保持 `null`。该事实已写成 `test-route-contract.py` 中的
  可执行断言。
- **没有工具限制通道** —— schema 里不存在 `tools` / `allowedTools` 字段。限制子代理工具集需要
  经 agent 定义文件实现，属于独立功能，不在本次路由表改动范围内。

### 别名解析不是可断言的属性

初稿的错误有两层。表层是读错了结构：grep 到的那行是 `latest_per_family`（每个家族的最新型号），
不是别名解析表。深层的问题更要紧——**即便读对了，那个结论也不该下**。

2026-10-05 的真实派活回执暴露了这点：

| 别名 | 实际解析到 |
|---|---|
| `haiku` | `claude-haiku-4-5-20251001` |
| `sonnet` | `claude-sonnet-5-5` |
| `opus` | **`claude-opus-5`**，不是初稿断言的 `claude-opus-5-5` |

查下来的事实（均在本机核实）：

- 二进制里**有两套 baked catalog**，一套 `opus → claude-opus-5`、另一套 `opus → claude-opus-5-5`。
  它们只是兜底。
- 实际生效的是远端拉取的 catalog，缓存在 `~/.claude/cache/model-catalog/`（本机 28 份），
  带 `fetchedAt` / `staleAt`，**TTL 59 分钟**，按账号区分。
- 该 catalog 里 `claude-opus-5` 与 `claude-opus-5-5` **都可用**；
  `state.model = claude-opus-5`、`selection_source = user_setting` —— 用户把会话模型钉在了 Opus 5。
- 家族内还有 per-provider 覆盖（bedrock / vertex / foundry / gateway / mantle 各不相同）。

「别名在家族内跟随用户已选模型」是与上述观测最自洽的解释，但**本机无法证明这条因果**，
所以不写成结论。

**能写成结论的是**：别名解析到哪个具体型号，由宿主在运行时根据远端 catalog、账号可用模型、
provider 覆盖和用户自己的模型设置共同决定，每小时还会刷新。**这不是一个稳定属性，文档不应断言它。**

tier-guard 按**家族别名**路由；具体型号不在它的控制范围内，也不该出现在它的候选目录或承诺里。
这不改变「Claude 列不动」这个决定——Agent 工具的四值枚举本来就只接受别名——但它改变了理由。

**顺带发现的风险**：Agent 工具 `model` 参数的描述文本中有一条条件分支——
`CLAUDE_CODE_COORDINATOR_FORCE_WORKER_INHERIT_MODEL` 开启时提示
"Unavailable on this session: this parameter is ignored — do not set it."。
即该开关会让 tier-guard 的改写**静默失效**。本机未设置，但这是宿主边界的一条未记录路径。

## v1 兼容层为什么冻结

`check_config` 按 `schema_version` 分流：生产 hook 加载 `routing.catalog.v2.json`
（`schema_version: 2`），只走 `_check_catalog`。v1 的
`routing.default.json` 及其不变量只在显式加载该文件时生效。

v1 有一条 `Codex effort 必须随档位单调不降` 的不变量。新表 L1=`high` → L2=`medium` 违反它。
由于 v1 是兼容层而非生产路径，2026-10-05 用户确认**冻结 v1 表**（保留 `gpt-5.6-*`），
只更新 v2 目录，以免为了迁就兼容层而削弱「只升不降」这条安全边界。

## `never_auto` 的现状（需要注意）

`never_auto.codex_models = ["gpt-6-astra", "gpt-5.6-sol"]` 只存在于 **v1** 配置中。
**v2 目录没有 `never_auto` 等价物** —— `_check_catalog` 不读这个字段。

v2 里「不许自动选某个模型」的机制是：候选必须在 `candidates` 中列出，且
`auto_eligible: true`。未列出的模型根本不可能被选中。因此 `gpt-6-astra`、`gpt-6-pro`、
`gpt-5.6-sol` 在 v2 下仍然选不到——但靠的是「不在表里」，不是一条显式的禁止规则。

2026-10-05 用户确认保留 v1 的 `never_auto` 条目。需要注意这在生产路径上是无操作的；若要在 v2
得到同样的显式禁止语义，需要新增字段与校验，属于独立改动。

## 尚未复验

- 新目录下 Codex 主代理明文预路由的三档实际 child 回执（旧证据见
  [v2 compatibility status](2026-09-12-v2-compatibility-status.md)，是 `26.908.40834` /
  CLI `0.154.0` 下按旧目录取得的）。
- 当前宿主为 Codex Desktop `26.930.31730` / CLI `0.160.0`，与全部既有 Codex 证据的版本
  （`26.908.40834` / `0.154.0`）不同。`spawn_agent` 在 hook 边界的 payload 形状是否变化
  未经验证——`fork_turns` 那个缺陷当初正是读 `rust-v0.154.0` 源码定位的。
- Codex 宿主能力闸门（`pre_dispatch_apply`、`dispatch_nudge`）保持关闭，本次未改动。
