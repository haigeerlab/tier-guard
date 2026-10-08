# Development, contributions and feedback

[中文](contributing.md) | [English](contributing.en.md) · [Back to README](../README.en.md)

## 1. Development setup

Clone the repository and prepare Git, python3 and `/bin/bash`. No third-party Python packages or jq are needed:

```bash
git clone https://github.com/haigeerlab/tier-guard.git
cd tier-guard
/bin/bash scripts/validate.sh
```

Use a separate contribution branch, for example `codex/docs-bilingual`. Read [CLAUDE.md](../CLAUDE.md), the [spec](../spec/tier-guard.md), [module plan](../tasks/tier-guard/plan.md) and [task list](../tasks/tier-guard/todo.md) first. These are maintainer/agent contracts, primarily in Chinese; current user entry points and this guide also have English versions.

## 2. Implementation structure and constraints

- `hooks/route_decide.py` owns the decision rules. Claude / Codex adapters and reports reuse the core rather than duplicating policy.
- `config/routing.catalog.v2.json` is current; `routing.default.json` serves historical v1 and migration tests.
- `commands/` contains Claude commands; `skills/` contains pre-dispatch instructions. Names and versions must match in both plugin manifests.
- Use `/bin/bash` and retain macOS 3.2 compatibility. Use `${VAR}` before multibyte characters. Do not introduce `cmd | grep -q`, `sed -i`, `timeout` or a hard jq dependency.
- Keep changes tied to the request. Runtime must not depend on `.agent/state.json` or other plugins' private files.
- Do not write task text, raw descriptions, failure logs or credentials into audits. Consider disclosure when reports reread historical transcripts.

## 3. Validation

Full free regression is the delivery check for every change:

```bash
/bin/bash scripts/validate.sh
```

Focused entry points:

```bash
python3 -B hooks/route_decide.py --selftest
python3 -B hooks/test-route-contract.py
/bin/bash hooks/test-tier-guard.sh
/bin/bash hooks/test-tier-guard-codex.sh
/bin/bash hooks/test-tier-commands.sh
/bin/bash hooks/test-tier-doctor.sh
/bin/bash hooks/test-tier-observe.sh
/bin/bash scripts/test-checkers.sh
```

New check scripts need positive and negative checker tests. For hook or assertion changes, verify mutation anchors and run relevant mutations. Full mutation testing is slower and not included in validate:

```bash
python3 -B scripts/check-mutation-anchors.py
python3 scripts/mutation-check.py
```

Documentation changes need both languages, relative links, commands, defaults and host differences checked. Do not rewrite historical experiment numbers to match current code.

## 4. Real-host verification and permissions

Real CLI / Desktop dispatch may write host configuration or transcripts and consume model usage; obtain authorization for those actions first. Paid host dispatch does not replace free regression. The real Codex pre-routing script runs in an interactive Terminal/TUI and preserves isolated directories and receipts:

```bash
/bin/bash scripts/codex-cli-preroute-smoke.sh
```

It starts a real host, uses an account and writes host session data. It requires Codex, Git, python3, an interactive terminal and a host-readable thread database. Read the script first. An ordinary collaboration API is not native-hook acceptance evidence; historical noninteractive exec failures do not establish the same limitation in every newer version. The full mutation suite uses subprocess interfaces introduced in Python 3.7.

Follow project confirmation rules before committing, pushing, releasing, writing under user `~/.claude` / `~/.codex`, enabling auto, changing host gates or denial behavior. `scripts/install-git-hooks.sh` installs a local pre-push hook and also requires confirmation.

## 5. Contributions and feedback

Use [Issues](https://github.com/haigeerlab/tier-guard/issues) for reports and suggestions, and [Pull Requests](https://github.com/haigeerlab/tier-guard/pulls) for changes. Check existing discussions first. A PR should describe the concrete problem, resulting behavior, validation and hosts that remain unverified.

Useful report details:

- Plugin version, host name/version and operating system.
- Effective mode and source, default/custom catalog, and whether relevant environment overrides exist.
- Minimal sanitized reproduction, expected/actual results and whether dispatch was native.
- Shareable event fields or test output, with credentials, account details, session IDs, personal paths and task text removed.

Do not upload raw logs, transcripts or a complete environment-variable listing. For sensitive reports, start with a description without sensitive information and agree on a suitable channel with maintainers. This repository does not declare a dedicated security email address.

## 6. Documentation and license

Chinese user documentation is the baseline; English keeps matching structure, parameters and limitations. New behavior should update README, reference, compatibility and CHANGELOG. Repository skill and command instructions remain authoritative. Preserve dated research and tested versions, and use navigation to explain subsequent changes.

Contributions follow the project's [Apache License 2.0](../LICENSE); consult the full license for its terms.
