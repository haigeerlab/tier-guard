# Changelog

All notable user-facing changes are documented here. Version numbers follow
[Semantic Versioning](https://semver.org/).

## [0.2.7] - 2026-10-06

### Changed

- **The factory default mode is now `off` instead of `guard`.** Measured
  dispatch mostly does not save money, and under `guard` the subagents
  Claude Code spawns on its own (Explore, general-purpose) also triggered
  the once-per-session deny, costing users who never dispatch an extra
  main-session turn. With `off` the hooks do nothing (no deny, no reminder,
  no log); the `tier-routing` skill still guides the main agent to pick an
  explicit model. Turn the hooks on with `/tier-mode guard` or
  `/tier-mode audit`. A mode already set through `/tier-mode` is kept.

- The log no longer stores the Agent `description` or the Codex
  `task_name` as text, only their length and SHA-256, the same as the
  prompt.
- `/tier-label` says it only labels v1 history records and refuses v2
  records with that explanation.
- README rewritten: the problem, the measured verdict that dispatch mostly
  does not save money, design principles, install on both hosts, modes,
  commands, architecture, and the spec-guard tier marker.

### Fixed

- Under `auto`, `fork` and `plugin:name` agents were rewritten even though
  tier-guard cannot tell whether they are pinned (a plugin agent's
  frontmatter may set a model). They are now left alone, as the spec says.
- A task with both a read-only phrase and an implementation phrase ("do a
  read-only review first, then implement the fix") was routed as read-only,
  to the cheapest model. It now routes as unknown, which is conservative.
- In the upstream tier marker, `failures` written after `reason` was
  swallowed by `reason` and silently lost, so the reclaim never fired. A
  `failures=` inside `reason` now makes the marker invalid.
- `/tier-report` counted host-internal subagents (no `agent_type`, linked
  to no dispatch) as dispatches. On a real log that showed 86% of
  dispatches as unobserved and 2653 guard fallbacks; they now get their own
  line, and the same log reads 0% missing and 0 fallbacks.
- `/tier-doctor` could show a legacy mode such as `dry-run` that the hooks
  ignore; it now shows the mode the hooks actually use.
- `off` set through `/tier-mode` still logged routes that fell back
  without a profile. It now logs nothing.

## [0.2.6] - 2026-10-06

### Added

- `tier-routing` tells a Codex main agent to wait for a dispatched subagent in
  one long `wait_agent` call (the largest allowed `timeout_ms`) instead of
  polling. In the spec-guard joint test the main agent polled every 10 to 30
  seconds, 25 to 31 times per run; each return is a main-session turn that
  re-reads the whole context, so the run cost more than doing the work itself
  even though the Luna subagents cost about $0.07 in total. Codex's own prompt
  already says to prefer waits of minutes and was not followed. spec-guard's
  dispatch rule says the same thing.
  Verified in a rerun with the guidance in place: waits dropped to 5-7 per
  run, each lasting until the subagent finished (up to 261s, no truncation),
  and dispatching every task cost the same as not dispatching instead of more
  than double.

### Fixed

- The dispatch cost figures quoted in 0.2.5 priced every cache write at 1.25x
  input. Claude Code's main session writes one-hour cache entries (2x input)
  while subagents write five-minute ones (1.25x), so the main session was
  undercounted. Corrected: dispatching the small tasks cost 15% to 54% more,
  not 19% to 63%, still about $0.21 more per run; the direction is unchanged.
  The `tier-routing` wording and the research note carry the corrected numbers.

## [0.2.5] - 2026-10-05

### Added

- `tier-routing` now tells the main agent when not to dispatch at all. If the
  chosen candidate is not cheaper than the main agent's own model, or the task
  is small and well specified, doing it in the main session is usually
  cheaper. Measured with an opus main session and sonnet subagents on two small
  tasks: dispatching cost 19% to 63% more, because the main session still read
  the diff, ran the tests and committed, so it made as many turns as doing the
  work itself and every subagent was pure extra. Dispatch pays off for tasks
  that need a lot of exploration or debugging. Details in
  `docs/research/2026-10-05-dispatch-cost-experiment.md`.

### Changed

- Codex L2 (bounded implementation with explicit acceptance) now routes to
  `gpt-6-luna` / `high` instead of `gpt-6.1-sol` / `medium`. The candidate
  `codex-sol-medium` is removed and `codex-luna-high` takes the
  `implementation` and `bounded_change` capabilities; L3 stays on
  `codex-sol-xhigh`. On 10 L2 tasks both arms passed 10/10 with no test
  tampering, and Luna cost about 1/14 as much per task ($0.0050 against
  $0.0690 with cached input at 10%, $0.0171 against $0.2636 at full price).
  `gpt-6.1-sol` / `medium` is also the default model of a Codex main session,
  so dispatching to it saved nothing. The evidence has a ceiling effect: all
  arms hit 10/10, so it shows Luna is enough for typical L2 work, not for
  harder L2 work, and each cell ran once. This changes the previous rule that
  tier upgrades only change effort: L2 to L3 on Codex now changes the model
  slug too. The Claude candidates and the frozen v1 table are unchanged.
  Evidence: `docs/research/2026-10-05-codex-l2-luna-experiment.md`.

## [0.2.4] - 2026-10-05

### Fixed

- Subagent token usage was counted about twice. The host writes one assistant
  message as several transcript lines, one per content block and again while
  streaming, and each line carries the same or a growing usage. Summing every
  line overcounted input by 1.97x, cache write by 1.96x and cache read by 1.83x
  on 109 real transcripts (output only 1.05x). Usage is now summed once per
  `message.id`, keeping the largest line. New stop records carry
  `usage_basis: message-id-dedup` so the report can tell them apart.
- `/tier-report` counted a resumed subagent once per stop. A resumed subagent
  appends to the same transcript and fires `SubagentStop` again, and each record
  holds the whole file's cumulative usage, so the table added the same work
  several times; records without stored usage were worse, each re-reading the
  file's current total. The table now counts each subagent once: it re-reads the
  transcript when it still exists, otherwise uses the latest record written
  with the fixed method. Subagents left with only pre-fix usage are kept out of
  the averages and counted in a note under the table.
- The L2 cost experiment had the same double count in its grading script. The
  corrected figures are $4.13 in total and an Opus/Sonnet ratio of 1.68x
  (1.50-1.96x); the conclusion that Sonnet is cheaper on every L2 task stands.

## [0.2.3] - 2026-10-05

### Added

- Upstream tier marker. A task can now carry a line of its own,
  `<!-- tier-guard: tier=L1|L2|L3 [failures=N] [reason=…] -->`, and the router
  uses that tier instead of guessing from the text. It travels in the task text
  because the hook sees nothing but `tool_input`; there is no side channel, and
  tier-guard still never reads an upstream tool's files or state. Anything
  malformed (no marker, two markers, a lowercase `l2`, a negative `failures`,
  text on the same line) degrades to "no marker" and routing falls back to
  inference, so a bad marker can never make the guard fail. `optional_context`
  gains `schema_version: 2` with an optional `tier`; version 1 envelopes keep
  working. If an envelope tier and a marker disagree, neither is trusted and
  routing falls back to inference.
- Precedence is pin > floor > tier > inferred, and an upstream tier cannot lower
  the floor. The marker rides in task text, so the text can forge it: without
  this rule a task that says `tier=L1` could route an irreversible `git push` to
  the cheapest model. Irreversible, ambiguous, cross-cutting and tradeoff work
  stays on the top tier, and the attempt is recorded as `tier_conflict:
  {upstream, floor}`. Recording a conflict never denies or changes the dispatch.
  With no floor, a valid tier now wins even over the conservative "not enough
  information" default, because a declared tier is information.
- `tier_source` (`pin`, `floor`, `upstream` or `inferred`) in every v2 decision,
  so a log reader can see where a tier came from instead of reconstructing it.
- Escalation and reclaim, driven by the marker's `failures` count (tier-guard
  does not judge failure itself; the upstream says so). `tier=L1` with at least
  one failure routes as L2, never below the floor, and is logged as
  `escalation: {from, to, consecutive_failures}`, where `to` is the final tier
  after the floor. `tier=L2` with two or more failures is a reclaim: on Claude
  Code the hook denies the dispatch with a reason that names the second failure
  and asks the main agent to handle the task or re-scope it as a new one;
  `audit` only reminds, and pinned dispatches, `off` and a closed
  `dispatch_nudge` gate do nothing. The reclaim deny is live on Claude Code,
  because its `dispatch_nudge` gate is open; Codex is unchanged, because its
  gate is still closed. Unlike the first-dispatch nudge, it does not need a
  `session_id`, is not limited to once per session and never touches the nudge
  marker, so the same failure count re-dispatched is reclaimed again. The
  deny never carries `updatedInput`, even under `auto`.
- New log fields: `tier_source`, `tier_conflict`, `escalation`, `reclaim` (in
  the decision) and `reclaim_output` (on the record, only when the hook emitted
  something). The marker's `reason` is logged only as a presence flag and a
  SHA-256, and neither the reason, the failure log nor the task text is ever
  written; assertions in both adapter suites read the whole log directory to
  prove it.
- `tier-routing` now teaches the main agent the marker: honour it, never go
  below the floor, escalate at one failure, handle the task itself at two, and
  carry failure logs to the next attempt itself. This matters most on Codex:
  its hook sees only an opaque token and cannot read the marker, so the skill
  is the only way the marker takes effect there.

### Fixed

- The first-dispatch deny said `tier-guard（auto）` even under `guard`, the
  default profile, so a user being stopped was told the wrong mode. The text is
  shared by `guard` and `auto`, so it now names no mode at all.
- `scripts/codex-cli-preroute-smoke.sh` printed an empty thread table on macOS:
  Codex records the resolved `/private/var/...` path and the script queried
  with `/var/...`. It also opened Codex's state database read-write and left
  one more trust entry in `~/.codex/config.toml` on every run. It now resolves
  the path, opens the database read-only, and runs every probe under one fixed
  repository, so Codex asks for trust once and keeps a single entry.

## [0.2.2] - 2026-10-05

### Added

- `SubagentStop` records the token usage the host already reports in the
  subagent transcript (input, cache write, cache read, output), summed over
  every assistant message. When the transcript carries no usage at all the
  field is omitted rather than written as zeros, so "no data" and "used
  nothing" stay distinguishable. `/tier-report` adds a table of average tokens
  by the model that actually ran. It deliberately converts nothing to dollars:
  prices change and differ by account, and the counts are the durable fact.

### Fixed

- `SubagentStop` no longer discards the record when it cannot read the
  subagent's transcript. The read happened before the record was built, so a
  missing file threw away everything — including the `session_id` and the
  transcript path the report needs to recover later — and left a three-field
  error row. On this machine that path covered 2610 of 3044 stop records
  (85.7%). The record is now built first and kept; a missing transcript is
  marked `transcript_status: missing` and, crucially, no longer counted as a
  guard fallback. Those two things are different: `fallback` means the guard
  itself hit an exception path and is how its own faults are diagnosed, while
  a host that writes no transcript for some kinds of subagent is a normal
  condition. Conflating them buried real faults under 86% noise. `/tier-report`
  now shows that share on its own, counting both the new field and the older
  `FileNotFoundError` rows so the figure stays honest on existing logs.

  This recovers no lost observations: for those dispatches the transcript was
  never written at all, so the model that actually ran is unknowable. The
  escalation design's precondition in the spec has been corrected accordingly
  — the metric that matters is split into a guard-fault rate, which should be
  near zero, and a no-transcript share, which is a host property that may not
  be movable at all.

  The v1 handler has the same defect and is deliberately left alone: it is the
  frozen compatibility layer, off the production path, and changing its record
  shape would change v1 report semantics for no production benefit.

- Claude Code pin detection missed a model source the host actually honours.
  `CLAUDE_CODE_SUBAGENT_MODEL_FORCE` and `CLAUDE_CODE_SUBAGENT_MODEL` configure
  the subagent model in Claude Code 2.1.289, but tier-guard read neither, so a
  dispatch the user had already pinned through the environment counted as
  unpinned. Under `auto` that would have rewritten the model and overridden an
  explicit choice, breaking the rule that an explicit model is never rewritten.
  Both variables are now pin sources, ranked below `tool_input.model` and the
  agent definition's frontmatter. Empty, `inherit` and `default` are treated as
  unset, matching the host's own check — counting them as pins would silently
  stop routing an entire class of dispatches. The same rule now applies to an
  agent definition's frontmatter: `model: inherit` or `model: default` is not
  an explicit choice and no longer counts as a pin. No live behaviour changed: the
  default profile is `guard`, which never rewrites.

### Changed

- v2 candidate catalog: the Codex column moves to the gpt-6 generation —
  `gpt-6-luna` / `high` for mechanical read-only work, and `gpt-6.1-sol` at
  `medium` / `xhigh` for the two higher tiers. `gpt-5.6-terra` leaves the
  catalog: it costs more per output token than `gpt-6.1-sol` and scores lower,
  so it was dominated on both axes. Candidate ids change accordingly
  (`codex-luna-high`, `codex-sol-medium`, `codex-sol-xhigh`). The Claude column
  is unchanged: the Agent tool's `model` parameter only accepts the family
  aliases, and it exposes no reasoning-effort or tool-restriction parameter to
  route on. Which concrete model an alias resolves to is decided by the host at
  runtime — measured here to follow the session model within its family — so
  tier-guard routes by family and makes no promise about the exact model. The v1 compatibility table in `routing.default.json` is frozen on the
  previous models on purpose. Rationale, availability measurements and the
  limits of that evidence are in
  `docs/research/2026-10-model-catalog-update.md`.

- The canonical repository moved to `haigeerlab/tier-guard`. The previous
  `haigeer-labs/tier-guard` repository is no longer reachable, so marketplace
  entries that point at the old owner must be removed and re-added against the
  new one. Commit history, tags `v0.1.1`–`v0.2.1` and the plugin version are
  unchanged by the move.

## [0.2.1] - 2026-09-14

### Fixed

- `/tier-report` no longer shows "linked 0 / N" in the suggested-vs-actual
  section for v2 records: it now reports how many v2 dispatches have an
  observed actual execution (matching the routing audit table), and the v1
  line counts only legacy records.

## [0.2.0] - 2026-09-14

### Added

- `guard` routing profile: under a host whose `dispatch_nudge` gate is open,
  the first unpinned child dispatch in each session is denied once with the
  host's candidate catalog summary, later unpinned dispatches get a reminder,
  and parameters are never rewritten. `/tier-mode set guard` persists without
  the auto quality gate.
- Reminder and deny texts include the host's candidate catalog summary and a
  rule to pick high-capability candidates for unclear, tradeoff,
  cross-cutting or irreversible work.
- `/tier-report` shows reminder / deny counts, the share of later same-session
  dispatches that passed explicit parameters, and pinned dispatches that were
  nudged; the v2 profile count includes `guard`.
- Claude Code v2 records the child's actual model from `SubagentStop`, and the
  report re-reads the transcript when the hook fired before it was flushed.

### Changed

- The default profile is now `guard` instead of `audit`.
- `claude-code.dispatch_nudge` is enabled in the production catalog, so Claude
  Code CLI denies the first unpinned child dispatch in each session once by
  default. `audit` remains available as remind-only.
- Codex `fork_turns` is no longer treated as an unknown pin.

### Known limitations

- `codex-cli.dispatch_nudge` stays disabled: in natural use the Codex parent
  already passes explicit parameters, and one tradeoff task out of four was
  explicitly routed to a lower tier by the parent, which guard respects as a
  pin.

## [0.1.1] - 2026-09-13

### Added

- Select the lowest-cost qualified `model` and `reasoning_effort` for a child
  agent when the parent can read the child-task text before dispatch.
- Audit records, reports, labels, and diagnostics for routing decisions without
  storing raw task text.
- Claude Code v2 pre-dispatch auto-routing for eligible unpinned child tasks;
  the default remains `audit` until its quality gate is met.

### Changed

- Codex and Claude plugin manifests now use the public `0.1.1` release version
  instead of a local Codex cache-busting snapshot.

### Known limitations

- Codex Multi-Agent V2 hooks receive an opaque task token rather than semantic
  child-task text. They therefore remain audit-only and never infer an
  automatic lower- or higher-tier route from that token. Parent-agent plaintext
  pre-routing remains the supported Codex workflow.
