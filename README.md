# tier-guard

Claude Code 与 Codex 的插件：主代理**新建子代理**时，按这次任务选一个**够用的最便宜模型**
（Codex 还包括 `reasoning_effort`），而不是让子代理默认继承主代理那个最贵的模型。

它不创建任务、不切换主代理的模型，也不替上游工作流决定怎么拆任务、验收标准是什么。

## 解决什么问题

主代理（比如跑在 opus 上的主会话）派子代理去干活时，如果不写明模型，子代理会**继承主代理的模型**。
于是"列一下这个目录的文件""把这个函数改个名"这种活，也按最贵的价格在跑。

tier-guard 在子代理创建前插一道关：

- 机械、只读的活 → 最便宜的档（Claude `haiku`，Codex `gpt-6-luna/high`）
- 有明确验收的受限实现 → 中档（Claude `sonnet`，Codex `gpt-6-luna/high`）
- 跨模块取舍、歧义、不可逆的活 → 最高档（Claude `opus`，Codex `gpt-6.1-sol/xhigh`）

宿主自己派的子代理（例如 Claude Code 内置的 Explore）也一样被管到。

## 先说清楚：派子代理大多不省钱

这是本仓自己实测出来的结论（[派活值不值得开](docs/research/2026-10-06-dispatch-verdict.md)）：

- 小任务派出去比主会话自己做**贵 15%～54%**；派活后主会话的轮次并没有减少。
- 唯一一次省钱（L2 任务交给 sonnet，便宜 23%）复跑不稳定；Codex 配合"一次长等待"也只是与不派**持平**。
- 省钱只来自"少跑的主会话轮次"：每次子代理交回，主会话都要把整个上下文再读一遍。

所以 tier-guard 的定位是：**不鼓励多派；真派了，别默认继承最贵的模型。**
你出于上下文隔离或其他原因决定派活时，它保证子代理用的是合格的最便宜模型。
如果你平时根本不派子代理，可以直接 `/tier-mode off`。

## 设计理念

- **只管新建的子代理，主代理绝不换模型。** 路由只在创建子代理前跑一次，运行中不切换。
- **你写明的就是你的。** 派活时显式给了 `model` 或 `reasoning_effort` 就是 pin，永不改写，只记录建议方向。
- **信息不足就选高档。** 不可逆、取舍、跨模块、验收不清的任务有一条下限（floor），任何信号都压不下去。
  省一点 token 不值得拿质量去换。
- **守卫坏了不能变成干活坏了。** 任何异常都放行（退出 0、不输出），并在日志里写明走的是哪条路径。
- **日志不记任务原文。** prompt、派活描述、Codex 任务名都只记长度和 SHA-256，因为里面可能有密钥。
- **只在实测过的宿主上改写参数。** 能不能改写由候选目录里的宿主能力闸门决定，环境变量绕不过去；
  没有真实端到端证据的宿主只给建议。
- **判断逻辑只有一份。** 两个宿主的薄壳和报告都调用同一个 `route_decide.py`，不各写一套。

## 安装

**Claude Code**

```bash
claude plugin marketplace add haigeerlab/tier-guard
```

```bash
claude plugin install tier-guard@tier-guard
```

装好后重启会话生效。以后升级用 `claude plugin marketplace update tier-guard`，再
`claude plugin update tier-guard@tier-guard`。

**Codex CLI**

```bash
codex plugin marketplace add haigeerlab/tier-guard --ref v0.2.6
```

```bash
codex plugin add tier-guard@tier-guard
```

Codex 按 `--ref` 固定版本，升级时换成新的 tag 重新添加。第一次使用时在 Codex CLI 里用 `/hooks`
审核并信任 tier-guard 的 hook。

## 怎么用

装上就生效，不需要额外操作。

**四种模式**

| 模式 | 行为 |
|---|---|
| `off` | 完全不工作：不判断、不记录、不改写。 |
| `audit` | 只记录建议；没写明模型的派活会收到一条提醒，不拦截。 |
| `guard`（默认） | 和 audit 一样不改参数；每个会话**第一次**没写明模型的派活会被拦一次，附上候选目录，主代理写明模型后重派，之后只提醒。 |
| `auto` | 在 guard 之上，对没写明模型的派活直接改写参数。只在 Claude Code 上可用，且 `/tier-mode` 拒绝持久开启，只能用环境变量 `TIER_GUARD_MODE=auto` 临时打开。 |

guard 的代价要知道：每个会话第一次派活被拦，主代理要重派，相当于多一轮主会话。不派活的人用 `off`，
嫌拦烦的人用 `audit`。

**命令与 skill**

| 名称 | 作用 |
|---|---|
| `/tier-mode [off\|audit\|guard]` | 查看或切换模式。不带参数时显示当前模式和它的来源。 |
| `/tier-report` | 路由摘要：请求了什么、选了什么、实际跑在哪个模型上、拦截与提醒次数、子代理按模型的 token 用量。 |
| `/tier-doctor` | 只读诊断：数据目录、日志、Codex hook 能观察到什么。 |
| `/tier-label <id> <判定>` | 仅限 v1 历史记录的人工标注（误报 / 打回）。默认的 v2 路由用不到。 |
| skill `tier-routing` | 主代理创建子代理前自动触发：按候选目录选模型并写明，告诉主代理什么时候干脆自己做。 |

日志在插件数据目录里：Claude Code 是 `~/.claude/plugins/data/tier-guard-tier-guard/`，
Codex 是 `~/.codex/plugins/data/tier-guard-tier-guard/`，主文件是 `decisions.jsonl`。

**想算钱？** tier-guard 只回答"派给了谁、实际跑的是什么模型"，不换算金额（价格会变，写进插件就是埋一个会过期的事实）。
按任务统计主会话加子代理的总花费，用 [spec-guard](https://github.com/haigeerlab/spec-guard-plugin) 的
`/cost-report <模块> --prices <价格文件>`，它同时读 Claude 和 Codex 的会话记录。

## 架构

```
主代理准备派子代理
   │
   ├─ skill  tier-routing ......... 主代理侧：派活前按候选目录选模型并写明；读上游档位标记
   │
   ├─ hook（宿主在派活前调用）
   │    Claude Code  PreToolUse(Agent)        路由 / 提醒 / 拦截 / 收回 / （auto）改写
   │                 PreToolUse(Bash)         v1 遗留：记录 `codex exec` 派活；默认 v2 下直接放行
   │                 SubagentStop             记录实际执行模型与 token 用量
   │    Codex        PreToolUse(spawn_agent)  只能记录和建议（拿到的任务是看不出内容的令牌）
   │
   ├─ 判断核心  hooks/route_decide.py ........ 全部判断规则；薄壳和报告都只调它
   ├─ 候选目录  config/routing.catalog.v2.json  各宿主的候选模型、能力、成本排序、宿主能力闸门
   └─ 数据      decisions.jsonl（不存原文）、模式文件、每会话拦截标记
```

一次派活的判断顺序是 **pin > floor > 上游档位 > 文本推断**：

1. 写明了模型 → pin，不改写；
2. 任务带不可逆、歧义、跨模块或取舍信号 → 不低于最高档（floor）；
3. 任务里有合法的上游档位标记 → 按它选档；
4. 否则按任务文本推断，推断不出就保守选高档。

## 与 spec-guard 配合：上游档位标记

上游工具（或你自己）可以在任务文本里为一次派活声明档位，**独占一行**：

```
<!-- tier-guard: tier=L2 failures=1 reason=按 spec 第 3 节实现，验收明确 -->
```

| 字段 | 含义 |
|---|---|
| `tier` | 必填，`L1` / `L2` / `L3`（大小写敏感）。L1 机械只读，L2 有明确验收的受限实现，L3 跨模块取舍、歧义或不可逆 |
| `failures` | 可选，非负整数：同一任务此前连续失败的次数，由派活方当场填写 |
| `reason` | 可选，写在最后，只给人读，不参与判断，日志只记是否存在和 SHA-256 |

规则：

- 整段任务里恰好出现一次；没有、重复、不独占一行、取值非法，都按"没有标记"处理，核心不会因此失败。
  字段按 `tier`、`failures`、`reason` 的顺序写，`reason` 里出现 `failures=N` 会让整个标记失效。
- 标记不能压过 floor：任务文本能伪造标记，一段写着 `tier=L1` 的不可逆任务仍然走最高档，日志记下这次冲突。
- **升档**：`tier=L1` 且 `failures>=1` → 按 L2 选档。
- **收回**：`tier=L2` 且 `failures>=2` → 不再派活，要求主代理自己处理或重新界定任务。
  Claude Code 上 guard / auto 直接拦下，audit 只提醒；pin 的派活和 off 不管。
- Codex 的 hook 读不到任务文本，标记在 Codex 上只靠 `tier-routing` 让主代理自己读、自己遵守。

## 宿主支持现状

| | Claude Code CLI | Codex CLI / Desktop |
|---|---|---|
| hook 能看到任务文本 | ✅ | ❌ 只拿到看不出内容的令牌 |
| 首次派活拦截 / 提醒 | ✅ 已开启 | 关闭 |
| 自动改写参数（auto） | ✅ 已实测（未写明模型的只读子任务实际跑在 haiku） | ❌ 只能建议 |
| 主代理按 skill 自己选模型 | ✅ | ✅ 已实测三档派发 |
| 实际执行模型与用量 | ✅ SubagentStop 回读 | 只记派活参数 |

Codex 要等上游在派活前给 hook 可验证的任务明文，或与实际子代理绑定的可信结构化标签，hook 才能独立选模型。
背景见 OpenAI Codex [#33284](https://github.com/openai/codex/issues/33284)，进度记在 [待办](tasks/tier-guard/todo.md)。
Claude Code Cloud 会话未验证。

## 文档

- [规约](spec/tier-guard.md)：完整行为定义
- [计划与已定决策](tasks/tier-guard/plan.md)、[待办](tasks/tier-guard/todo.md)
- [实测证据](docs/research/)：每条结论都带可核对的出处
- [变更记录](CHANGELOG.md)

## 开发

```bash
/bin/bash scripts/validate.sh
```

覆盖路由契约、Claude / Codex 薄壳、模式与报告、观测、插件结构和校验器自身。变异测试（慢，不进 validate）：

```bash
python3 scripts/mutation-check.py
```

真实 Codex CLI 的三档预路由验收脚本（在 Terminal 里跑，会建隔离目录并保留审计日志与线程回执）：

```bash
/bin/bash scripts/codex-cli-preroute-smoke.sh
```

开发约束（bash 3.2、不依赖 jq、不用 `sed -i` 等）见 [CLAUDE.md](CLAUDE.md)。

## License

Licensed under the [Apache License 2.0](LICENSE).
