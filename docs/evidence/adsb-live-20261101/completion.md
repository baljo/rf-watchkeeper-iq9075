# ADS-B Live completion check — 1 November 2026

Implemented/tested/deployed/production-active: yes. Unattended full-session
completion: pending scheduled expiry. Reboot: intentionally not exercised.

Standing workflow gates:
1. Live EVK/source/services/data inspected before changes: passed.
2. Exact changes preserved by Git patch; private originals/deployment identity
   evidence at adsb-session/private/monitor-deployment-20261101/: passed.
3. Tests: `python3 -m unittest discover -s adsb-session -v` (7 passed);
   `python3 -m unittest -v test_dashboard_state_isolation test_audio_catalog_cache
   test_validation_capacity test_rf_health test_ais_validation
   test_acquisition_control` (25 passed). Existing tests emitted nonfatal
   ResourceWarnings. Windows fixture execution failed due temporary-file rename
   restrictions; target Linux execution passed. Python 3.12 unavailable locally.
4. Dated project log: appended.
5. Current status, architecture and ADS-B operations: appended.
6. Private backup and UI/observer-only rollback: documented.
7. Production-active distinguished from unattended-verified: yes.
8. Observer restart and persisted aggregate cursor: verified live; dashboard
   restarted independently. Capture/watchdog restart and host reboot skipped
   to preserve reservation; remain unverified by this task.
9. Live observations at 19:19 UTC: two session aircraft, valid frames, sample
   progress, zero drops, two aircraft with decoded positions, fresh health,
   active watchdog, scheduler intentionally inactive. No coverage claim.
10. No receiver coordinates, aircraft identities, trails, logs or private DB
    in public evidence. Existing live private HTML differs from public regional
    defaults; preserved on EVK. API omits coordinates.
11. Existing retention/RF/ASR decisions: preserved.

Isolation: dashboard has separate cgroup, empty PartOf/BindsTo/ConsistsOf/
PropagatesStopTo; reverse dependencies are boot targets only. Before/after
capture PID 214787, start ticks 3073111, attempt 3 and decoder container identity
were equal. Expiry 1793602845.977125 unchanged. Capture was uninterrupted.
Observer alone was restarted after a resource cleanup; aggregate state resumed.
HTTP `/`, `/adsb`, `/api/adsb` returned 200. Private SQLite/lease/log routes
returned 404. Browser rendered session metrics, aircraft table and Helsinki
09:00:45 stop time, then updated automatically without reload.

No external notification was installed. Local private reports plus dashboard
are the unattended reporting path. Real expiry/restoration/report execution
will occur after this deployment verification; fixture success is not proof
of the future 12-hour outcome. Current exact patch is in changes.patch.
