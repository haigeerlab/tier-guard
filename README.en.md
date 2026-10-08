# tier-guard

[中文](README.md) | [English](README.en.md)

A subagent model-routing plugin for Claude Code and Codex. After the main agent decides to create a subagent, it selects the lowest-ranked qualified model from a capability catalog; on Codex, it also selects `reasoning_effort`. The main agent's model stays unchanged.

**Released version: 0.2.8 · Factory default: `off`.** The `tier-routing` skill guides the main agent to choose explicit parameters. Hook auditing, reminders, denial and rewriting depend on the mode and host. The plugin does not create tasks or decide task decomposition and acceptance criteria.

## 1. Project purpose

Subagents may inherit the main agent's model. Using a costly model for simple read-only work can add unnecessary overhead. tier-guard supplies a candidate catalog, pre-dispatch decisions and auditing to help choose a qualified model for work already selected for delegation.

“Lowest cost” means **the `cost_rank` ordering within the current catalog**, not a live price lookup or a guarantee of the lowest total task cost. The main agent remains responsible for defining the task, deciding whether to delegate and accepting the result.

In this repository's small-task experiments, delegation increased total cost by 15%–54%. One saving did not reproduce consistently, and Codex with long waits only matched the cost of doing the work directly. See the [dispatch economics verdict](docs/research/2026-10-06-dispatch-verdict.md). These results describe specific experiments, not every task.

## 2. Use cases and boundaries

Useful for tasks that already need context isolation or independent exploration, and for developers who need to observe requested models, routing suggestions and execution evidence. Small tasks that take only a few tool calls are usually better handled in the main session.

Current candidates come from the [v2 catalog](config/routing.catalog.v2.json):

| Required capability | Claude Code | Codex CLI / Desktop |
|---|---|---|
| L1: mechanical, read-only | `haiku` | `gpt-6-luna` / `high` |
| L2: bounded implementation with explicit acceptance | `sonnet` | `gpt-6-luna` / `high` |
| L3: cross-cutting tradeoffs, ambiguity or irreversible effects | `opus` | `gpt-6.1-sol` / `xhigh` |

- Parameters are selected before subagent creation; running agents are not switched.
- An explicit model or effort is a **pin** and is not rewritten by the hook. Claude environment variables and agent definitions can also establish a pin.
- Claude Code hooks can see task text. In tested versions, native Codex hooks receive only an opaque token and cannot independently classify the task. Codex relies on the main agent reading the skill and passing explicit parameters.
- There is no runtime dependency on agent-skills or spec-guard; they are optional upstream workflows or development tools.
- No external semantic provider is implemented. The router does not send task text to an external classification service. The host manages its own model services and network activity.
- Hooks read configuration, events and necessary host transcripts, and write local audit/state data when enabled. See [data and permissions](docs/reference.en.md#5-data-and-permissions).

Claude Code CLI has real dispatch evidence; Codex CLI / Desktop have main-agent pre-routing evidence. Claude Code Cloud and native Windows shells have not been verified by this repository; see [compatibility](docs/compatibility.en.md). A skill is an instruction executed by the main agent, not a guarantee that it will be loaded or followed on every natural dispatch.

## 3. Prerequisites

- An installed and authenticated Claude Code or Codex host that supports plugins, skills and the relevant hooks.
- `python3` and `/bin/bash`. The repository does not declare a verified minimum Python version; the full mutation suite uses interfaces introduced in Python 3.7. Repository checks target macOS Bash 3.2 compatibility. No `jq` or third-party Python packages are required.
- GitHub access and the Git environment required by the host to install a Git marketplace.
- Account access to the catalog's models and Codex effort levels. The catalog does not automatically discover account availability.
- Permission to execute hooks, read necessary transcripts and write plugin data. Codex hook trust must be reviewed in the CLI's `/hooks` interface.

Installation commands were checked against local help for Claude Code `2.1.291` and Codex CLI `0.160.0`. These are documentation-check versions, not minimum supported versions. The compatibility guide lists versions with real behavior evidence.

## 4. Quick start

### Claude Code

Install in a terminal:

```bash
claude plugin marketplace add haigeerlab/tier-guard
claude plugin install tier-guard@tier-guard
```

Restart the session, then check the mode inside Claude Code:

```text
/tier-guard:tier-mode
```

A first installation without overrides should show `off`. Then send:

```text
Use tier-routing to select a candidate model for a read-only review task and explain why; do not create a subagent yet.
```

Expect the main agent to explain the task boundary, candidate and whether delegation is worthwhile. To observe real hook behavior, switch to audit and explicitly request one read-only task with clear scope and acceptance:

```text
/tier-guard:tier-mode audit
Use tier-routing to create a read-only subagent: inspect only the README section headings and do not modify any files. Acceptance: return missing sections and explain why they are needed.
/tier-guard:tier-report
```

Real dispatch consumes host model usage. If the main agent chooses to do the task itself, there will be no subagent audit record; that does not prove the hook failed.

### Codex CLI / Desktop

Install a pinned release in a terminal:

```bash
codex plugin marketplace add haigeerlab/tier-guard --ref v0.2.8
codex plugin add tier-guard@tier-guard
```

If the same marketplace is already registered with another ref, follow the [update steps](#7-updates-and-uninstall) first. Repeating add does not change its ref.

Review the current plugin hooks through `/hooks` in Codex CLI and start a new session. Use native task dispatch in Desktop. `/hooks` is a CLI interaction, not an ordinary desktop chat message.

Use the same “select a model without creating a subagent” request to check the skill. **Installing this plugin does not register Claude Code commands such as `/tier-guard:tier-mode` in Codex.** To inspect or set a Codex mode, use the [script entry points](docs/reference.en.md#2-codex-and-ordinary-shell-entry-points) with the actual plugin path and Codex data directory.

The default `off` mode does not write hook logs. Audit verification requires setting `audit` before creating a subagent through native dispatch. Codex records normally show `task_visibility=opaque_token` and `applied=false`; this reflects the input boundary, not an installation failure.

## 5. Entry points, commands and parameters

Claude Code commands use the plugin namespace to avoid collisions:

| Entry point | Parameters and purpose |
|---|---|
| `/tier-guard:tier-mode` | No argument: mode and source; `off`, `audit`, `guard`: persistent mode changes; v2 rejects persistent `auto` |
| `/tier-guard:tier-report` | Summary; optional `--share [days]`, default 7 days, measures output-token share from Claude transcripts only |
| `/tier-guard:tier-doctor` | Read-only diagnosis of paths, effective mode and Codex hook records; cannot prove hook trust |
| `/tier-guard:tier-label <id> <fp\|tp\|reject\|accept>` | User-provided labels for historical v1 records; not applicable to v2 |
| skill `tier-routing` | Before dispatch, decide whether to delegate, select a candidate and pass explicit parameters to the new subagent; may be invoked by name |

| Mode | Claude Code CLI | Codex CLI / Desktop (production gates) |
|---|---|---|
| `off` (factory default) | No recording, reminders, denial or rewriting; skill remains available | Same |
| `audit` | Records suggestions; unpinned dispatch may receive a reminder | Auditing; reminder gate closed |
| `guard` | No parameter rewriting; denies the first unpinned dispatch per session, then reminds; L2 failure reclaim is evaluated separately | Auditing; reminder, denial and rewriting gates closed |
| `auto` | Controlled temporary mode; may rewrite unpinned, classifiable inputs on a supported host; first-dispatch denial still applies | Automatic rewriting unavailable; opaque inputs are not rewritten |

`guard` may affect host-created subagents such as Explore and add a retry turn. Factory `off` does not replace an existing saved mode. Mode precedence is `TIER_GUARD_MODE` → the data directory's `mode` file → catalog default.

`auto` is for experiments explicitly chosen by the user. If the mode command refuses it, do not ask the agent to bypass the refusal by changing environment variables or state files. See the [usage and configuration reference](docs/reference.en.md) for parameters, upstream tier markers and configuration limits.

## 6. Output and acceptance

Normally installed plugin data directories are:

- Claude Code: `~/.claude/plugins/data/tier-guard-tier-guard/`
- Codex: `~/.codex/plugins/data/tier-guard-tier-guard/`

Host injection or user overrides can change the path. Use state / doctor output to determine the actual directory.

| What to verify | Required evidence |
|---|---|
| Installation | Correct version, enabled state and path in the host plugin inventory; start a new session |
| Default state | state / doctor shows `off` and its source; no new logs is expected |
| Audit pipeline | Native dispatch in `audit` / `guard` adds an `agent` or `codex-spawn` event to `decisions.jsonl` |
| Main-agent pre-routing | Dispatch explicitly includes the selected model and, on Codex, effort; actual execution needs separate verification |
| Automatic rewriting | `applied=true` means the hook emitted a rewrite; also verify the host's actual execution receipt |
| Claude actual execution | `SubagentStop` / transcript supplies model and tokens; unobserved does not mean zero usage |

In 0.2.8, report reads the current mode from the current configuration regardless of empty or v1-only logs and preserves v1 historical statistics; doctor/report accept explicit `--config`. After upgrading from 0.2.7, restart the session and verify the loaded version. See [compatibility and known limitations](docs/compatibility.en.md).

tier-guard does not convert tokens to currency. For module-level costs covering the main session and subagents, optionally use [spec-guard](https://github.com/haigeerlab/spec-guard-plugin)'s cost-report tools. Neither plugin reads the other's data at runtime.

## 7. Updates and uninstall

### Claude Code

```bash
claude plugin marketplace update tier-guard
claude plugin update tier-guard@tier-guard
```

Restart after updating and verify the version and mode. Existing persistent modes and environment variables may remain effective.

Uninstall while preserving data:

```bash
claude plugin uninstall tier-guard@tier-guard --keep-data
```

Without `--keep-data`, the host's uninstall policy determines persistent-data handling. Back up audit records and labels you need. For a project / local installation, pass the matching `--scope` when uninstalling.

### Codex

A pinned tag does not automatically follow new releases. CLI 0.160.0 includes the ref in source matching, so repeating add cannot change it. Back up data you need, remove the old marketplace registration, add the target tag, install the plugin and verify its version:

```bash
codex plugin marketplace remove tier-guard
codex plugin marketplace add haigeerlab/tier-guard --ref v0.2.8
codex plugin add tier-guard@tier-guard
```

This example registers the current release again; replace the tag when upgrading. The source is unavailable between removal and reinstallation. See Codex 0.160.0's [source matching](https://github.com/openai/codex/blob/rust-v0.160.0/codex-rs/core-plugins/src/marketplace_add/metadata.rs) and [same-name source rejection](https://github.com/openai/codex/blob/rust-v0.160.0/codex-rs/core-plugins/src/marketplace_add.rs). For a branch-tracking marketplace, `codex plugin marketplace upgrade tier-guard` refreshes its source before reinstallation; it does not move a pinned tag to the latest release. Restart and review hook trust after updating.

```bash
codex plugin remove tier-guard@tier-guard
```

Removing a plugin and removing a marketplace are separate operations. Back up data before uninstalling. Codex remove help promises uninstall and cache removal, not guaranteed data preservation or complete erasure. To clean up data, confirm the actual directory before deleting this plugin's data yourself. Host transcripts are separate from plugin data.

## 8. Troubleshooting

| Symptom | Checks and action |
|---|---|
| No logs | Check effective mode first: `off` does not record. Then check enabled state, new session, data path, hook trust and whether a subagent was actually created |
| Codex cannot find `/tier-mode` | Use the script entry points; Claude command files do not register Codex slash commands |
| Mode change has no effect | Check `TIER_GUARD_MODE`, which overrides the persistent file; ensure command and hook use the same directory |
| Installed 0.2.7 report shows `dry-run` | Old report configuration limitation; confirm with state / doctor. Upgrade to 0.2.8, restart the session and verify again |
| Codex `opaque_token` / `applied=false` | Expected boundary on tested hosts; use main-agent pre-routing rather than changing gates to force automatic routing |
| guard denies first dispatch | Expected; the main agent should retry with explicit catalog parameters. L2 second-failure reclaim is not limited to once per session |
| Model unavailable or effort rejected | Check account and host support; the catalog is not an account-availability guarantee |
| Audit exists, actual execution unknown | Check whether the host supplies and saves transcripts; Codex currently audits request parameters only |
| No hook output, fallback logged | Check Python, JSON configuration and permissions; exceptions attempt to allow execution and log, but logging is not guaranteed |

“No records” alone does not establish that the plugin is uninstalled or untrusted. See the [reference](docs/reference.en.md) for diagnosis steps.

## 9. Architecture and documentation

```text
Main agent decides whether to delegate
  ├─ tier-routing skill: reads task text, selects a candidate, passes explicit parameters
  └─ host hook: PreToolUse → adapter → route_decide.py → audit / reminder / rewrite
       └─ Claude SubagentStop: reads actual execution model and usage
Catalog: config/routing.catalog.v2.json
Local data: decisions.jsonl, mode, nudge-denied/, historical labels.jsonl
```

Decision precedence is **pin → floor (minimum capability) → valid upstream tier → text inference**. A low-tier marker cannot override the floor; unknown requirements are handled conservatively. The [spec](spec/tier-guard.md) defines full constraints and the read-only exemption.

- [Usage and configuration reference](docs/reference.en.md)
- [Current compatibility and known limitations](docs/compatibility.en.md)
- [Documentation index and historical evidence](docs/README.en.md)
- [Changelog](CHANGELOG.md)

## 10. Development, contributions and feedback

Run the free local validation:

```bash
/bin/bash scripts/validate.sh
```

See the [contribution guide](docs/contributing.en.md) for development rules, focused tests, mutation tests and real-host verification boundaries. Contributions should explain the problem, impact, scope and evidence. Submit feedback through [GitHub Issues](https://github.com/haigeerlab/tier-guard/issues) and changes through [Pull Requests](https://github.com/haigeerlab/tier-guard/pulls).

### Reporting a bug

1. Check troubleshooting above and the [known limitations](docs/compatibility.en.md), then search existing Issues for the same problem.
2. Sign in to GitHub and select **New issue** on the Issues page. Use a title describing the symptom, such as “Native dispatch does not write audit logs in audit mode”.
3. Include minimal reproduction steps, expected and actual behavior, plugin version, host name/version, operating system, and mode/source. Attach only necessary, sanitized log excerpts. If reproduction is intermittent, describe the conditions and frequency.

Include relevant event types to help locate the dispatch or observation stage. Do not publish credentials, full task text, raw transcripts or unchecked logs.

## 11. License

This project uses the [Apache License 2.0](LICENSE). The LICENSE file contains the authoritative terms.
