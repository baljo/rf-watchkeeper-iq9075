# Tower AD-scored review queue — 9 October 2026

Implemented, tested, deployed and active on EVK. The optional queue shows the latest 20 unreviewed AD-scored Tower candidates, newest first. A successful atomic shadow result must provide a positive summary.count, finite numeric summary.p100 and threshold, mode shadow_only and no pending/failure status. Booleans, numeric strings, NaN and infinity fail closed. Existing voice_candidate/uncertain/anomaly_candidate criteria still apply. Ordinary recent history and authoritative human labels remain available. Scoring is shadow evidence, not a validated speech probability.

Live SQLite schema inspected read-only: audio_recordings has no anomaly-score/review columns. Actual score evidence is evaluation/tower-anomaly/shadow/<capture>.json; labels are evaluation/tower-anomaly/human-review/<capture>.json. No guessed database-field filter was used.

Live API matched an independent retained-record scan: 20 eligible scored unreviewed items, newest first; compatibility alias and inclusive history verified. Both 9 October 2026 Helsinki examples 10:14:52 and 10:13:50 lacked completed scores and were excluded. Newest queued scored capture at initial verification was 09:11:44 Helsinki. Authenticated dashboard HTTP fixture test saves a label, excludes it, refills with the next scored candidate and preserves reviewed history; no fabricated labels were saved to the real dataset.

Nine final targeted tests passed (queue, score validity, human review and cumulative validation). Review fixture updated to include actual summary.count. Broader original run had two legacy history-status assertions and one invalid-WAV retention EOFError; all three reproduced against the pre-change baseline. Two attempted unavailable suites were recorded as import errors and excluded from the final targeted run. No production tests were weakened. Full logs remain in EVK evidence.

Only dashboard restarted. RF scheduler, interpreter and ATIS worker PIDs unchanged; retention/classification/scheduler/scoring/review/configuration hashes and human-label/model hashes unchanged at verification. 30-day retention, permanent pins, training/reference records, production thresholds and RF scheduling preserved. Subsequent live observation records continued capture progress. Restart persistence verified; reboot and long unattended operation unverified.

Rollback: restore atis_view.py and dashboard.html from docs/evidence/tower-scored-queue-20261009/backup and restart only rf-watchkeeper-dashboard.

Exact operational patch and test suite preserved. Canonical checkout is older than live operational baseline, so publication uses an exact baseline-specific patch rather than replacing unrelated canonical code. Precise location information omitted. Completion check: live inspection, schema/data verification, backups, patch, tests, deployment, active API, restart, protected services/data, shared docs/log and rollback complete; reboot/unattended duration not verified. Source-control reference is reported separately.

### 2026-10-09 — Approved AD-scored Tower queue publication

Thomas explicitly approved publication to the canonical repository's main branch. Published fix: [cda4169](https://github.com/baljo/rf-watchkeeper-iq9075/commit/cda41692e0786d2cf94eb3f590ba74834fe7d74e). The remote main reference was verified after push. This supersedes the earlier pending-publication gate. Newer canonical commits were preserved; the fix was reapplied in an isolated checkout, with no force push and no alteration of unrelated local work. EVK deployment and validation remain as documented in [the scored queue report](tower-scored-queue-20261009.md); no additional deployment or service restart was necessary.

