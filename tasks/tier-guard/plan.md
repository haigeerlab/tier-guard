# Implementation Plan: tier-guard v2 — 动态子代理模型路由

> 基于 [`spec/tier-guard.md`](../../spec/tier-guard.md) 的需求草案。
> 本计划由用户在 2026-09-12 确认进入计划阶段后建立；本仓处于 spec-guard local 模式，
> 不进入远端 tracker。

## Prior implementation status

工作区已有 v1 实现与测试，验证的是“默认 T2、只升不降”的下限守卫。它们保留作宿主事件和
hook 编码的证据，但**不构成 v2 的完成项**。本计划完成前，不将现有 `Task 4b` 或任何既有
冒烟结果表述为动态路由已经交付。

## Architecture decisions

- 主代理不换 model 或 effort；路由只发生在子代理创建前。
- core 接受标准化 `RouteRequest`，独立选择目标候选，不以请求模型作为路由起点。
- 显式 pin 默认不改写；未 pin 的目标可能高于、低于或等于请求参数。
- 模型目录只存能力、可用性与成本事实；策略根据本次任务动态选择最低合格候选。
- agent-skills 是可选、显式的上下文 provider；spec-guard 仅是本仓开发流程，不是运行时依赖。
- semantic provider 先只定义受约束接口和“未配置”行为；不在本计划中联网、取凭据或发送任务原文。
- hook adapter 必须在真实派发前改写参数才能启用 auto；Codex Desktop 已验证主代理明文预路由的三档实际派发，但 hook 因接收不透明令牌仍保持 advisory。
- 2026-09-13 用户确认：自然使用时主代理不会自发加载 tier-routing，因此由派活事件驱动主代理显式预路由——audit 注入提醒（改变“audit 下 stdout 为空”的旧契约）、auto 每个会话 deny 一次；hook 仍不做语义判断。
- 提醒与 deny 受 `host_capabilities.<host>.dispatch_nudge` 实测闸门控制，默认全部 `false`；判定逻辑只放在 `hooks/route_decide.py`。
- 2026-10-05 用户确认 Phase 7 的 D1–D3：失败次数随标记行 `failures=N` 传入；合法上游 tier 可低于「信息不足」保守档，但撤销不了不可逆 / 歧义 / 取舍 floor；L2 二次失败收回 deny 仅 guard / auto、pin 不拦、受 `dispatch_nudge` 闸门、不限每会话一次。
- 2026-10-05 用户确认 Phase 8：先测派活成本（opus 父代理 × 上下文大小）；若 Codex L2 改用 Luna，可放开「升档只许动 effort，不许换 slug」；「不省钱就别派」先只做在 tier-routing skill 里。
- 2026-09-13 Task 12 评估后用户确认：新增 `guard` profile 并设为默认（推翻「默认 audit」）。guard = 每会话第一次未 pin 派活 deny 一次、之后提醒，**从不改写参数**；audit 退回只记录 + 提醒；auto = guard + 参数改写。guard 不改参数，可由 `/tier-mode` 直接持久化，不需要 auto 的质量门槛。
- 2026-10-06 用户确认：出厂默认 profile 由 `guard` 改为 `off`（推翻上一条的「设为默认」，guard 行为不变）。依据是派活大多不省钱（dispatch verdict）；guard 下宿主自己派的 Explore 等子代理也会触发每会话一次拦截，不派活的用户白付一轮主会话。off 下 tier-routing skill 照常可用，只是 hook 不拦截、不提醒、不记录。

## Dependency graph

```text
RouteRequest + model catalog
          ↓
pure route decision + contract tests
          ├─────────────┬─────────────┐
          ↓             ↓             ↓
  Claude adapter   Codex CLI adapter   optional context/provider interface
          └─────────────┴─────────────┘
                        ↓
              audit/report migration
                        ↓
         real-host verification and documentation
```

## Task list

### Phase 1: Contract and pure routing core

#### Task 1: Define route request, decision, catalog, and pin contracts

**Description:** Replace v1 tier/start/floor configuration with a versioned model catalog and a normalized route contract. Keep all task text in memory unless a host explicitly chooses audit hashing.

**Acceptance criteria:**

- [x] Config represents eligible candidates, capability facts, costs and host availability independently from task classification.
- [x] `RouteRequest` and `RouteDecision` schemas cover pin, evidence source, confidence, fallback and host capability.
- [x] No configuration invariant encodes “only raise”, “T1/T2 same slug”, or a blanket ban that is not user policy.

**Verification:**

- [x] Focused config/schema tests reject invalid catalog entries and accept an eligible low-cost candidate.
- [x] Existing v1 config is either migrated explicitly or rejected with an actionable migration error.

**Dependencies:** None.
**Files likely touched:** `config/routing.default.json`, `hooks/route_decide.py`, `spec/tier-guard.md`.
**Estimated scope:** M.

#### Task 2: Implement deterministic dynamic classification and selection

**Description:** Make the pure core classify task signals independently, filter candidates by hard constraints, then select the least-cost qualifying candidate. Add conservative behavior for absent task text, unknown signals, and low confidence.

**Acceptance criteria:**

- [x] Equivalent task input and catalog version produce the same decision and explanation.
- [x] A clear low-risk task can choose a lower-cost candidate even when request parameters were higher.
- [x] A complex, ambiguous, external or irreversible task cannot choose a candidate below its computed requirement.
- [x] Pin returns an advisory decision without a parameter rewrite target.

**Verification:**

- [x] New positive, negative and unknown-input cases run through the pure core self-test or dedicated test file.
- [x] Mutation checks cover accidental reintroduction of start-tier or only-raise behavior.

**Dependencies:** Task 1.
**Files likely touched:** `hooks/route_decide.py`, `hooks/test-tier-guard.sh`, `scripts/mutation-check.py`.
**Estimated scope:** M.

### Checkpoint: Core policy review

- [x] Contract and all deterministic route cases pass locally.
- [x] Human review confirms low-cost selection, pin semantics and conservative unknown handling before adapters change.

### Phase 2: Host adapters

#### Task 3: Adapt Claude pre-dispatch behavior

**Description:** Translate a v2 decision into Claude’s hook payload without changing non-routing parameters. Preserve explicit pin, audit mode and fail-open behavior.

**Acceptance criteria:**

- [x] `audit` writes the decision but never rewrites `model`.
- [x] `auto` rewrites an unpinned Agent call to the selected target, including a lower-cost target when eligible.
- [x] A pinned request, malformed payload or unavailable catalog never changes the call.

**Verification:**

- [x] `hooks/test-tier-guard.sh` covers lower, equal, higher, pinned and fallback decisions.
- [x] Full validation remains green after this task.

**Dependencies:** Task 2.
**Files likely touched:** `hooks/claude_hook.py`, `hooks/test-tier-guard.sh`, `hooks/tier-guard.sh`.
**Estimated scope:** M.

#### Task 4: Adapt Codex CLI pre-dispatch behavior

**Description:** Apply a v2 decision to native Codex CLI `spawn_agent` parameters while preserving Codex’s `permissionDecision: allow` encoding and its host capability limits.

**Acceptance criteria:**

- [x] An eligible unpinned simple task can change both slug and effort to the selected low-cost candidate.
- [x] A complex task can select a higher candidate when the catalog permits it.
- [x] Pin, malformed input and unsupported host capability remain non-mutating with an explicit audit state; inherited child settings are unpinned and can be selected dynamically.

**Verification:**

- [x] Pure-route contract covers lower/equal/higher decisions; `hooks/test-tier-guard-codex.sh` covers host selection, pin and unknown input.
- [x] A fixture proves `updatedInput` retains every non-routing spawn argument.

**Dependencies:** Task 2.
**Files likely touched:** `hooks/codex_hook.py`, `hooks/test-tier-guard-codex.sh`, `hooks/codex-hooks.json`.
**Estimated scope:** M.

### Checkpoint: Adapter review

- [x] Claude and Codex thin-shell suites pass.
- [x] Both adapters consume the same pure decision and differ only in host encoding.
- [x] Desktop remains explicitly marked advisory; no desktop auto claim is added.

### Phase 3: Optional context and observability

#### Task 5: Add versioned optional-context and semantic-provider interfaces

**Description:** Define a strict agent-skills context envelope and a semantic-provider abstraction. Implement only the no-provider path; do not send task text externally or add credentials.

**Acceptance criteria:**

- [x] Context from an unknown source/version is ignored safely and recorded as unavailable.
- [x] Valid agent-skills metadata can improve a decision without being required for core routing.
- [x] No source code reads `.agent/state.json` or invokes spec-guard.
- [x] Provider absence produces a deterministic conservative outcome.

**Verification:**

- [x] Tests cover absent, malformed and valid optional context.
- [x] Repository search demonstrates no runtime references to spec-guard state or commands.

**Dependencies:** Task 2.
**Files likely touched:** `hooks/route_decide.py`, `config/routing.default.json`, `skills/tier-routing/SKILL.md`.
**Estimated scope:** M.

#### Task 6: Migrate audit, reporting and mode controls

**Description:** Replace v1 “raise/floor violation” reporting with v2 decision/actual/quality fields. Keep privacy-safe task fingerprints and distinguish advisory from applied decisions.

**Acceptance criteria:**

- [x] Reports separate selected, requested and actual model/effort.
- [x] Reports never infer token cost when a host did not provide it.
- [x] `off`, `audit`, `auto`, pin and unsupported-host behavior are visible in output.

**Verification:**

- [x] Command and observability suites cover migrated records plus a backward-compatible v1 record if retained.
- [x] Reports remain resilient to malformed or partial logs.

**Dependencies:** Tasks 3–5.
**Files likely touched:** `hooks/tier_report.py`, `hooks/tier_state.py`, `hooks/test-tier-commands.sh`, `hooks/test-tier-observe.sh`.
**Estimated scope:** M.

### Checkpoint: Local full validation

- [x] `/bin/bash scripts/validate.sh` passes.
- [x] `python3 scripts/mutation-check.py` passes.
- [x] Documentation and skill text do not retain “default T2” or “only raise” as product policy.

### Phase 4: Real-host evidence and release readiness

#### Task 7: Prove Codex CLI lower-cost child execution

**Description:** Run an isolated interactive Codex CLI case that asks for a simple unpinned child task, then compare decision log, hook output and child’s actual model/effort.

**Acceptance criteria:**

- [ ] The child actually starts with the selected lower-cost candidate, not merely a suggested value.
- [ ] Evidence records host version, working directory, start/end time, task fingerprint and actual parameters.
- [ ] Failure to observe pre-dispatch application leaves CLI auto status unverified rather than passing by assertion.

**Verification:**

- [ ] Reproducible smoke command or documented manual protocol passes.
- [ ] Result is recorded in a research document without raw sensitive task text.

**Dependencies:** Tasks 4 and 6.
**Files likely touched:** `docs/research/`, `evals/` or `hooks/test-tier-guard-codex.sh`.
**Estimated scope:** S.

**2026-09-12 evidence:** [`Task 7 CLI v2 smoke`](../../docs/research/2026-09-12-task7-codex-cli-v2-smoke.md)
now proves a real CLI 0.154.0 `updatedInput` receipt (`terra/high` parent → `terra/xhigh` child),
while the low-cost-candidate acceptance remains intentionally unchecked.

**2026-09-13 status:** 原生 CLI 的 hook 边界把子任务替换为 `opaque_token`，因此 hook 不可安全地按
任务语义选择 Luna；即使 CLI 已证实接受 `updatedInput`，本项“hook 独立低成本实际执行”仍被该宿主输入
边界阻断，不能以猜测升/降档来满足验收。与此分开的可用路径是主代理在明文阶段使用同一能力目录预路由；
Codex Desktop 与 CLI 都已实际回执 `luna/medium`、`terra/high`、`terra/xhigh` 三档，详见
[`v2 compatibility status`](../../docs/research/2026-09-12-v2-compatibility-status.md)。这不改变本项的
未完成状态，也不授权开启生产 `auto`。

#### Task 8: Publish compatibility status and desktop escalation evidence

**Description:** Align docs, diagnostics and release criteria with actual host evidence. Preserve the advisory boundary and define the evidence needed to upgrade a host from audit to automatic.

**Acceptance criteria:**

- [x] CLI, Desktop and Cloud are each labeled with independently supported capability status.
- [x] No document claims Desktop automatic routing while the V2 pre-dispatch gap remains.
- [x] Doctor output directs users to evidence, not self-reported plugin state.

**Verification:**

- [x] Documentation checks and focused doctor tests pass.
- [x] A reviewer can trace each host claim to a reproducible evidence file.

**2026-09-13 status:** the [v2 compatibility table](../../docs/research/2026-09-12-v2-compatibility-status.md)
labels every host independently. Claude Code CLI `2.1.269` now has a real low-cost Haiku receipt and may
open its host capability gate while staying default-audit; Codex Task 7's independent low-cost hook receipt
remains open because its V2 input is opaque. This task preserves that distinction rather than converting it
into a broad routing claim.

**Dependencies:** Tasks 6 and 7.
**Files likely touched:** `commands/tier_doctor.md`, `hooks/tier_doctor.py`, `docs/research/`, `skills/tier-routing/SKILL.md`.
**Estimated scope:** M.

### Phase 5: Main-agent pre-routing nudge

#### Task 9: Nudge contract, catalog gate and skill trigger

**Description:** Add the pure nudge decision (`none` / `remind` / `deny`) and the `dispatch_nudge` host gate, and rewrite the tier-routing skill description so it names every subagent creation as its trigger.

**Acceptance criteria:**

- [x] `dispatch_nudge` is optional per host (absent = `false`, keeping older v2 catalogs usable); a non-boolean value is a catalog error; production catalog sets it explicitly `false` for every host.
- [x] The nudge decision depends only on mode, pin, host gate and whether this session was already denied; selftest covers each branch.
- [x] Reminder and deny reason text contain no task text.
- [x] `skills/tier-routing/SKILL.md` description triggers on creating any subagent/child agent; skill-sync check stays green.

**Verification:**

- [x] `python3 -B hooks/route_decide.py --selftest`, `python3 -B hooks/test-route-contract.py` and `/bin/bash scripts/validate.sh` pass.

**Dependencies:** None.
**Files likely touched:** `hooks/route_decide.py`, `config/routing.catalog.v2.json`, `hooks/test-route-contract.py`, `skills/tier-routing/SKILL.md`.
**Estimated scope:** M.

#### Task 10: Claude adapter nudge

**Description:** Encode the nudge decision for Claude PreToolUse(`Agent`): `additionalContext` for reminders, `permissionDecision: "deny"` with reason for the once-per-session auto block.

**Acceptance criteria:**

- [x] audit + unpinned + gate open → allow, reminder context, no `updatedInput`, no deny.
- [x] auto → first unpinned call per session is denied with a reason; later unpinned calls keep the existing apply behavior and add the reminder.
- [x] pin, frontmatter pin, `plugin:name` agents, `off`, closed gate, missing `session_id` and any exception → no reminder, no deny.
- [x] Audit records carry `nudge`; per-session deny state lives only in the data directory.

**Verification:**

- [x] `hooks/test-tier-guard.sh` covers every branch; new assertions are killed in `scripts/mutation-check.py`; `CLAUDE.md` hard rules match the new audit contract.

**Dependencies:** Task 9.
**Files likely touched:** `hooks/claude_hook.py`, `hooks/test-tier-guard.sh`, `scripts/mutation-check.py`, `CLAUDE.md`.
**Estimated scope:** M.

#### Task 11: Codex adapter nudge

**Description:** Encode the same decision for Codex PreToolUse(`spawn_agent`) under Codex's output rules: deny requires a non-empty reason, `ask` is unsupported, `updatedInput` still requires `allow`.

**Acceptance criteria:**

- [x] Same branch coverage as Task 10, including `opaque_token` inputs.
- [x] No output combination Codex 0.154.0 rejects (`ask`, empty deny reason, `updatedInput` without `allow`).

**Verification:**

- [x] `hooks/test-tier-guard-codex.sh` covers every branch; new assertions are killed in `scripts/mutation-check.py`.

**Dependencies:** Task 9; review after Task 10.
**Files likely touched:** `hooks/codex_hook.py`, `hooks/test-tier-guard-codex.sh`, `scripts/mutation-check.py`.
**Estimated scope:** M.

#### Task 12: Report and natural-trigger real-host evaluation

**Description:** Report nudge outcomes and measure whether nudged main agents pass explicit parameters in natural use on each host.

**Acceptance criteria:**

- [x] `/tier-report` shows counts of `none` / `reminded` / `denied` and the share of later unpinned-session dispatches that passed an explicit model.
- [x] ~~Claude Code CLI and Codex CLI each reach the spec thresholds over ≥10 natural dispatches, with 0 tradeoff tasks lowered and 0 pinned calls nudged.~~ Not met under audit (Claude 8/10 explicit, tradeoff 2/4); superseded by Task 15 under guard.
- [x] Evidence is recorded in `docs/research/` without raw task text.
- [x] `dispatch_nudge` is opened only for hosts with that evidence, after explicit user confirmation (decided in Task 15).

**Verification:**

- [x] `hooks/test-tier-commands.sh` covers the new report section; real-host protocol documented and reproducible.

**Dependencies:** Tasks 10 and 11.
**Files likely touched:** `hooks/tier_report.py`, `hooks/test-tier-commands.sh`, `docs/research/`, `config/routing.catalog.v2.json`.
**Estimated scope:** M.

### Phase 6: Default guard profile

#### Task 13: Guard profile in core, state and catalog

**Description:** Add `guard` as a routing profile between `audit` and `auto`, make it the production default, and let `/tier-mode` persist it without the auto quality gate.

**Acceptance criteria:**

- [x] `ROUTING_PROFILES` and catalog validation accept `guard`; the production catalog's `mode` is `guard`.
- [x] Under `guard`, `route()` never yields an applicable target (same pin / target semantics as `audit`).
- [x] `nudge_decision("guard", …)` behaves like today's auto nudge (deny once per session, then remind); `audit` stays remind-only.
- [x] `tier_state.py set guard` persists without the gate; `set auto` keeps its current refusal.

**Verification:**

- [x] `route_decide.py --selftest`, `test-route-contract.py` and `test-tier-commands.sh` cover each branch; new assertions are killed in `scripts/mutation-check.py`; `scripts/validate.sh` passes.

**Dependencies:** None.
**Files likely touched:** `hooks/route_decide.py`, `hooks/tier_state.py`, `config/routing.catalog.v2.json`, `hooks/test-route-contract.py`, `hooks/test-tier-commands.sh`, `scripts/mutation-check.py`.
**Estimated scope:** M.

#### Task 14: Guard in adapters, report and user-facing text

**Description:** Prove both adapters never emit `updatedInput` under `guard`, count `guard` in `/tier-report`, and align command, skill, README, CLAUDE.md and doctor wording with the new default.

**Acceptance criteria:**

- [x] Claude and Codex shell suites show `guard` denies once, then reminds, and never emits `updatedInput` even when `pre_dispatch_apply=true`.
- [x] `/tier-report` profile counts include `guard`; messages no longer claim the default is `audit`.
- [x] `/tier-mode` description, `skills/tier-routing/SKILL.md`, `README.md`, `CLAUDE.md` and `tier_doctor.py` describe `guard` as the default.

**Verification:**

- [x] Shell suites and skill-sync check pass; new assertions are killed in `scripts/mutation-check.py`; `scripts/validate.sh` passes.

**Dependencies:** Task 13.
**Files likely touched:** `hooks/test-tier-guard.sh`, `hooks/test-tier-guard-codex.sh`, `hooks/tier_report.py`, `hooks/tier_doctor.py`, `commands/tier-mode.md`, `skills/tier-routing/SKILL.md`, `README.md`, `CLAUDE.md`, `scripts/mutation-check.py`.
**Estimated scope:** M.

#### Task 15: Real-host re-evaluation under guard

**Description:** Repeat the Task 12 protocol (4 natural sessions per host, three real tasks each) with the default `guard` profile, then decide on opening `dispatch_nudge` for each host.

**Acceptance criteria:**

- [x] Each host meets the spec thresholds under `guard`, or the shortfall is recorded with evidence.
- [x] Evidence is recorded in `docs/research/` without raw task text.
- [x] `dispatch_nudge` is opened only for hosts that meet the thresholds, after explicit user confirmation.

**Verification:**

- [x] `/tier-report` statistics plus the per-dispatch category table reproduce the conclusion.

**Dependencies:** Task 14.
**Files likely touched:** `docs/research/`, `config/routing.catalog.v2.json`.
**Estimated scope:** M.

### Final checkpoint: v2 review

- [ ] All plan acceptance criteria and repository validation pass. (Blocked: Task 7 waits on Codex providing task text or trusted structured labels before dispatch.)
- [x] A fresh reviewer verifies model selection can move down as well as up.
- [x] Real-host evidence exists for every claimed automatic host. Only Claude Code CLI is claimed automatic in Host compatibility; its controlled auto run started an unpinned read-only child on `claude-haiku-4-5-20251001` (`docs/research/2026-09-13-claude-cli-v2-smoke.md`). Codex CLI / Desktop remain advisory. Checked 2026-09-14.
- [x] Semantic-provider network integration remains disabled unless separately approved. Catalog `semantic_provider.mode` is `disabled`; every local v2 routing record reports `disabled` (Claude 30, Codex 14); hooks import no network client. Checked 2026-09-14.

### Phase 7: Upstream tier, escalation and tier log fields

> Planned 2026-10-05 from spec sections「上游档位信号（tier）」「升档与收回」「每次派发必记的档位字段」.
> Code is untouched by this planning step.

**Where the work lands.** Both adapters already pass the full task text to `route_decide.route()` and log the
returned decision verbatim, so parsing, precedence and the new fields belong in the core; adapters only need
assertions that the fields arrive and nothing leaks. v2 has no explicit `floor` object today: the floor is the
third branch of `_requirements()` (irreversible side effect, missing/ambiguous acceptance, cross-cutting scope or
tradeoff load). Codex hooks receive `opaque_token`, so a marker in the task text is invisible there; on Codex the
upstream tier can only take effect through the main agent following `tier-routing`.

**Decisions D1–D3 — confirmed by the user on 2026-10-05 as proposed; written into the spec and the decided list above:**

- **D1 · Failure-signal transport (blocks Task 19).** The spec names `consecutive_failures` but v2 has no producer
  (it exists only as a v1 `ctx` input). Proposal: extend the same marker line with an optional non-negative integer,
  `<!-- tier-guard: tier=L1 failures=1 -->`. Upstream counts "result uncertain" as one failure, so no second
  keyword is needed. Requires a spec edit before Task 19.
- **D2 · Upstream tier vs the low-confidence branch (blocks Task 17).** When every signal is `unknown`, routing is
  conservative because information is missing, not because a floor rule fired. Proposal: a valid upstream tier
  counts as information, so it may route below that conservative default; only the irreversible / ambiguous /
  tradeoff floor stays binding. This narrows the decided rule「信息不足不能被路由到低能力候选」and needs explicit
  confirmation.
- **D3 · The L2 second-failure deny (blocks Task 20; boundary「任何会让守卫返回 deny 的改动」).** Proposal:
  `guard` and `auto` deny, `audit` only reminds (same split as the dispatch nudge); pinned dispatches are logged but
  not denied; the deny is gated by `host_capabilities.<host>.dispatch_nudge`, the only deny channel verified on a
  real host; it is not limited to once per session, because a re-dispatch with the same failure count should be
  reclaimed again.

#### Task 16: Parse the upstream tier marker and record `tier_source`

**Description:** Add a core parser for `<!-- tier-guard: tier=L1|L2|L3 [reason=…] -->` and accept it either from the
task text or from `optional_context` `schema_version: 2` (which adds an optional `tier`; `schema_version: 1` stays
valid). A valid tier maps to the existing capability labels and is used ahead of text inference; every decision
records `tier_source` as `upstream` or `inferred`.

**Acceptance criteria:**

- [ ] Exactly one well-formed marker on its own line with a case-exact `L1`/`L2`/`L3` is adopted; zero markers mean
  "not declared"; two or more, an illegal value, or an envelope whose fields do not match each degrade to
  `unavailable`, fall back to pure inference, and never make `route()` return a fallback.
- [ ] `tier_source` is `upstream` when the tier was adopted and `inferred` otherwise.
- [ ] `reason` never appears in the decision; only whether it was present and its SHA-256.

**Verification:**

- [ ] `route_decide.py --selftest` and `test-route-contract.py` cover each degrade path with one assertion apiece;
  the new assertions are killed in `scripts/mutation-check.py`; `check-mutation-anchors.py` and `validate.sh` pass.

**Dependencies:** None.
**Files likely touched:** `hooks/route_decide.py`, `hooks/test-route-contract.py`, `scripts/mutation-check.py`.
**Estimated scope:** M.

#### Task 17: Floor precedence, `tier_conflict`, and the `pin` / `floor` sources

**Description:** Enforce `pin > floor > tier > inferred`. An upstream tier above the floor wins; one below the floor
is overridden by the floor and the conflict is recorded as `tier_conflict: {upstream, floor}`. Pinned requests keep
today's behaviour and report `tier_source: pin`. Applies D2 to the low-confidence branch.

**Acceptance criteria:**

- [ ] A task that hits the irreversible floor and carries `tier=L1` ends at the floor and records `tier_conflict`
  (positive assertion); the same task without the marker records no conflict, and an `L3` marker on an `L1` task
  raises it to `L3` with no conflict (negative assertions).
- [ ] `tier_source` is separately verifiable for `pin`, `floor`, `upstream` and `inferred`.
- [ ] Recording a conflict never turns into a deny or a fallback.

**Verification:**

- [ ] Selftest and contract tests hold the positive and negative cases; mutants for the comparison direction and
  for "conflict recorded" are killed; `validate.sh` passes.

**Dependencies:** Task 16; D2.
**Files likely touched:** `hooks/route_decide.py`, `hooks/test-route-contract.py`, `scripts/mutation-check.py`.
**Estimated scope:** M.

#### Task 18: Tier fields reach both audit logs, and nothing leaks

**Description:** Prove through the real adapter entry points that `tier_source` and `tier_conflict` land in
`decisions.jsonl`, and add the log-leak assertions the spec requires: no marker `reason` text, no task text.

**Acceptance criteria:**

- [ ] Claude and Codex shell suites each feed a task carrying a marker with a distinctive `reason` and assert the
  new fields are present in the written record.
- [ ] The same suites assert the distinctive `reason` string and a distinctive task sentence occur nowhere in the
  log file (asserted, not inspected by hand).
- [ ] The Codex suite also covers an `opaque_token` task: no tier is adopted and `tier_source` is `inferred`.

**Verification:**

- [ ] `test-tier-guard.sh`, `test-tier-guard-codex.sh` and `validate.sh` pass; the leak assertions are killed by a
  mutant that logs the raw text.

**Dependencies:** Task 17.
**Files likely touched:** `hooks/test-tier-guard.sh`, `hooks/test-tier-guard-codex.sh`, `scripts/mutation-check.py`.
**Estimated scope:** S.

### Checkpoint: Upstream tier

- [ ] Tasks 16–18 pass `validate.sh`; mutation run has 0 survivors and 0 stale anchors.
- [ ] Review with the user before escalation work starts (D1 and D3 must be settled by then).

#### Task 19: Compute escalation from the failure count

**Description:** Using the transport chosen in D1, compute the escalated tier: an `L1` request with one or more
failures routes as `L2`; escalation never lowers the tier and never goes below the floor. Record
`escalation: {from, to, consecutive_failures}` only when an escalation happened. No deny yet.

**Acceptance criteria:**

- [ ] `L1` + failures ≥ 1 → `L2`, with the `escalation` object; failures = 0 or no marker → no `escalation` field.
- [ ] The escalated tier is never below the original tier and never below the floor (asserted on an
  irreversible-task fixture).
- [ ] An `L2` request with failures ≥ 2 is classified as "reclaim" in the decision, without any adapter output yet.

**Verification:**

- [ ] Selftest and contract tests; mutants on the thresholds (`>= 1`, `>= 2`) and on "only on escalation" are
  killed; `validate.sh` passes.

**Dependencies:** Checkpoint · Upstream tier; D1.
**Files likely touched:** `hooks/route_decide.py`, `hooks/test-route-contract.py`, `scripts/mutation-check.py`, `spec/tier-guard.md` (D1 wording).
**Estimated scope:** M.

#### Task 20: Reclaim to the main session after the second L2 failure

**Description:** Turn the core's "reclaim" decision into a deny through the existing channel, with a reason that
says this is the reclaim after the second failure and asks the main agent to handle or re-scope the task. Profile,
pin and gate behaviour follow D3.

**Acceptance criteria:**

- [ ] Claude suite: reclaim produces a deny with the reclaim reason and no `updatedInput`, under each profile per D3.
- [ ] Pinned, `off`, gate-closed and missing-`session_id` cases produce no deny, each with its own assertion.
- [ ] The once-per-session nudge marker is neither consumed nor checked by the reclaim deny.

**Verification:**

- [ ] `test-tier-guard.sh` (and the Codex suite for the visible-text path) plus `validate.sh`; every branch has a
  killed mutant.

**Dependencies:** Task 19; D3 (approved 2026-10-05).
**Files likely touched:** `hooks/route_decide.py`, `hooks/claude_hook.py`, `hooks/codex_hook.py`, `hooks/test-tier-guard.sh`, `hooks/test-tier-guard-codex.sh`, `scripts/mutation-check.py`.
**Estimated scope:** M.

#### Task 21: Teach the main agent the marker, and document the contract

**Description:** Update `tier-routing` so the main agent honours a marker it sees (the only path on Codex, where the
hook cannot read it), keeps floor precedence, and carries failure logs itself. Sync README, CHANGELOG and the spec's
acceptance list.

**Acceptance criteria:**

- [ ] `skills/tier-routing/SKILL.md` states marker precedence, the floor rule and that failure logs stay with the
  main agent; the skill-sync check passes.
- [ ] README documents the marker format and the Codex limitation; CHANGELOG has an Unreleased entry.
- [ ] No document claims the marker works through the Codex hook.

**Verification:**

- [ ] `validate.sh` (including the skill-sync check) passes; wording reviewed by the user.

**Dependencies:** Task 20.
**Files likely touched:** `skills/tier-routing/SKILL.md`, `README.md`, `CHANGELOG.md`, `spec/tier-guard.md`.
**Estimated scope:** S.

#### Task 22: Real-host check of marker, floor and reclaim

**Description:** On Claude Code CLI (where the hook sees the task text) run a small protocol: an `L1` marker on a
read-only task, a forged `L1` on an irreversible task, an `L3` marker on a trivial task, and an `L2` task with
`failures=2`. Record results in `docs/research/`.

**Acceptance criteria:**

- [ ] Each case's `tier_source`, `tier_conflict`, `escalation` and deny match the spec, read from an isolated audit
  directory.
- [ ] The evidence records no task text or `reason` text.

**Verification:**

- [ ] The research note reproduces each verdict from the audit records.

**Dependencies:** Task 21; user approval for `claude -p --plugin-dir` (writes under `~/.claude`).
**Files likely touched:** `docs/research/`.
**Estimated scope:** S.

### Checkpoint: Phase 7 complete

- [ ] Every spec acceptance criterion for upstream tier, floor precedence, `tier_source`, escalation and log leaks
  has a passing assertion.
- [ ] `validate.sh` passes; mutation run has 0 survivors and 0 stale anchors.
- [ ] Real-host evidence for Claude Code exists; the Codex limitation is documented, not claimed away.

**Out of scope for Phase 7:** writing `escalated` into v2 stop records (the spec's ordered precondition 1 — a
host-no-transcript share low enough to be representative — is not met); any `/tier-report` view of the new fields
(no acceptance criterion asks for it); making the reclaim deny depend on parsing subagent output (a Non-goal).

### Phase 8: Make subagent dispatch actually save money (with spec-guard)

> Spec: `spec/tier-guard.md` → 「Dispatch economics」(written after the fact, 2026-10-05: this phase was first planned
> without a spec update; the spec section and its assumptions were then reviewed by the user).
> Requested by the spec-guard project session on 2026-10-05, approved by the user the same day. Division of labour:
> spec-guard owns where and what to dispatch and the per-module cost report (it reads host session records, never tier-guard
> logs); tier-guard owns choosing a cheaper-but-sufficient model and telling the main agent when dispatch would not save.

**Decisions (user, 2026-10-05):** run the Claude cost experiment (budget about $8–15); the catalog constraint
「升档只许动 effort，不许换 slug」 may be relaxed if Codex L2 moves to Luna; the "not cheaper → do it yourself" hint starts in
the `tier-routing` skill only, no hook change.

**Why first:** whole-flow accounting on the textkit acceptance runs (sonnet parent) showed dispatch cost 2.0–2.8× the inline
run ($0.55–0.77 vs $0.271, after correcting cache-write pricing; first reported as 2.1–3.0×). A cheaper child model is necessary but not sufficient; the likely saving lever is main-session
context size (each inline tool call re-reads it). That has to be measured before any rule depends on it.

#### Task 23: Claude dispatch cost experiment
Opus parent; main-session context small (~30K) vs large (~200K, pre-loaded); inline `/build auto` vs spec-guard `--dispatch`;
2 runs each. Whole-flow cost = main + subagent transcripts, deduped per message.id. Output: the context size above which
dispatch is cheaper, in `docs/research/`.
**Acceptance:** 8 runs recorded with per-run cost split main/subagent; conclusion states the break-even or that none was found.

#### Task 24: Codex L2 candidate experiment (Luna vs Sol/medium)
The 10 Claude-side L2 tasks on Codex: `gpt-6.1-sol/medium` vs `gpt-6-luna` at `high` and `xhigh`; quality graded on pristine
tests; tokens from rollout `token_count` (run `codex exec` directly, not the ephemeral wrapper).
**Acceptance:** pass rate and per-task tokens/cost for each arm; explicit verdict whether Luna can take L2.

#### Task 25: Codex L2 catalog change (only if Task 24 passes)
Move Codex L2 to Luna; update catalog doc, CHANGELOG and contract tests; release. Ask before the release.

#### Task 26: "Not cheaper → do it yourself" in tier-routing
Skill text: when the chosen candidate is not cheaper than the main agent's own model (e.g. opus main + L3, or Codex main on
`gpt-6.1-sol/medium` + an L2 that stays on sol), do the task in the main session instead of dispatching. Wording informed by
Task 23. Skill-sync check passes.

#### Task 27: Joint test with spec-guard
Same 4–6 task module on Claude and Codex, dispatch vs no dispatch; spec-guard's cost report and tier-guard's logs must agree
on tiers and models.

### Phase 9: Closing review fixes and documentation (2026-10-06, user approved)

Source: the closing review (independent read-only reviewer plus my own data check); D1, D2, D3 and D6 were reproduced
before planning. Settled with the user: `/tier-label` stays but is labelled v1-only; Agent `description` and Codex
`task_name` are logged as length + SHA-256 only; "删除" / "delete" are **not** added to the irreversible words; the
duplicated hook sequence and the v1 code stay as they are.

#### Task 28: Routing fixes (D1, D2, D3)
- D1: under `auto`, fork and `plugin:name` agents are rewritten (reproduced: both got `updatedInput.model`). Skip the rewrite
  when the pin cannot be determined, in the Claude shell; v2 auto assertions for fork and plugin agents.
- D2: a task with both read-only and implementation markers is classified read-only (haiku). Return `unknown` instead.
- D3: `failures` written after `reason` is silently dropped. A `failures=N` token inside `reason` makes the marker invalid.
- Verify: selftest, both shell suites, new assertions red before the fix, mutants for each.

#### Task 29: Report and mode fixes (R1, R2, D4, D7)
- R1/R2: SubagentStop records without `agent_type` that link to no dispatch are host-internal. Count them on their own line;
  exclude them from the transcript-coverage ratio and from the fallback count.
- D4: `/tier-doctor` reads the mode with the same allowed profiles as the hooks.
- D7: `off` from the mode file logs nothing, including fallback paths.
- Verify: commands and observe suites, real-data report shows the split, mutants.

#### Task 30: Privacy and tier-label (spec change)
- Log Agent `description` and Codex `task_name` as `*_chars` + `*_sha256`; the report stops showing them as text.
- `/tier-label` description and output say it only labels v1 history records.
- Verify: an assertion that neither raw value appears in the log; mutants.

#### Task 31: Documentation pass
- README rewritten for a first-time reader: the problem, value and design ideas (including the measured verdict that
  dispatch mostly does not save money), install on Claude Code and Codex, modes, commands and skill, architecture,
  working with spec-guard (tier marker, cost report).
- Stale lines: hook header comments ("only auto denies"), SKILL.md quality-gate wording and old model names, command
  descriptions, CHANGELOG Unreleased.
- Research docs are historical evidence and are not rewritten.
- Verify: validate, skill-sync check, full mutation run.

## Risks and mitigations

| Risk | Impact | Mitigation |
|---|---|---|
| Semantic classifier itself costs more than it saves | High | Run only in gray cases; no provider by default; require cost/quality evidence before enablement. |
| Model catalog claims outlive host availability | High | Version catalog, capability-detect at adapter boundary, fail closed to advisory. |
| Desktop V2 does not apply updatedInput | High | Preserve advisory status; require pre-dispatch parameter-application evidence; do not emulate enforcement post-spawn. |
| agent-skills/spec-guard coupling leaks into runtime | Medium | Explicit envelope only; automated repository scan forbids state/command references. |
| An incorrect low route silently lowers quality | High | Conservative unknown handling, pin, audit rollout, labels and sampled quality checks. |
| A forged low tier in task text lowers a dangerous task | High | Floor always wins over tier; conflict recorded; positive and negative assertions (Task 17). |
| Upstream tier is silently ignored on Codex because the hook sees `opaque_token` | Medium | Main-agent path through `tier-routing` (Task 21); documented limitation; Codex suite asserts `inferred` for opaque text (Task 18). |
| The reclaim deny traps the main agent in a loop | Medium | Deny text asks to handle or re-scope; a new dispatch is a fresh `RouteRequest`; gated by `dispatch_nudge` (D3). |

## Sequencing

Tasks 1 → 2 are sequential. Tasks 3, 4 and 5 may proceed after Task 2 but all touch the route contract and should be reviewed serially in this single working tree. Task 6 follows their settled record shape. Tasks 7 and 8 come last because they must validate the code actually installed in each host, not just repository tests.

Phase 7 is sequential: Tasks 16 → 17 → 18 share the decision shape, then the checkpoint settles D1 and D3 before Tasks 19 → 20. Task 21 follows the final behaviour and Task 22 validates the code as it runs in the host.

Phase 9: Tasks 28 → 29 → 30 touch the hooks and are done serially; Task 31 comes last so the docs describe the final behaviour.
