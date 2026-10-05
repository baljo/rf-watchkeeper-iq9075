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
