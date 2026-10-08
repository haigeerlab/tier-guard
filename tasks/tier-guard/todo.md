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
- [x] Task 18 · 两个适配层的审计记录带上新字段；`reason` 与任务原文不入日志（断言覆盖）
  - 两个适配层原样记录决策、不做过滤；未发现任何现有路径把任务原文或 reason 写进日志
- [x] Checkpoint · Upstream tier（validate + 变异 206 / 0 / 0；D1–D3 已定；2026-10-05 用户批准进入 Task 19）
- [x] Task 19 · 按失败次数升档：L1 失败 → L2，只升不降、不低于 floor，记录 `escalation`
  - floor 也命中时 `escalation.to` 取最终有效档（L3），冲突仍记上游声明档；收回按声明档判定（宁可多收回）；
    L3 失败不做任何事。`reclaim` 只进决策、不改 action / target，deny 留给 Task 20
- [x] Task 20 · L2 二次失败收回主会话（新 deny 路径，D3 已批准）
  - 偏离计划：计划写「缺 `session_id` 不 deny」，那是从预路由提醒照搬的笔误；按 spec D3，收回不依赖 `session_id`，缺了照样 deny
  - 生产影响：Claude 闸门开着，guard 下带 `tier=L2 failures>=2` 的派活会被真实拦下；Codex 闸门关闭，行为不变
- [x] Task 21 · tier-routing skill、README、CHANGELOG、spec 同步（含 Codex hook 读不到标记的限制）
- [x] Task 22 · Claude Code 真实宿主验证标记 / floor / 收回（跑前确认写 `~/.claude`）
  - 五个用例全部符合 spec；收回 deny 生效且未消耗会话标记。证据：[`upstream tier host check`](../../docs/research/2026-10-05-upstream-tier-host-check.md)
  - 顺带发现两件旧事：停止记录 `actual_execution` 偶发为空（疑似 transcript 未落盘）；首次 deny 文案写死「（auto）」
- [x] Checkpoint · Phase 7 complete（spec 中上游档位 / floor / `tier_source` / 升档 / 不漏日志各有通过的断言；变异 241 / 0 / 0；Claude 宿主证据已有，Codex 限制已写明）

## Phase 8 · 让子代理派活真正省钱（与 spec-guard 分工，2026-10-05 用户批准）

> 详见 plan「Phase 8」。整体账实测：sonnet 父代理下派活比不派贵 2.0–2.8 倍（更正计价后），先测清楚何时划算。

- [x] Task 23 · Claude 派活成本对照：opus 父代理 × 主会话上下文 小/大 × 派/不派，各 2 次
  - 两档都是派更贵（更正计价后 +54% / +15%，均约 +$0.21；初版 +63% / +19%）；H1 未被支持：派活时主会话轮次没减少。回本要看 task 能省几轮主会话，小 task 永不划算
- [x] Task 24 · Codex L2 对照：Luna（high / xhigh）vs Sol/medium，10 个 L2 任务
  - Luna/high 10/10，成本约 Sol 的 1/14；可以承担 L2
- [x] Task 25 · 若 Luna 过关：Codex L2 改为 Luna（发版前先问）
  - `codex-luna-high` 同时承担 L1/L2，`codex-sol-medium` 移出目录；L3 仍为 sol/xhigh
- [x] Task 26 · tier-routing 加「所选候选不比你便宜就自己做」
  - 另加「任务小而明确也自己做」，依据 Task 23 实测；与 spec-guard「默认不派」一致
- [x] Task 27 · 与 spec-guard 联调：Claude / Codex × 派 / 不派，成本报告与日志交叉核对
  - 主组 14 次已核对、三方一致：Claude 仅 Task 4（L2→sonnet）派了便宜 23%；R 组 4 次一次没派；Codex 亏在 wait_agent 轮询。
    记录：[`joint cost test`](../../docs/research/2026-10-06-spec-guard-joint-cost-test.md)。口径已与 spec-guard 核清（成本报告不含最后一次勾选后的收尾轮）。补跑：Codex W 组一次长等待后 wait_agent 25–31→5–7 次、与不派持平；Claude S 组新门槛只一半选中 Task 4 且未省钱
- [x] 补跑完整变异测试（2026-10-06，HEAD `a8e3ce0`，负载均值约 8–14）：符合预期 257 / 不符 0 / 锚点失效 0（抓到 252、如期等价 5），
  7 组基线全绿。补上 `439dd3f` 记下的缺口：当时 `test-tier-guard.sh` 基线因高负载下性能断言失败，其 54 个变异体未跑，这次全部抓到

## Phase 9 · 收尾评审修复与文档整理（2026-10-06 用户批准）

> 详见 plan「Phase 9」。评审结论：总体约 3.6 / 5，默认 guard 路径可靠，问题集中在 auto、报告口径与文档。

- [x] Task 28 · 路由修复：auto 不改写 fork / 插件 agent（D1）；只读 + 实现同现归 unknown（D2）；`reason` 里出现 `failures=` 判非法（D3）
  - 新断言先红后绿（Claude 薄壳 4 条、契约 D2/D3）；变异 6 条全抓到，改动打断的 1 条旧锚点已更新
- [x] Task 29 · 报告与模式修复：宿主内部子代理单独计数（R1/R2）；`/tier-doctor` 模式与 hook 一致（D4）；off 一律不记（D7）
  - 新断言先红后绿；变异 6 条全抓到。本机真实日志：派活 474 次、未写 transcript 0%；宿主内部 2906 次单列；守卫兜底 2653 → 0
- [x] Task 30 · 隐私与 tier-label：`description` / `task_name` 只记长度与 sha256；`/tier-label` 标明仅限 v1 记录
  - v1 / v2 写日志处一并改；v1 重派推断改比 sha256（兼容旧记录原文）；新断言先红后绿；变异 4 条全抓到，打断的 tier18 锚点已更新
- [x] Task 31 · 文档整理：README 重写（场景、价值与设计理念、安装、用法、命令、架构、与 spec-guard 配合）；过时注释与说明
  - 另修：四个 hook 头注释（guard 也会 deny）、SKILL.md（auto 只能环境变量临时开、标记字段顺序、Desktop 旧型号标为历史证据）、CHANGELOG Unreleased；安装命令按两边 CLI `--help` 核对
- [x] 出厂默认 mode 由 guard 改为 off（spec-guard 会话提出，2026-10-06 用户确认）：目录、规约、plan 决策表、CLAUDE.md、README、命令、skill、报告文案与依赖默认值的测试同步；off 下 tier-routing skill 照常可用
- [x] Checkpoint · Phase 9（2026-10-06，0.2.7）：validate 通过；最终代码完整变异 274 / 1 / 0，那 1 条是「去掉 off 快速路径」在高负载下被性能计时断言（auto 模式、与该变异无关）误杀，手工单跑 147 / 0 仍存活，等价裁决成立。首轮暴露的「SubagentStop off 判断」因 D7 变为等价，已改标并写明原因

## 待补宿主验收（不改变生产配置）

- [x] Codex CLI 主代理明文预路由：在真实交互式 Terminal/TUI 中复现 Desktop 的三档 child 回执。
  2026-09-13 00:54–00:55 +0800，CLI `0.154.0` 的真实 TUI 父线程保持 `terra/high`，三个
  child 的 SQLite 回执依次为 `luna/medium`、`terra/high`、`terra/xhigh`；三条原生 hook 审计均为
  `opaque_token`、显式 pin、`applied=false`。详见
  [`Task 7 CLI v2 smoke`](../../docs/research/2026-09-12-task7-codex-cli-v2-smoke.md)。

- [x] Claude Code CLI v2：真实 `PreToolUse` audit 与受控 auto 都已验证；明确只读的未 pin child
  实际回执为 `claude-haiku-4-5-20251001`。当时生产默认 audit（0.2.7 起出厂默认 off），Cloud 未外推。详见
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
  v2 记录恒显示「已关联 0 / N」，与表格里已入账的实际执行矛盾。已修复（该记录初写时未发布，后于 0.2.1 发布）：v2 报「已观测实际执行 X / N」，
  v1 分母只数旧记录，不在报告里比较实际档高低；回归先红后绿，变异 2 条被抓到。本机真实日志显示 8 / 30。
  详见 [`v0.2.0 release`](../../docs/research/2026-09-14-v0.2.0-release.md)。

## 上游前置条件（不在本插件内绕过）

- [ ] Codex Multi-Agent V2：在 `PreToolUse` 派发前提供可验证的任务明文，或与实际 child payload
  绑定的可信结构化能力标签；满足后重跑 Task 7。参见 OpenAI Codex
  [#33284](https://github.com/openai/codex/issues/33284)。

## Phase 10 · 中文优先的双语文档修订（2026-10-08，设计已确认）

> 基线 main = origin/main = `3c602f2`；fetch 与完整 validate 通过。详见 plan「Phase 10」。

- [x] Task 32 · 中文 README 完整使用流程
- [x] Task 33 · 中文参考、兼容性、贡献指南及文档导航
- [x] Checkpoint · 中文版本（report）
  - 临时目录验证默认 off、state / doctor、audit/off 持久切换和 auto 拒绝通过；空日志 report 显示 dry-run 的已知限制复现。中文命令与 CLI help、源码核对完成。
- [x] Task 34 · 现行说明同步与历史范围标注
- [x] Task 35 · 五对中英文用户文档与语言切换
- [x] Task 36 · 链接、双语一致性、示例与完整仓库验证
- [x] Checkpoint · 双语文档交付（report）
  - 五对用户文档一致性、46 份 Markdown 的 245 个本地链接 / 锚点、10 个外部链接、临时目录示例、AST 范围核对与完整 validate 均通过。
  - Codex 固定 tag 升级按官方 0.160.0 源码更正；25 份历史正文与基线一致。已知空日志 report 模式问题只作说明。完整证据及未验证项见 plan 本批交付记录。

## Phase 11 · 开发约定审计补齐（2026-10-08，用户已确认）

- [x] Task 37 · 补齐 Codex 项目入口与状态说明
  - 新增 AGENTS.md，引用共用开发规则并声明 Codex 本地流程；plan 明确 todo 是执行状态记录。
    入口引用与唯一成对声明块检查通过，原有 todo 正文和任务状态逐字保持不变。
- [x] Task 38 · 恢复 Spec Guard marketplace 并核验
  - 仅刷新 spec-guard-marketplace，返回 errors=[]；查询确认 0.52.3 installed=true、enabled=true，固定 ref 保持 v0.52.3。
    官方 phase 为 BUILDING；verify-artifacts：3 通过、0 警告、0 失败。文档基线 / 影响 / 交付核验均为 absent，
    历史核验明确报告「未验证：没有 capability history ledger」，不记为通过。
- [x] Task 39 · 仓库回归与本批交付（report）
  - 完整 `/bin/bash scripts/validate.sh` 退出 0；`git diff --check` 通过。
    本批仓库改动仅 AGENTS.md、plan.md、todo.md；未修改运行代码、配置、清单、版本或原有未完成项。
    仅恢复用户已授权的 marketplace 快照；未提交、推送、发布、付费派活、安装 pre-push 或启用可选文档基线。

## Phase 12 · 文档基线与历史快照（2026-10-08，用户已确认）

- [x] Task 40 · 启用文档基线和模块影响
  - 基线和模块影响的官方核验均为 valid，文档声明核验为 ready；五项关注点均沿用现有指导来源。
    target 与 verified 的范围在基线中明确说明，不将声明核验解释为代码或全部宿主验收通过。
- [x] Task 41 · 导入历史能力图快照
  - 官方迁移预览无冲突，import --confirm 成功；实际账本与已确认预览一致，快照内容与能力图逐字一致。
    verify-history 通过；语义审计保留 1 条 timestamp-unverified（at: imported），模块数组为空，历史状态不据此补全。
- [x] Task 42 · 本批验收（report）
  - 完整 `/bin/bash scripts/validate.sh` 退出 0，`git diff --check` 通过；官方产物检查 3 通过、0 警告、0 失败。
    原有 5 个未完成项和运行代码保持不变。本批完成的是文档治理声明及历史快照保存，
    不代表历史全流程已补证或模块已交付；未提交、推送、发布或进行付费派活。

## Phase 13 · 剩余事项核对与历史补正（2026-10-08，用户已确认）

- [x] Task 43 · 保存剩余事项核对证据及原样历史审计报告
  - 审计来源按原字节保存，哈希与已确认 correction 一致；现有样本核对保留原有五项状态。
- [x] Task 44 · 按已审阅 correction 追加 imported → unknown 补正，并核验实际结果
  - 官方 correct --confirm 成功；实际账本与已审阅预测一致，原 initiatives 和快照哈希保持不变。
    validate、verify、verify-history 均通过；audit 为 correctedFindings=1、unresolvedFindings=0，真实历史时间仍未知。
- [x] Task 45 · 完整回归、官方检查、限定范围提交与 origin/main 同步（report）
  - 完整 `/bin/bash scripts/validate.sh` 退出 0，diff 检查通过；官方产物检查 3 通过、0 警告、0 失败，历史核验通过。
    五文件补正提交 `2739548` 已推送，远端 main 读回 `2739548482fc0c2ba46a7ca7f463ae061cbe2def`。
    原有五项状态保持不变；本批交付完成记录在读回远端成功后补记，不代表 Codex 上游阻塞或两项观察已解决。

## Phase 14 · 报告当前模式来源修复（2026-10-08，用户已确认）

- [x] Task 46 · 失败回归与报告模式来源最小修复
  - 原代码命令回归先出现 9 项预期失败；修复后 72 通过、0 失败。当前模式与 auto 提示读取现行配置，v1 门槛标为历史统计。
    隔离目录实测默认 off、持久 audit/guard、旧 dry-run 回退与 state 一致；既有 v1 判定、关联及 v2 回归保持通过。
- [x] Task 47 · 定向变异校验与中英文说明同步
  - 五个 report runtime 变异体全部抓到：符合预期 5、不符 0、锚点失效 0；全仓 280 个锚点唯一命中。
    历史观测回归 34 通过、0 失败；Spec、中英文 compatibility/reference 与 Unreleased 修复说明已同步。
- [x] Task 48 · 完整回归、官方检查与本地 diff 验证（report）
  - 完整 `/bin/bash scripts/validate.sh` 退出 0；官方产物检查 3 通过、0 警告、0 失败，文档 baseline/impact 为 valid，声明核验为 ready。
    diff 检查及正确性、可读性、架构、安全、性能复核通过；原有五个未完成项逐字保留。
    本批仅交付可审阅的本地修复，尚未提交、推送或发布；未新增付费派活，未修改运行配置或宿主闸门。

## Phase 15 · 自定义配置诊断一致性（2026-10-08，方案 A 已确认）

- [x] Task 49 · 失败回归与 doctor/report 显式配置入口
  - 原代码 report 8 项、doctor 10 项预期失败；修复后命令 89 通过、doctor 17 通过，均 0 失败。
    同一自定义 audit 目录的 state 与本地 hook 记录一致；配置/模式覆盖、错误退出、只读及 v1 历史统计通过。
- [x] Task 50 · 定向变异和双语文档同步
  - 配置入口 8 条和参数边界 2 条定向变异全部抓到，不符 0、锚点失效 0；全仓 290 个锚点唯一命中。
    Spec、双语 reference/compatibility 和 Unreleased 已同步；默认命令不自动读取配置环境变量。
- [x] Task 51 · 整仓验证与本地 diff 交付（report）
  - 完整 `/bin/bash scripts/validate.sh` 退出 0；官方产物检查 3 通过、0 警告、0 失败，文档 baseline/impact 为 valid、声明核验为 ready。
    隔离目录中三个诊断工具模式一致，运行前后文件集合和逐文件 SHA-256 完全不变；diff 与代码复核通过。
    原有五项逐字保留；本批 13 文件局部修改，验证阶段未提交或推送，未发布、付费派活或写入宿主配置。
    用户于 2026-10-08 以“继续”授权本批提交并推送至既有 origin/main；提交前已确认远端与本地基线一致。

## Phase 16 · 发布前收口（2026-10-08，用户已确认）

- [x] Task 52 · 完整变异测试与实际结果记录
  - 原校验器按索引分为四个独立副本，73/73/72/72 项覆盖全部 290 个变异，无重复或遗漏。
    284 抓到、6 预期等价、0 不符、0 锚点失效；串行预跑主动结束，不计入完整结果。
    结构化汇总见 docs/research/2026-10-08-release-full-mutation.json。
- [x] Task 53 · 临时插件副本及本地接口冒烟
  - 从已提交基线导出带空格路径的副本；双清单候选 0.2.8、marketplace、路径及 skill 同步通过。
    27 项冒烟通过、0 失败：默认/自定义模式、覆盖和错误退出、清单原始 hook 命令及只读哈希均符合预期。
    仅本地接口核验，真实宿主派活 0；结果见 docs/research/2026-10-08-release-preview-smoke.json。
- [x] Task 54 · 发布清单、更新预览与本地交付（report）
  - 下一版 0.2.8 的 9 文件补丁和临时包已形成；补丁可应用，双语版本标注和固定 tag 核对通过。
    当前双语 README/reference/compatibility 明确已发布 0.2.7 与 Unreleased 行为，纠正旧报告限制说明。
    完整 validate 退出 0；官方产物 3 通过、0 警告、0 失败，baseline/impact valid、声明 ready；本地链接及 diff 检查通过。
    发布说明与更新/回退预览见 docs/research/2026-10-08-v0.2.8-release-preview.md。
    原有五项逐字保留；本批未提交、推送、创建 tag、正式发版、更新宿主或付费派活。

## Phase 17 · v0.2.8 正式交付与本机更新（2026-10-08，用户已确认）

- [x] Task 55 · 版本准备、完整验证与正式 tag 发布
  - 正式补丁后完整 validate 退出 0，官方产物 3 通过、0 警告、0 失败，文档声明 valid/ready；源码和生产目录无改动。
    发布提交 278e08a 已推送；远端 v0.2.8 附注 tag 和解引用提交读回一致，未覆盖既有 tag。
- [x] Task 56 · Claude user scope 插件更新与核验
  - 私有备份后刷新既有 marketplace，CLI 回执 0.2.7 → 0.2.8；user scope、登记提交和安装代码与发布身份一致。
    插件数据哈希与 Claude settings 未变；同期 Spec Guard 元数据变化已记录，归因未确认，未擅自回滚。
- [x] Task 57 · Codex 固定 ref 插件更新与核验
  - 旧来源重新登记为 v0.2.8 并重装，版本 0.2.8、installed/enabled 均 true，安装代码与 tag 一致。
    Codex config 仅 tier-guard marketplace 区块变化，其他设置、hook 信任记录及原数据哈希未变。
- [x] Task 58 · 实际交付记录、提交与远端同步（report）
  - 两边实际安装根共 20 项只读校验通过，每宿主 24 文件字节与发布提交一致；mode 均 off。
    正式交付结果见 docs/research/2026-10-08-v0.2.8-delivery.md/json；记录随后提交/推送，不移动发布 tag。
    原有五项逐字保留，无付费派活或信任代签；当前会话需刷新，安装核验不代替真实 child 验收。
  - 后续用户截图核对（2026-10-08）：Codex CLI 的 tier-guard `PreToolUse` 项为 `[x]`、`Trusted`，
    启用与信任界面核对完成；完整路径被截断，不据此认定版本或真实派活执行，原有五项仍未完成。
