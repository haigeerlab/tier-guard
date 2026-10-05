# Todo: tier-guard v2

> 本列表取代 v1 下限守卫的未完成项；v1 产物保留在工作区作证据，但不代表符合 v2 需求。

- [x] Task 1 · 路由契约与模型目录
- [x] Task 2 · 动态分类与最低合格候选选择
- [x] Checkpoint · Core policy review
- [x] Task 3 · Claude pre-dispatch adapter
- [x] Task 4 · Codex CLI pre-dispatch adapter
- [x] Checkpoint · Adapter review
- [x] Task 5 · 可选上游上下文与语义 provider 接口
- [x] Task 6 · 审计、报告与模式迁移
- [x] Checkpoint · Local full validation
- [ ] Task 7 · Codex CLI hook 独立的真实低成本子代理验证（阻塞：hook 输入为 `opaque_token`）
- [x] Task 8 · 宿主兼容性与 Desktop 升级条件
- [ ] Checkpoint · v2 review（独立核心审查已完成；阻塞：Task 7 仍等待上游提供任务明文或可信结构化信号。）

- [x] Task 9 · 提醒判据契约、`dispatch_nudge` 宿主闸门与 tier-routing 触发描述
- [x] Task 10 · Claude adapter 提醒（audit 注入提醒 / auto 每会话 deny 一次）
- [x] Task 11 · Codex adapter 提醒（遵守 Codex 0.154.0 输出约束）
  - [x] 真实宿主缺陷：Codex 原生 `spawn_agent` 每次都带 `fork_turns`（`"all"` / `"none"`），被 `_codex_nudge_pin`
    当成「判不出 pin」，提醒与 deny 在真实 Codex 上永不触发。已按 rust-v0.154.0 源码确认 `fork_turns` 与 pin 无关并修复
    （单测先红后绿、变异体抓到、validate 通过）。证据：[`dispatch nudge e2e`](../../docs/research/2026-09-13-dispatch-nudge-e2e.md)
  - [x] 修复后在真实 Codex CLI 上复测提醒 / deny：宿主采纳提醒上下文与 deny + 原因，主代理带显式参数重派
  - [x] 风险：deny 后主代理不加载 skill 时自行降档（复测中三个 child 均为不在目录里的 `luna/low`，含取舍类任务）。
    2026-09-13 用户确认并实现：提醒 / deny 文本附上本宿主候选目录摘要与「信息不足、取舍、跨模块或不可逆选高档」
    （`route_decide.catalog_summary`；单测先红后绿，变异 25 条符合预期）。
    真实宿主复测（2026-09-13 17:51 起，提交 `56de0e1`）：Claude auto 被拦后不加载 skill 也按目录传 haiku / sonnet / opus（通过）；
    Codex auto 改为目录内的 `luna/medium`，但取舍类任务仍被分到最低档（未达标）。
  - [x] 区分 Codex 取舍类降档的原因：对照测试（child 真正做取舍分析，auto + 禁止 skill，每宿主 2 轮）中取舍类任务 4/4 次拿到高能力档
    （Claude opus ×2、Codex `terra/xhigh` ×2）；此前的降档来自「child 只回复固定文本」的测试设计，不需要加强文本约束。
    证据：[`dispatch nudge e2e`](../../docs/research/2026-09-13-dispatch-nudge-e2e.md)
  - [ ] 观察：受限实现任务会选低一档——对照测试 Codex 2/2；Task 12 评估 Codex 2/4、Claude 1/4。不违反取舍类门槛；
    2026-09-13 用户确认暂不处理，继续积累数据
  - [ ] 观察：Codex 取舍类任务被主代理显式选到低档——Task 15 guard 复评 12 次中 1 次（会话 3 分到 `luna/medium`）；
    显式参数是 pin，hook 不干预，要改善只能作用于 skill 文本或候选目录描述。2026-09-14 用户确认暂不处理。
    重新评估条件（与上一条共用）：真实使用中再出现取舍类被降档，或实现类样本每宿主 ≥10 次；届时先出方案再改。
    证据：[`dispatch nudge e2e`](../../docs/research/2026-09-13-dispatch-nudge-e2e.md)
  - [x] Claude audit 提醒在真实宿主送达但未被采纳（1 轮、提醒后 2 次派活）。2026-09-13 用户确认：不改 audit 语义，
    留到 Task 12 用每宿主 ≥10 次自然派活的数据再决定。2026-09-14 关闭：Task 12 由 guard 取代，audit 语义未改；
    默认 guard 下 Claude 显式传参 12/12（Task 15），安装版 `0.2.0` 两轮验收拦截后 8/8 显式传参。
- [x] Task 12 · 报告与自然触发真实宿主评估（每宿主 ≥10 次，开闸门前再确认）——audit 下未达标，由 Task 13–15 的 guard 取代并关闭
  - [x] `/tier-report` 新增「主代理预路由提醒」统计：提醒 / 拦截 / 未触发次数、提醒后同会话显式传参比例、pin 被打扰次数
  - [x] 真实宿主评估（2026-09-13，每宿主 4 会话 12 次派活）：Claude 显式传参 8/10、取舍类 2/4（audit 未达标）、pin 0；
    Codex 自然预路由 12/12（提醒指标无样本）、取舍类 4/4、pin 0。证据：[`dispatch nudge e2e`](../../docs/research/2026-09-13-dispatch-nudge-e2e.md)
  - [x] 开闸门决定：按规约 Claude 在 audit 下不满足。2026-09-13 用户确认新增默认 `guard` profile，改由 Task 15
    在 guard 下复评后决定（结果见 Task 15）
- [x] Task 13 · guard profile：核心判据、状态持久化与默认目录
- [x] Task 14 · guard 在两个适配层、报告与命令 / skill / README / CLAUDE.md 文案中落地
- [x] Task 15 · guard 下真实宿主复评并决定是否开闸门（开闸门前再确认）
  - [x] guard 复评（2026-09-13，提交 `39108b5`，每宿主 4 会话）：Claude 显式传参 12/12、取舍类 4/4、pin 0（达标）；
    Codex 主代理 12/12 自行显式传参（拦截 / 提醒未触发）、取舍类 3/4（主代理显式选错档，未达标）、pin 0。
    证据：[`dispatch nudge e2e`](../../docs/research/2026-09-13-dispatch-nudge-e2e.md)
  - [x] 开闸门决定：2026-09-13 用户确认只开 `claude-code.dispatch_nudge`；Codex 取舍类未达标且问题在主代理自身选档，保持关闭

## Phase 7 · 上游档位、升档与档位日志（2026-10-05 拆分，用户已批准）

> 详见 plan「Phase 7」。D1–D3 已于 2026-10-05 按提案确认并写入 spec。

- [x] 已确认 D1 · v2 失败次数的传输方式（提案：同一标记行加 `failures=N`）——阻塞 Task 19
- [x] 已确认 D2 · 上游档位能否低于「信号全未知」的保守档（提案：能；只有不可逆 / 歧义 / 取舍 floor 不可破）——阻塞 Task 17
- [x] 已确认 D3 · L2 二次失败收回的 deny：guard / auto 拦、audit 提醒、pin 不拦、受 `dispatch_nudge` 闸门约束——阻塞 Task 20
- [x] Task 16 · 解析上游档位标记（任务文本 + 信封 v2），记录 `tier_source` upstream / inferred
  - 过渡规则：上游档位暂时只许抬高、不许压低，Task 17 换成 floor 优先级。标记非法而信封合法时整体按 unavailable（保守）；
    pin 请求暂时也可能显示 `tier_source: upstream`，由 Task 17 的 `pin` 来源接管。变异体 21 条全部抓到
- [x] Task 17 · 优先级 pin > floor > tier > 推断，`tier_conflict`，伪造低档撤销不了 floor（正反断言）
  - floor = 危险信号命中且推断落在 L3。只读 + 小范围 + 机械的任务即便显式标「验收缺失」也仍走 L1（沿用既有只读豁免）：
    若算作 floor，带 `tier=L1` 反而会被抬到 L3，比不带标记还贵。该边角有断言和变异体守着，未改既有路由
- [ ] Task 18 · 两个适配层的审计记录带上新字段；`reason` 与任务原文不入日志（断言覆盖）
- [ ] Checkpoint · Upstream tier（validate + 变异 0 存活；D1 / D3 在此之前定下）
- [ ] Task 19 · 按失败次数升档：L1 失败 → L2，只升不降、不低于 floor，记录 `escalation`
- [ ] Task 20 · L2 二次失败收回主会话（新 deny 路径，D3 已批准）
- [ ] Task 21 · tier-routing skill、README、CHANGELOG、spec 同步（含 Codex hook 读不到标记的限制）
- [ ] Task 22 · Claude Code 真实宿主验证标记 / floor / 收回（跑前确认写 `~/.claude`）
- [ ] Checkpoint · Phase 7 complete

## 待补宿主验收（不改变生产配置）

- [x] Codex CLI 主代理明文预路由：在真实交互式 Terminal/TUI 中复现 Desktop 的三档 child 回执。
  2026-09-13 00:54–00:55 +0800，CLI `0.154.0` 的真实 TUI 父线程保持 `terra/high`，三个
  child 的 SQLite 回执依次为 `luna/medium`、`terra/high`、`terra/xhigh`；三条原生 hook 审计均为
  `opaque_token`、显式 pin、`applied=false`。详见
  [`Task 7 CLI v2 smoke`](../../docs/research/2026-09-12-task7-codex-cli-v2-smoke.md)。

- [x] Claude Code CLI v2：真实 `PreToolUse` audit 与受控 auto 都已验证；明确只读的未 pin child
  实际回执为 `claude-haiku-4-5-20251001`。生产仍默认 audit，Cloud 未外推。详见
  [`Claude CLI v2 smoke`](../../docs/research/2026-09-13-claude-cli-v2-smoke.md)。

- [x] Claude Code CLI v2 完整端到端验收（A/B/C/D，报告自动记录实际执行）。2026-09-13 首轮未通过：
  v2 跳过 `SubagentStop`，且当轮 mode 实为 audit。工作树修复后以 `--plugin-dir` 复测：点名 tier-routing 的
  主代理预路由三档实际为 haiku / sonnet / opus，报告实际执行三条全部入账。详见
  [`Claude CLI v2 e2e`](../../docs/research/2026-09-13-claude-cli-v2-e2e.md)。
- [x] 自然触发：不点名 tier-routing 时主代理自行选择子代理模型。2026-09-13 Claude CLI 与 Codex CLI 均未通过——
  主代理都没有加载 skill，三个子代理全部继承父代理参数。详见同一文档。
  2026-09-14 以已安装的 `0.2.0`（默认 guard，无 `--plugin-dir`、无 `TIER_GUARD_MODE`）在 Claude CLI 复测两轮 A/B/C/D，上一项一并通过：
  主代理未加载 skill，第一次未 pin 派活被拦截后按目录显式传 haiku / sonnet / opus，D 的 pin 未被打扰，实际执行 8/8 与请求一致并入账报告。
  Codex 闸门仍关闭，Codex 自然触发以 Task 15（主代理 12/12 自行显式传参）为准。详见
  [`v0.2.0 release`](../../docs/research/2026-09-14-v0.2.0-release.md)。

- [x] 观察（2026-09-14 安装版验收发现）：`/tier-report`「建议档 vs 实际执行档（SubagentStop）」只按 v1 字段关联，
  v2 记录恒显示「已关联 0 / N」，与表格里已入账的实际执行矛盾。已修复（未发布）：v2 报「已观测实际执行 X / N」，
  v1 分母只数旧记录，不在报告里比较实际档高低；回归先红后绿，变异 2 条被抓到。本机真实日志显示 8 / 30。
  详见 [`v0.2.0 release`](../../docs/research/2026-09-14-v0.2.0-release.md)。

## 上游前置条件（不在本插件内绕过）

- [ ] Codex Multi-Agent V2：在 `PreToolUse` 派发前提供可验证的任务明文，或与实际 child payload
  绑定的可信结构化能力标签；满足后重跑 Task 7。参见 OpenAI Codex
  [#33284](https://github.com/openai/codex/issues/33284)。
