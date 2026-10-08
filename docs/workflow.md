# Engineering workflow

1. The EVK working tree at `/root/rf-watchkeeper` is the operational source of truth.
2. Every substantial future Work-mode implementation task must append a dated entry to [project-log.md](project-log.md) before the task is considered complete.
3. Documentation describes verified current behavior, not assumptions from chat history. Inspect source, configuration, service state, retained records and test output; identify dates, evidence and uncertainty.
4. If Git metadata is unavailable on the EVK, save exact patches and regression/test artifacts for significant changes, as done for the [METEOR crash fix](evidence/meteor-satdump-crash.patch). Keep them in the project and link them from its engineering entry. No usable `.git` metadata or Git executable was found on 2026-10-05.
5. Do not silently rewrite historical entries. Append corrections or later findings when understanding changes.

Keep useful existing guides; add current-status notes and cross-links rather than competing copies. A historical guide's installation defaults are not necessarily the current runtime configuration.

Each concise log entry records date/time (with timezone), change, reason, important files, affected services/components, configuration/behavior, validation, result and remaining issues. Mark unknown times explicitly; a backup timestamp is evidence of a snapshot, not proof of the exact deployment time.

Suggested entry:

```text
### YYYY-MM-DD HH:MM UTC — change
- Change/reason:
- Files/components:
- Configuration/behavior:
- Validation/evidence:
- Result/follow-up:
```

## Canonical public repository

Use [baljo/rf-watchkeeper-iq9075](https://github.com/baljo/rf-watchkeeper-iq9075) for public source/documentation. The initial publication imports the preserved EVK implementation through a local Git checkout; it does not create Git metadata on the live EVK or make GitHub contain recordings/models/databases. Preserve source history/evidence on the EVK, reconcile subsequent operational edits before public commits, and review explicit staged paths and secret/large-file checks. Current public topics summarize stable behavior; dated log entries and original guides remain historical evidence.


## Standing Work rule — definition of done (8 October 2026)

Applies to EVERY RF Watchkeeper engineering task. Documentation and evidence are required completion work. If any applicable step is missing, the task is NOT complete; mark the outstanding gate explicitly.

1. Inspect the actual live EVK state; never infer deployment from a patch.
2. Save exact code/configuration changes or patches in project evidence/history.
3. Record exact tests, commands, results, failures and skips.
4. Append a dated shared project-log entry stating what changed, why, what was verified, what remains unverified, and temporary state or operational restrictions.
5. Update current status, architecture and operations documentation whenever behavior, configuration, thresholds, scheduling, services, retention, resource use, dashboard behavior or processing flow changes.
6. Record rollback information for changes to production behavior.
7. Distinguish implemented, tested, deployed, production-active and unattended-verified. Never collapse these into “fixed.” State whether a running path is production or shadow/candidate.
8. Verify persistence across service restart/reboot, or explicitly state which persistence checks remain unverified. Do not disrupt an active reservation merely to close a gate.
9. Read live datasets and shared records for current counts/statistics. Date frozen evidence; never reuse historical counts as current.
10. Never publish precise home coordinates or private location information in GitHub/project documentation; use only the approximate Vaasa/Korsholm region in public material.
11. Preserve current decisions unless Thomas explicitly changes them: Tower ASR deferred because current audio is too poor for useful transcription; Tower recordings retained 30 days with pinned references protected; METEOR failed/unverified raw captures not automatically deleted; production and shadow/candidate paths clearly identified.

An explicitly documented unverified persistence check is permitted by item 8, but it is not a passing restart/reboot test. Report outstanding operational validation separately from completed documentation repair.

## Mandatory session entry and completion check — 8 October 2026

Every future Work session touching RF Watchkeeper must read repository-root AGENTS.md and this workflow before making changes, regardless of what the prompt repeats. At completion, check every applicable standing rule and save the check with the evidence. Inspect current state before changing it; preserve/back up relevant files before edits; implement and test the change. Save code/configuration diffs, exact tests/results and appropriate evidence. Append a dated project log and update relevant technical/current-status/operations documents when behavior changes. Document temporary states, restrictions and unfinished verification, and production rollback. Distinguish implemented / tested / deployed / production-active / unattended-verified individually.

Commit and push code/documentation to the canonical GitHub repository when the normal project workflow calls for publication: use a local Git checkout when the EVK has no Git, reconcile operational edits, stage explicit paths, inspect the diff, and check secrets/private locations and generated/large files. Lack of Git on the EVK alone is not a reason to omit publication. Keep private live evidence and backups on the EVK and publish a sanitized report. Read live counts and date them as observations. Never expose precise home coordinates or private location information, including in tests, SVG metadata, diffs or evidence.
