# Changelog

All notable user-facing changes are documented here. Version numbers follow
[Semantic Versioning](https://semver.org/).

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
