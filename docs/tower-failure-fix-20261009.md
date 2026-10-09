# Tower/AD queue failure completion audit — 9 October 2026

Verification: 09:38:05–09:39:26 Europe/Helsinki (06:38:05–06:39:26 UTC).

## Problem, cause and installed behavior

Zero-frame recordings repeatedly reached inference and blocked later items. The automatic Tower anomaly **shadow diagnostic** worker lacked durable terminal failure handling. Production capture and the production recognizer are separate paths.

The deployed worker validates completed audio before inference, including when resources are busy. Missing, empty, zero-frame, corrupt/truncated, unsupported, oversized and too-short audio becomes `unscorable`. Persistent failure JSON excludes terminal items from pending. Inference/start/I/O failures use 60/120/240/480-second exponential backoff and become `failed_terminal/retry_exhausted` on failure five. Resource preemption has a 60-second cooldown and consumes no audio-failure attempts. Batches continue past item failures; global resource deferral stops inference. Oldest-first ordering and a process lock are used. Unreadable failure state excludes the affected item rather than resetting retries.

## Exact production change and state migration

Only `tower_anomaly_shadow.py` was replaced in the empty-recording fix. Installed SHA256: `8ffb0361b5fdf68bafbe6c965b2bc4248583ae31f5f33f9983d5c3a11566437e`, independently confirmed. Exact backup-to-installed diff: [worker.patch](evidence/tower-failure-fix-20261009/worker.patch). Test artifact: [test_tower_failures.py](../test_tower_failures.py).

Affected automatic units: `rf-watchkeeper-tower-anomaly-shadow.service` and `.timer`. Existing `batch.conf` passes `--batch` and sets TimeoutStartSec=70; timer OnUnitInactiveSec=60s, AccuracySec=5s. Worker bounds are five items and 45 seconds, child limit 15 seconds. CPUQuota=10%, MemoryMax=256M, TasksMax=8, Nice=19, idle I/O and one BLAS/OMP thread remain. No service configuration changed in this fix. This corrects the earlier historical six-item documentation. Original deployment occurred after the 09:17:16 baseline and before the 09:22:42 verification; exact replacement time is not recorded. Only the AD timer was briefly paused for replacement; capture was not stopped.

No SQLite schema/data migration occurred. Additive JSON state under `evaluation/tower-anomaly/shadow/failures/` reclassified 14 retained zero-frame recordings as `zero_frames` and 457 historical missing recordings as `missing_audio`. The latter were already filtered out by the former queue and are not a 457-item backlog reduction. Existing absence is not repaired by this fix. Originals and metadata are never rewritten by the worker.

## Verification and achieved levels

Implemented/validated: YES. `cd <project-root>; PYTHONPATH=. python3 /tmp/test_failures.py` against installed modules: nine tests passed, zero failures/skips, 0.026 seconds. Tests cover permanent missing/zero/corrupt/short failures, truncation, preservation, idempotence, bounded retries, continued batch processing, preflight before inference under contention, preemption budget, successful retry cleanup, corrupt state isolation and output safety.

Deployed and production-active automatic shadow worker: YES. Installed hash matches tested source; timer active; service success result, executing a fresh run at final observation; scheduler/dashboard active. This follow-up changed documentation only on the EVK; no worker reinstallation or service restart.

Unattended verification: YES for the observed short window. Journal since 09:17:16 shows eight later scores, 17 resource-deferred batches and one batch-limit completion by 09:38:05. Terminal count remains 471, no 5 October recording pending. Every existing 5 October audio/metadata hash matches the pre-deployment baseline. Corrupt audio is covered by isolated fixtures, not an invented live corrupt example. Naturally repeated systemd oneshot launches retain terminal state and retry cooldown. Reboot and deliberately forced restart remain unverified; no reboot/restart was performed to close this audit. Long-run throughput acceptance is NOT achieved.

Queue: 92 pending at 09:38:05, 94 at 09:39:26; one capture directory arrived and zero scores completed in that 81-second follow-up. Pending eligibility can change as captures finalize, so capture-directory arrivals do not exactly equal pending changes. At 09:22:42 the earlier report measured 86 pending. Resource-deferral throughput/backlog remains unresolved; short samples are not whole-day capacity estimates. No scheduling/model/threshold/retention/ASR change is part of this task.

## Evidence, recovery and publication

The prior Work-local `tower_failure_fix/README.md` is incorporated as [original verification report](evidence/tower-failure-fix-20261009/original-report.md), with its baseline/final evidence preserved privately in the EVK evaluation directory for this audit. Sanitized current evidence is [verification.json](evidence/tower-failure-fix-20261009/verification.json). Shared project log and Tower operations guide link this audit, so no chat history is needed.

Production rollback backup is `tower_anomaly_shadow.py.bak-failure-fix-20261009` alongside the worker. Pause the AD timer and wait for an active worker before restoring; the old worker ignores terminal failure records and can reintroduce the retry loop. Preserve failure JSON and score files. After repairing an individual audio/inference cause, archive its failure JSON before explicitly clearing that entry to retry. Never clear all terminal state automatically. Previously missing audio cannot be restored by clearing state. No DB rollback is needed.

The repository includes deployed worker/source dependencies, tests, exact sanitized patch and shared docs. Private recordings, metadata, runtime failure JSON, databases, machine-specific service paths and rollback backups intentionally remain EVK-only: privacy, size and operational state. Public documentation uses repository-relative artifact names; location, if needed, is only the approximate Vaasa/Korsholm region.

Completion checklist: live inspection, exact patch, nine-test result, shared dated log, current operations/architecture links, rollback, status distinctions, dated live counts, privacy review and retained decisions are recorded. Persistence across natural worker launches verified; forced restart/reboot explicitly unverified. Commit/push receipt is appended after publication. Remaining operational limitations are throughput/backlog and reboot verification, not hidden completion claims.
