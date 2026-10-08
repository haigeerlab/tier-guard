# Usage and configuration reference

[中文](reference.md) | [English](reference.en.md) · [Back to README](../README.en.md)

For the default v2 catalog in 0.2.7. Host commands and script invocations are different. Replace shell path placeholders with actual installation paths before running examples.

Runtime tool output is currently primarily Chinese. Both references explain the same modes, fields and acceptance evidence; structured log field names are identical.

## 1. Claude Code commands

Use these inside a Claude Code session:

| Command | Arguments | Reads and writes |
|---|---|---|
| `/tier-guard:tier-mode` | None: mode and source; `off` / `audit` / `guard`: save mode; `auto`: rejected in v2 | show is read-only; set writes `mode` |
| `/tier-guard:tier-report` | `--share [days]`; defaults to 7 days | Reads logs and may reread Claude transcripts; share scans additional Claude project transcripts |
| `/tier-guard:tier-doctor` | None | Reads configuration and logs; cannot inspect Codex trust |
| `/tier-guard:tier-label` | `<tool_use_id> <fp\|tp\|reject\|accept>` | Appends to `labels.jsonl`; accepts user-provided v1 judgments only |

`fp` / `tp` mean false / true positive for historical irreversible-signal hits. `reject` / `accept` mean rejected / accepted historical T1 output. Missing IDs, mismatched record types and v2 records are rejected. This is not a quality-calibration tool for current v2 routing.

## 2. Codex and ordinary shell entry points

Codex does not obtain Claude slash commands from `commands/*.md`. Run `codex plugin list --available --json` to locate tier-guard's version, enabled state and source path, then confirm the plugin root contains `hooks/tier_state.py` and its manifest. If the output points only to a marketplace, locate its tier-guard plugin directory. Do not hardcode an old version's cache path.

`TIER_GUARD_PLUGIN_ROOT` below is **a shell variable for this example**, not an environment variable automatically consumed by the plugin:

```bash
TIER_GUARD_PLUGIN_ROOT="/absolute/path/to/tier-guard"
TIER_GUARD_DATA_DIR="$HOME/.codex/plugins/data/tier-guard-tier-guard"
python3 "$TIER_GUARD_PLUGIN_ROOT/hooks/tier_state.py" show --data "$TIER_GUARD_DATA_DIR"
python3 "$TIER_GUARD_PLUGIN_ROOT/hooks/tier_doctor.py" --data "$TIER_GUARD_DATA_DIR"
python3 "$TIER_GUARD_PLUGIN_ROOT/hooks/tier_report.py" --data "$TIER_GUARD_DATA_DIR"
```

To enable auditing, the user runs:

```bash
python3 "$TIER_GUARD_PLUGIN_ROOT/hooks/tier_state.py" set audit --data "$TIER_GUARD_DATA_DIR"
```

Replace `audit` with `off` to turn it off. This modifies the mode file in the specified directory, not every host's configuration: command and hook must use the same directory. If an environment variable overrides the mode, address it in the host's startup environment and start a new session.

Script interfaces:

| Script | Arguments | Defaults and purpose |
|---|---|---|
| `tier_state.py` | `show` or `set <mode>`; `--data DIR`; `--config PATH` | No action means show; reads the plugin v2 catalog by default |
| `tier_doctor.py` | `--data DIR` | Diagnoses paths, effective mode, logs and Codex spawn records |
| `tier_report.py` | `--data DIR`; `--recent N`; `--share [days]`; `--projects DIR` | recent: 10; share: 7 days; projects: `~/.claude/projects`, not total Codex usage |
| `tier_label.py` | `<tool_use_id> <fp\|tp\|reject\|accept>`; `--data DIR` | Historical v1 user labels only |

These are supported parameters, not a promise of graceful handling for every missing or invalid argument. Supply complete, valid values as listed.

## 3. Configuration sources and precedence

| Setting | Precedence / scope |
|---|---|
| Data directory | Script `--data` → `TIER_GUARD_LOG_DIR` → host-injected `CLAUDE_PLUGIN_DATA` → `~/.local/state/tier-guard` |
| Mode | `TIER_GUARD_MODE` → `<data directory>/mode` → the selected configuration's `mode` |
| Hook catalog | `TIER_GUARD_CONFIG` → plugin `config/routing.catalog.v2.json` |
| state configuration | Script `--config` → default plugin v2 catalog; **does not automatically read `TIER_GUARD_CONFIG`** |
| doctor / report configuration | Default plugin catalog; a custom hook catalog is not automatically propagated |

A normal host installation generally injects its plugin data path. An ordinary shell does not know whether you mean Claude or Codex data, so pass `--data` explicitly.

Old persistent modes and environment overrides may remain. Under v2, a legacy `dry-run` mode file falls back to the catalog default. Do not edit the file to bypass an `auto` refusal. With a custom catalog, state can inspect it using the matching `--config`, but doctor / report do not support that option. Also check the hook record's actual `catalog_identity` when diagnosing configuration differences.

Key catalog fields:

- `schema_version: 2`, `mode`: contract version and factory mode.
- `routing.pin_policy: respect`: preserve explicit pins; `unknown_requirement: conservative`: choose conservatively for unknown requirements.
- `candidates`: `id`, `host`, `model`, `reasoning_effort`, `cost_rank`, `auto_eligible`, `capabilities`. Select qualified candidates by `cost_rank`, then `id`.
- `host_capabilities.<host>.pre_dispatch_apply`: evidence for host rewriting; `dispatch_nudge`: reminder / denial gate.
- `classification`: rule signals; `semantic_provider.mode: disabled`: no external semantic provider is implemented.

Capability gates are not ordinary user switches. Temporary `auto` cannot bypass closed gates or opaque task inputs. Expanded candidates, changed pin semantics and new host support require design and real-behavior validation first.

## 4. Upstream tiers, escalation and reclaim

An upstream tool or main agent may put exactly one marker on its own line in the subtask text:

```text
<!-- tier-guard: tier=L2 failures=1 reason=Implement the confirmed design with explicit acceptance -->
```

| Field | Requirement |
|---|---|
| `tier` | Required; case-sensitive `L1`, `L2` or `L3` |
| `failures` | Optional nonnegative integer: previous consecutive failures of the same task; the plugin does not judge failure |
| `reason` | Optional and last; for human readers, not routing; its text is not written to the audit log |

Field order is tier → failures → reason. Duplicate markers, markers not on a separate line, invalid values or `failures=N` embedded in reason make the marker unavailable and return to inference. The upstream decides whether uncertainty counts as failure; the plugin does not read or forward failure logs.

- Precedence: pin → floor → upstream tier → inference. A valid marker may be lower than the conservative unknown-information tier, but never below the floor.
- The floor depends on core risk signals and the resulting required capabilities. Explicit mechanical, small-scope, read-only tasks have an existing exemption; a single keyword does not necessarily mean L3.
- `tier=L1` with `failures>=1`: escalate the effective tier to at least L2; the floor may raise it further.
- `tier=L2` with `failures>=2`: the main agent should reclaim or redefine the task. The Claude hook denies under guard / auto when unpinned and gated on; audit reminds. Reclaim needs no session ID and does not consume the first-dispatch denial marker.
- Codex hooks cannot see the marker; the skill guides the main agent to follow these rules. The hook does not deny reclaim when off, pinned, gated off or pin status is unknown.

## 5. Data and permissions

| File / source | Purpose |
|---|---|
| `decisions.jsonl` | Routing/event audit: models, effort, timestamps, session/tool identifiers, catalog fingerprint and decisions |
| `mode` | Persistent mode |
| `nudge-denied/` | Once-per-session denial markers; filenames derived from session ID SHA-256 |
| `labels.jsonl` | User-provided v1 labels; the last label for an ID wins |
| Claude agent definitions, host transcripts | Pin checks, actual execution and usage; report may reread transcripts, and share scans project transcripts |

New-version prompt, description and task_name records store length and SHA-256, not text. Upstream reason stores presence and digest only. **Logs may still contain sensitive metadata**, including transcript paths, session identifiers and older records. Historical v1 report snippets can be read temporarily from transcripts with long tokens masked; masking is not a complete sanitization guarantee.

New audit directories and the main log request 0700 / 0600 permissions respectively. This does not repair existing permissions or give every state file the same permissions. No automatic rotation or retention period is configured; users manage backup and cleanup.

Hook exceptions attempt to allow execution and record fallback; an unwritable directory may prevent logging. Catalog-default off and mode-file off still need working Python/configuration parsing to be recognized, whereas environment `TIER_GUARD_MODE=off` has a shell fast exit. Allowing execution on error does not guarantee an error log.

## 6. Diagnosis and acceptance steps

1. Inspect the plugin inventory: installed state, enabled state, version, path and new-session loading.
2. Use state / doctor for the data directory and mode source; check configuration differences if using a custom catalog.
3. When auditing is desired, set audit and dispatch natively through the host; compare logs before and after.
4. Check `routing_version`, event, `requested`, `decision`, `catalog_identity` and `applied`; also check Codex `task_visibility`.
5. To prove the actual model, inspect host receipts or transcripts. A Claude alias resolving to a different concrete model is not necessarily a routing error; missing data does not mean zero usage.

Codex CLI `/hooks` reviews trust; doctor cannot prove it. Verify Desktop using native dispatch, not a collaboration API that bypasses the host hook. See [compatibility](compatibility.en.md) for the empty-log report mode limitation.

## 7. Temporary auto experiments

Only for a controlled Claude Code experiment explicitly chosen by the user. It consumes model usage and may emit rewritten dispatch parameters:

```bash
TIER_GUARD_MODE=auto claude
```

After starting, use `/tier-guard:tier-mode` to verify the environment source. The command prefix affects that process only; after exit, a newly started Claude uses its normal environment and persistent mode. It does not persist auto, override pins or enable automatic Codex routing. Do not have the agent run this example on its own after a mode-command refusal.
