# Implementation Plan: tier-guard v0.1.1 release and real-project acceptance

## Overview

Publish tier-guard as a stable, default-audit `v0.1.1` release, then validate
the released artifact in a fresh public, non-production GitHub project. The release must not
claim that Codex V2 hooks autonomously classify opaque child-task tokens; that
upstream limitation remains explicit.

## Architecture Decisions

- Normalize both plugin manifests to the same SemVer release version, `0.1.1`.
  The existing `+codex.*` value is a local cache-busting snapshot, not the
  public release identity.
- Use the annotated Git tag `v0.1.1` as the immutable source of the published
  artifact and GitHub Release.
- Exercise the released marketplace artifact in `haigeer-labs/tier-guard-e2e`,
  a public disposable GitHub repository containing no secrets or production
  data. Do not treat a developer checkout as
  installation evidence.
- The acceptance report distinguishes verified default-audit behavior and
  parent-agent plaintext pre-routing from the intentionally unavailable Codex
  hook auto-routing behavior.

## Task List

### Phase 1: Release artifact

- [x] Task 1: Normalize manifests and add a curated `CHANGELOG.md` entry.
  - Acceptance: both manifests declare `0.1.1`; the changelog states the
    user-visible capability boundary and upgrade impact.
  - Verification: `scripts/check-manifests.py .` and
    `/bin/bash scripts/validate.sh` pass.

### Checkpoint: Local release gate

- [x] Task 2: Run complete validation, mutation checks, and Git hygiene checks.
  - Acceptance: test suites pass; no secret, whitespace, or manifest drift is
    present; the release commit is reproducible.
  - Verification: `/bin/bash scripts/validate.sh`,
    `python3 scripts/mutation-check.py`, `git diff --check`, and staged-diff
    review pass.

### Phase 2: Publish

- [x] Task 3: Commit the release metadata, create and push annotated tag
  `v0.1.1`, then create a GitHub Release from that tag.
  - Acceptance: the remote branch and tag resolve to the release commit; the
    release notes communicate the audit-default and Codex V2 limitation.
  - Verification: `git ls-remote` and GitHub Release metadata agree on tag and
    commit.

### Phase 3: Released-artifact acceptance

- [x] Task 4: Create the public `haigeer-labs/tier-guard-e2e` repository and
  install tier-guard from the published marketplace source.
  - Acceptance: the installed cache is associated with `v0.1.1`, enabled, and
    its hook paths resolve inside the installed artifact.
  - Verification: `codex plugin list --json` plus installed-manifest and hook
    path inspection.

- [x] Task 5: Run an isolated real Codex TUI acceptance using the installed
  release and collect evidence for three parent-agent plaintext pre-routing
  tiers, audit logs, and pin protection.
  - Acceptance: real child receipts are `luna/medium`, `terra/high`, and
    `terra/xhigh`; audit records preserve opaque-token safety and an explicit
    pin produces no rewrite.
  - Verification: the project's TUI smoke protocol and recorded host evidence
    agree; no raw task text is retained.

### Checkpoint: Report and cleanup

- [x] Task 6: Write the final test report, including environment, cases,
  evidence, verdict, and known upstream limitation.
  - Acceptance: every claimed pass is evidence-backed; unsupported automatic
    Codex-hook routing is marked out of scope rather than passed by inference.
  - Verification: report links to the immutable release and test artifacts;
    the test repository contains no secrets or production data.

## Risks and Mitigations

| Risk | Mitigation |
| --- | --- |
| GitHub organization permission is unavailable | Stop before external creation and report the exact missing authority. |
| Local plugin cache masks a fresh installation | Verify the installed manifest and cache path after adding the published marketplace. |
| Codex TUI cannot be automated reliably | Use the checked-in interactive smoke protocol and label the test blocked, not passed, if receipts cannot be observed. |
| Users mistake audit evidence for automatic routing | State the V2 opaque-token boundary in changelog, release notes, and test verdict. |
