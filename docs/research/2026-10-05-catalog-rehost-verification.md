# 新候选目录的宿主复验：执行协议

> 状态：**A / B / C 均已通过**（A 在 0.2.2 发布后复跑）　｜　日期：2026-10-05　｜　执行人：用户 + 主会话
>
> 本文是阶段 4 的执行清单，结果回填到下方「结果」各节。**在填入真实回执前，任何一节都不构成通过。**

## 为什么要复验

两件事同时变了，既有证据都不再直接适用：

1. **候选目录换代**（提交 `98f6fb8`）。Codex 列从 `gpt-5.6-luna` / `gpt-5.6-terra` 换成
   `gpt-6-luna` / `gpt-6.1-sol`。既有三档回执证据取自旧目录。
2. **宿主版本跨代**。全部既有 Codex 证据来自 Desktop `26.908.40834` / CLI `0.154.0`；当前是
   Desktop `26.930.31730` / CLI `0.160.0`。`fork_turns` 那个缺陷当初正是读 `rust-v0.154.0`
   源码定位的，`spawn_agent` 在 hook 边界的 payload 形状是否变化**无人验证**。

Claude 侧候选未变（别名 `haiku`/`sonnet`/`opus` 本来就解析到目标模型），但 `claude_hook.py` 因
pin 修复改动过（提交 `e90f3f6`），且 CLI 从 `2.1.269` 升到 `2.1.289`，仍需复验。

## 已在本机核实的前置（不需要你重跑）

- `gpt-6-luna / high`、`gpt-6.1-sol / medium`、`gpt-6.1-sol / xhigh` 三个组合服务端均接受；
  反向对照（不存在的 slug）被 HTTP 400 拒绝。见 [模型目录更新](2026-10-model-catalog-update.md)。
- `~/.codex/state_5.sqlite` 的 `threads` 表在 0.160.0 下仍有脚本需要的全部列，另新增
  `cli_version` 列。
- 三个会影响 tier-guard 的宿主开关（`CLAUDE_CODE_SUBAGENT_MODEL`、
  `CLAUDE_CODE_SUBAGENT_MODEL_FORCE`、`CLAUDE_CODE_COORDINATOR_FORCE_WORKER_INHERIT_MODEL`）
  本机均未设置。
- `scripts/validate.sh` 全绿（451 条断言），`mutation-check.py` 0 存活。

---

## smoke 脚本已按新目录更新（提交随本文一起）

`scripts/codex-cli-preroute-smoke.sh` 原本是为旧目录写的，直接运行会用**错误的通过条件**验收。
已改五处：

| 行 | 改动 |
|---|---|
| 22 | child B 回声串 `CLI_PREROUTE_TERRA_OK` → `CLI_PREROUTE_SOL_OK` |
| 26 | 开场说明：父代理改述，并写明本次是用 `TIER_GUARD_MODE=audit` 强制覆盖、生产默认是 `guard` |
| 30 | 父代理 `-m gpt-5.6-terra` → `-m gpt-6.1-sol`（effort 仍 `high`） |
| 50 | SQLite 查询加 `cli_version` 列，并补一行表头 |
| 57 | 通过条件改为新三档，并补一句「任何 child 出现 sol/high 即为继承而非路由」 |

**父代理为什么是 `gpt-6.1-sol / high`**：`(sol, high)` **不等于任何一个子代理目标**
（目标是 luna/high、sol/medium、sol/xhigh），所以一旦某个 child 回执是 sol/high，立刻能判定它
继承了父参数而非被路由——继承和路由不会混淆。

**为什么加 `cli_version`**：这次复验的核心风险就是宿主版本跨代（0.154 → 0.160），把产出回执的
CLI 版本直接钉进证据，比事后回忆可靠。该列是 0.160 的 `threads` 表新增的，已确认存在。

脚本改完已过 `/bin/bash -n` 与内嵌 python 的语法检查，并自查了本仓的 bash 3.2 / `grep -q` /
`sed -i` / `timeout` 约束。

## A · Codex：主代理明文预路由三档（在真实 TUI 中执行）

`codex exec` 不行：该入口的 collaboration wait 不创建可观察 child。（**2026-10-05 更正**：这是 CLI 0.154 时的结论；
在 0.160.0 上 `codex exec` 能派出子代理——spec-guard 联调的 exec 运行在线程表里都有 `thread_spawn` 子线程，`parent_thread_id` 指向主线程。下面的 TUI 流程仍然有效。）**必须在交互式 Terminal/TUI 中跑。**

```bash
cd /Users/vilin/Documents/haigeerlab/tier-guard && /bin/bash scripts/codex-cli-preroute-smoke.sh
```

脚本会自建隔离工作目录与独立审计目录，不污染本仓也不写生产审计日志。流程：

1. 脚本打印隔离目录路径，然后进入 Codex TUI 并自动投喂提示词。
2. TUI 里会依次出现三个 child。**等三个回复都出现**（`CLI_PREROUTE_LUNA_OK` /
   `CLI_PREROUTE_SOL_OK` / `CLI_PREROUTE_XHIGH_OK`）。
3. 退出 Codex 回到脚本，它会自动打印审计记录和 SQLite 线程回执。

**通过条件**（三条全中才算通过）：

- 三个 child 回复都出现；
- 审计目录有三条对应记录；
- SQLite 线程回执依次为 `gpt-6-luna / high`、`gpt-6.1-sol / medium`、`gpt-6.1-sol / xhigh`；
- 父线程保持 `gpt-6.1-sol / high` 不变。

**预期会看到、但不算失败的现象**：三条 hook 审计记录的 `task_visibility` 应为 `opaque_token`、
`applied=false`。这是 Codex Multi-Agent V2 的已知边界（[#33284](https://github.com/openai/codex/issues/33284)），
不是本次改动引入的。

### 结果

**0.2.2 复跑：通过。**（2026-10-05 发布 `v0.2.2` 并装到两个宿主后，同一脚本，隔离目录
`tier-guard-cli-preroute.D6Pnil`。）

| 线程 | 实际 model / effort | 审计记录 requested | 子线程自己的回复 |
|---|---|---|---|
| 父 | `gpt-6.1-sol / high` | — | — |
| child_a | **`gpt-6-luna / high`** | `gpt-6-luna / high`，pinned | `CLI_PREROUTE_LUNA_OK` |
| child_b | **`gpt-6.1-sol / medium`** | `gpt-6.1-sol / medium`，pinned | `CLI_PREROUTE_SOL_OK` |
| child_c | **`gpt-6.1-sol / xhigh`** | `gpt-6.1-sol / xhigh`，pinned | `CLI_PREROUTE_XHIGH_OK` |

四条通过条件全中：三个回复都在（从各子线程自己的 rollout 读出，不只看父代理的汇总）；3 条审计记录
的 `catalog_identity.sha256` 都是新目录 `7ce63580…`；线程回执与新目录三档逐一对应；父线程
`sol / high` 未变，没有任何 child 出现 `sol / high`。`task_visibility`、`applied`、`fallback`
与首轮相同。

要让宿主拿到新目录，除了发版还需要一步：Codex 的 marketplace 在 `~/.codex/config.toml` 里钉了
`ref = "v0.2.1"`，`marketplace upgrade` 只会刷新到所钉的 tag。把它改成 `v0.2.2` 后重装才生效。
**今后每次发版，Codex 侧都要同步改这个 ref。**

**首轮（0.2.1 安装版）：宿主机制通过，新目录未覆盖。**（2026-10-05 02:06–02:07，Codex CLI `0.160.0`，隔离目录
`tier-guard-cli-preroute.wZZTkw`，3 条审计记录、4 条线程回执。）

| 线程 | 实际 model / effort | 对应审计记录 requested |
|---|---|---|
| 父 | `gpt-6.1-sol / high` | — |
| child_a | `gpt-5.6-luna / medium` | `gpt-5.6-luna / medium`，pinned |
| child_b | `gpt-5.6-terra / high` | `gpt-5.6-terra / high`，pinned |
| child_c | `gpt-5.6-terra / xhigh` | `gpt-5.6-terra / xhigh`，pinned |

三个回声串都出现。三档各不相同、与审计记录逐条一致、父线程未变——**主代理读技能、按档显式传参、
宿主照参执行这条链在 0.160 下完好**，没有继承。

**但这是旧目录的三档。** 审计记录的 `catalog_identity.sha256` 是 `1ef8289d…`，即已发布的
`0.2.1`；本仓当前目录是 `7ce63580…`。Codex 侧插件缓存按版本号建目录
（`~/.codex/plugins/cache/tier-guard/tier-guard/0.2.1/`），目录换代的提交没有改版本号，所以
宿主拿不到新目录。**通过条件里的 `gpt-6-luna / high`、`gpt-6.1-sol / medium`、`gpt-6.1-sol / xhigh`
没有出现，按定义 A 不算通过。** 要真验新目录，需先发 0.2.2 让 Codex 重新安装。

预期内现象均如协议所述：`task_visibility = opaque_token`、`applied = false`。另外三条记录的
推断都是 `tradeoff + cross_cutting`、置信度 `low`、建议 `codex-terra-xhigh`——hook 看不到任务明文，
信号全为 `unknown`，于是按最保守档建议。这是同一个已知边界的另一面，不是新问题；audit 下也不会据此改写。

---

## B · Codex：payload 形状是否随 0.154 → 0.160 变化

这是本次最可能出问题、也最没人验证过的一项。上一轮 `fork_turns` 缺陷就是这类问题。

在 A 跑完后，从同一个隔离审计目录取一条原始记录：

```bash
python3 -c "
import json,sys
p=sys.argv[1]
for line in open(p):
    r=json.loads(line)
    if r.get('event')=='codex-spawn':
        print(json.dumps({k:r[k] for k in r if k not in ('prompt_sha256',)}, ensure_ascii=False, indent=2)); break
" <隔离审计目录>/decisions.jsonl
```

**要看的**：`decision.requested` 里有没有出现 0.154 时代没有的字段，`task_visibility` 是否仍是
`opaque_token`，以及 `fallback` 是否为空。任何一条异常都说明 payload 形状变了，需要先修适配层
再谈路由。

### 结果

**通过，带一条边界。** 把 A 的 3 条记录与本机 Codex 审计日志里全部 20 条旧 `codex-spawn` v2 记录
（按 `session_id` 回查线程表：`0.154.0` 2 条、`0.154.0-alpha.6.2` 13 条、`0.155.0-alpha.9*` 4 条、
`0.158.0-alpha.2.1` 1 条）逐层比对键集：

| 层 | 新增 | 消失 |
|---|---|---|
| 顶层 | 无 | 无 |
| `decision` | 无 | 无 |
| `decision.requested` | 无 | 无（仍是 `model` / `reasoning_effort` / `pinned`） |

`task_visibility` 仍为 `opaque_token`，三条 `fallback` 均为 `null`，`task_name` 正确取到
`child_a` / `child_b` / `child_c`，requested 的 model/effort 与线程表一致——适配层解析出的东西都对。

**边界**：比对的是 hook **写出来的**记录形状，不是宿主原始 payload。hook 不读的新字段不会出现在
记录里；本仓不落原始 payload，所以「0.160 的 payload 里多了某个 hook 尚未利用的字段」这件事
测不出来。能下的结论是：**hook 依赖的字段在 0.160 下都还在、语义没变。**

---

## C · Claude Code：三档 + pin（含本次新修的 env pin）

复用既有的 A/B/C/D 协议（见 [Claude CLI v2 e2e](2026-09-13-claude-cli-v2-e2e.md)），**新增 E**。

用已安装的插件跑（不要加 `--plugin-dir`，那会绕过安装版）：

```bash
cd /Users/vilin/Documents/haigeerlab/tier-guard && claude
```

在会话里依次派五个子代理。前四个沿用原协议：

| 子任务 | 构造 | 预期 |
|---|---|---|
| A | 只读标记 +「验收」行 | 选 `haiku` |
| B | 实现标记 + 范围标记 +「验收」行 | 选 `sonnet` |
| C | 取舍词 | 选 `opus` |
| D | 同 A，但显式传 `model=sonnet` | pinned，不改写，建议 haiku |

**E 是本次新增，专门验 pin 修复**。另开一个终端，带环境变量启动：

```bash
cd /Users/vilin/Documents/haigeerlab/tier-guard && CLAUDE_CODE_SUBAGENT_MODEL=sonnet claude
```

在该会话里派一个**与 A 完全相同**的只读子任务，**不传** `model` 参数。

| 子任务 | 构造 | 预期 |
|---|---|---|
| E | 同 A，不传 model，但 `CLAUDE_CODE_SUBAGENT_MODEL=sonnet` | **记为 pinned、不改写**；修复前这里会被当成未 pin |

E 是这次 pin 修复的真实宿主验证。修复前的行为是：tier-guard 看不到该变量 → 判为未 pin →
`guard` 下第一次派活被 deny、`auto` 下会改写覆盖你的显式选择。

跑完用：

```bash
/tier-guard:tier-report
```

**通过条件**：A/B/C 三档的「实际执行」与「选择」一致并入账；D 的 pin 未被打扰；
**E 记为 pinned 且 applied=false**。

### 结果

**A/B/C/D 已完成**（2026-10-05 18:10–18:17，由主会话用 Agent 工具直接派发，
插件为已安装的 `0.2.1`，工作树停在 `8ff0b78`）。E 另行执行，见下方「E」。

| | requested | tier-guard 建议 | action | nudge | 实际执行 |
|---|---|---|---|---|---|
| A（首次未 pin） | — | haiku | select | **denied** | — |
| A（重派） | haiku | haiku | keep | none | `claude-haiku-4-5-20251001` |
| B | sonnet | sonnet | keep | none | `claude-sonnet-5-5` |
| C | opus | opus | keep | none | `claude-opus-5` |
| D | sonnet | **haiku** | lower | none | `claude-sonnet-5-5` |

通过：三档建议与任务类型一一对应；拦截**整个会话只发生一次**；D 的 pin 被记录为方向性建议
（`lower` → haiku）但 `target=null`、`applied=false`，未被改写。

两处口径更正：

- 协议初稿写 D 应为 `action == "pinned"`。**错了**：`pinned` 是 auto 的分支，guard 下 pin 请求
  走方向性审计（`raise`/`lower`/`keep`）。仓里本就有一条变异体守着这个区别。`lower` 才是对的。
- C 的实际执行是 `claude-opus-5` 而非 `claude-opus-5-5`。**这不是路由错误**，见
  [模型目录更新](2026-10-model-catalog-update.md) 的「别名解析不是可断言的属性」一节。

**E 通过**（2026-10-05，`claude -p --plugin-dir .`，HEAD `3224121`，独立审计目录）。启动命令带
`CLAUDE_CODE_SUBAGENT_MODEL=sonnet TIER_GUARD_MODE=audit`，提示词要求派活时既不传 `model` 也不传
`subagent_type`。

| 核对项 | 结果 |
|---|---|
| 父代理 Agent 调用的参数键 | `description` / `prompt` / `run_in_background`——**没有 `model`** |
| 审计记录 | 1 条：`pinned = true`、`requested.model = sonnet`、`action = raise`、`nudge = none`、`applied = false` |
| 子代理实际执行 | `claude-sonnet-5-5` |

调用里没有 `model`，记录却是 pinned 且 requested 为 `sonnet`——pin 只可能来自环境变量，正是
`e90f3f6` 修的那条路径。修复前这里会判为未 pin，guard 下首次派活会被 deny。

**偏离协议的一处**：协议要求用已安装插件跑，E 用了 `--plugin-dir .`。原因同 A 节——已安装的
`0.2.1` 不含 pin 修复，用它跑只能复现修复前的行为。顺带核实了 `--plugin-dir` 会**遮蔽**同名的已安装
插件而不是并存：唯一那条记录的目录指纹是工作树的 `7ce63580…`，不是安装版的 `1ef8289d…`；同一分钟
生产日志 0 条，安装版 hook 没有触发。

本轮顺带暴露的三件事（均已核实，已写进 spec）：v2 的 stop handler 不写 `escalated`；
真实日志里带该字段的记录 0 条；3034 条 stop 里 2601 条（85.7%）是 `FileNotFoundError` fallback。

---

## D · 需要回传的东西

| # | 内容 | 怎么取 |
|---|---|---|
| 1 | Codex smoke 的完整终端输出 | 脚本自己会打印审计记录与 SQLite 回执，整段复制 |
| 2 | 隔离审计目录路径 | 脚本第一行打印 |
| 3 | B 节那条原始 `codex-spawn` 记录 | 上面的 python 片段输出 |
| 4 | `/tier-guard:tier-report` 的完整输出 | Claude 会话里直接复制 |
| 5 | 两个宿主的版本 | `codex --version`、`claude --version`、Desktop 关于页 |

**不要回传的**：任务原文、子代理回复正文（回声串除外）、任何 `~/.codex` 或 `~/.claude` 下的
凭据文件。审计记录本身只含长度与 SHA-256，可以整条贴。

## 这次复验不覆盖的

- **Codex 闸门仍关闭**，本协议不改 `pre_dispatch_apply` / `dispatch_nudge`，也不验证 Codex 侧的
  `updatedInput` 是否被采纳——那仍是 Task 7 的阻塞项，需要上游提供任务明文。
- **阶段 3 新写的 spec 内容（上游 tier、升档、新日志字段）一行代码都没实现**，本协议不验证它们。
- Codex Cloud 不在范围内。
