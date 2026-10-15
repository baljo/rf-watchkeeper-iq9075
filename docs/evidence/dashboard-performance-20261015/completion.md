# Dashboard validation performance fix — 15 October 2026

Implemented, tested, deployed and production-active. Final dashboard restart at approximately 20:09:48 UTC / 23:09:48 Helsinki. No RF service restart was performed by this task. Reboot, rendered browser confirmation and long unattended operation remain unverified.

## Cause and changes

At diagnosis there were 1,484 validation records, ten occupied review slots and 808 eligible candidates. A read-only reproduction spent 22.19 seconds on 8,080 unnecessary text comparisons. Live overlapping requests took 218–275 seconds. Full queue selection now exits before comparisons; newly changed jobs are still indexed using existing discovery logic. Validation GETs share one serialized ten-second response under a lock and successful review saves invalidate it. The browser's initial/periodic requests share one pending-request guard and 15-second timeout. No review/retention/scoring rules changed.

## Verification

- `python3 -B -m unittest -v test_validation_capacity`: four passed, including zero full-queue comparisons and unchanged rows, selection into an available slot then stop, duplicates excluded, concurrent single snapshot and save invalidation.
- `python3 -B -m unittest -q test_atis_shadow test_tower_review_policy`: 16 passed. Injected failure messages were expected regression fixtures; final result OK.
- Node parsed every inline script and tested that concurrent validation calls skip, then release the guard after success and failure.
- Post-restart sequential/warm concurrent HTTP results: verification.json. All 200; review-record digest unchanged.
- Cold concurrent test: cold-concurrent.json. All six requests 200 and within their applicable frontend timeouts.
- Service restart loads persisted source; dashboard and scheduler both active afterward. Original human review fields (ID/state/reference/revision/hold) digest unchanged.
- Existing tab must reload for new frontend guard. No browser UI was used to claim rendering or user-session reconnection.

## Rollback

On EVK copy `atis_validation.py`, `dashboard.py`, and `dashboard.html` from `/root/rf-watchkeeper/backups/dashboard-performance-20261015/` to `/root/rf-watchkeeper/`, then `systemctl restart rf-watchkeeper-dashboard.service`. Backup includes pre-task source. Exact patches and hashes are retained here. No database rollback needed; no schema migration.

## Completion audit

Live state inspected; exact patches/backups retained; regression and HTTP evidence saved; dated project log and current status/dashboard/architecture/operations updated; privacy review applied (public frontend retains approximate observer coordinates); unrelated production decisions preserved; restart persistence verified. Reboot and unattended persistence explicitly unverified. Local commit e8b883f records the implementation. Thomas explicitly approved GitHub publication and reaffirmed standing authorization to keep baljo/rf-watchkeeper-iq9075 updated on 15 October 2026. The earlier approval block is resolved; standing authorization is recorded in docs/workflow.md. Exact patch files retain whitespace-only context lines; diff whitespace warnings for those evidence files do not indicate whitespace errors in changed source. Dashboard active since 20:09:50 UTC; scheduler active continuously since 19:48:34 UTC. Subsequent ATIS and AIS completions observed through 20:11:41 UTC.
