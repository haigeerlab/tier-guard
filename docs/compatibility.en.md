# Current compatibility and known limitations

[中文](compatibility.md) | [English](compatibility.en.md) · [Back to README](../README.en.md)

Checked on 2026-10-08 against source version 0.2.7. Production defaults to `off`. Claude's `pre_dispatch_apply` and `dispatch_nudge` are true; both Codex gates are false. Results apply only to the listed versions, protocols and configurations, not every newer release.

## 1. Host capabilities

| Host | Existing evidence | Production limits |
|---|---|---|
| Claude Code CLI | Visible tasks, pins and a controlled Haiku auto receipt on 2.1.269; reminder evaluation on 2.1.270; three-tier and environment-pin checks on 2026-10-05 | Default off; guard / audit do not rewrite; persistent auto rejected; host resolves aliases |
| Codex CLI | Native auditing and explicit main-agent pre-routing on 0.154.0; new-catalog dispatch and record-field checks on 0.160.0 | Native tasks arrive as opaque_token; the main agent selects through the skill; hooks do not independently classify, rewrite, remind or deny |
| Codex Desktop | Historical three-tier main-agent pre-routing and native auditing on 26.908.40834 / 0.154.0-alpha.6.2 | Old models prove the mechanism only; production hook rewriting is unproven and gates remain closed |
| Claude Code Cloud | No repository evidence of real v2 subagent dispatch | CLI results are not extrapolated |
| Native Windows shell | Not verified by this repository | Hooks require `/bin/bash`; direct support is not claimed |

This review checked installation, update and uninstall interfaces with local `--help` from Claude Code 2.1.291 and Codex CLI 0.160.0, without rerunning real host dispatch. macOS Bash 3.2 is the repository regression environment; other Unix environments need host and shell verification.

The report always reads the current mode from the current configuration, even with empty or v1-only logs. The default is `off`; environment overrides and valid persistent modes retain their precedence. The v1 gate explains historical data only and does not permit current v2 auto mode.

## 2. Known limitations

- **Custom catalogs are not propagated:** hooks read `TIER_GUARD_CONFIG`; state, doctor and report accept explicit `--config`. Without it, diagnostics read plugin defaults; they do not automatically read the hook configuration environment variable. See [configuration precedence](reference.en.md#3-configuration-sources-and-precedence).
- **Skill execution varies:** installation does not ensure loading on every natural dispatch. Explicit parameters are pins, so hooks do not correct a main agent's poor tier choice.
- **Execution and usage gaps:** Claude depends on host transcripts, which report tries to reread. Codex auditing records dispatch parameters only, not proof of actual models or total cost.
- **Error logging is not guaranteed:** configuration, interpreter and permission failures attempt to allow execution; if logs cannot be written, there may be no fallback record.
- **Costs are not live billing:** catalog rankings do not query current pricing. Experiment pass rates and economic conclusions do not apply to every task or account.

## 3. Verification evidence

- [Controlled Claude CLI v2 auto](research/2026-09-13-claude-cli-v2-smoke.md)
- [Claude end-to-end checks and subsequent fixes](research/2026-09-13-claude-cli-v2-e2e.md)
- [Reminder and guard reevaluation](research/2026-09-13-dispatch-nudge-e2e.md)
- [Controlled Codex CLI v2 rewriting and main-agent pre-routing](research/2026-09-12-task7-codex-cli-v2-smoke.md)
- [Historical Desktop native dispatch](research/2026-09-12-codex-desktop-native-smoke.md)
- [2026-10-05 catalog and host rechecks](research/2026-10-05-catalog-rehost-verification.md)
- [Codex L2 Luna task experiment](research/2026-10-05-codex-l2-luna-experiment.md)

An older controlled Codex CLI snapshot accepted updatedInput, proving a parameter mechanism. It did not solve opaque task input and does not authorize production automatic routing. Upstream context: [OpenAI Codex #33284](https://github.com/openai/codex/issues/33284).

## 4. Evidence required for support claims

Main-agent pre-routing requires explicit dispatch parameters and a real child receipt. Hook automatic routing requires pre-dispatch auditing, `applied=true`, selected parameters and an actual execution receipt together. Installation, offline tests, Spawned text or after-the-fact logs alone are insufficient. New host support should be designed first, tested with isolated configuration, then reviewed before changing capability gates.
