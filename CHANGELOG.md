# Changelog

All notable user-facing changes are documented here. Version numbers follow
[Semantic Versioning](https://semver.org/).

## [Unreleased]

### Changed

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
