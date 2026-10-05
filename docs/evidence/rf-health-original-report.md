# RF Watchkeeper watchdog implementation and verification

Installed on iq-9075-evk, root@100.116.155.87, in /root/rf-watchkeeper. Latest saved live verification: 05 Oct 2026 14:56:04 EEST.

The watchdog is enabled and running. V4MAIN01 is GREEN after today's M2-4 recording completed successfully. It was correctly classified BUSY during the recording, with recovery suppressed throughout the satellite reservation. The intentionally disconnected 43300001 is DISABLED. Recent real receiver failures: 0.

## Capture health and recovery

- Shared receiver reports require real sample evidence and acceptable completion, independently of decoded traffic. AIS with zero messages is healthy when sample DSP processing occurred and the scheduled run ended normally.
- FM and Tower count actual PCM bytes while retaining the existing playback/recording pipeline. ATIS reports recorded PCM samples. METEOR capture and its existing preflight report IQ bytes. The gain diagnostic also reports native AIS sample processing.
- AIS gets a native bounded runtime, an outer dwell + 20-second deadline, process-group cleanup, and a reader that cannot hang on an incomplete output line. Existing FM/AM/ATIS time bounds are retained; the monitor also checks overdue recorded job deadlines.
- A stale idle receiver gets a direct eight-second maximum probe using V4MAIN01, 256000 IQ samples, and exactly 512000 varied IQ bytes. Temporary files are removed. USB enumeration alone is insufficient.
- Recovery stages inspect stale owners, preserve unknown/continuous owners, retry acquisition, skip unavailable targeted USB recovery, restart the scheduler cleanly, and retry acquisition before considering a reboot.
- No safe V4-only USB reset mechanism was found. No generic USB/hub reset was introduced; the configured USB hook remains null.
- Automatic reboots are transactionally limited to one per hour in persistent SQLite state, shared with existing METEOR reboot recovery. Watchdog reboots are suppressed during satellite reservations and inside seven minutes before recording. Existing per-pass reboot reservations and post-boot resume remain in place.
- A shared control lock serializes recovery and METEOR receiver reservation. If the health service is interrupted after pausing the scheduler, its stop hook restores ordinary operation when satellite ownership allows.
- Boot ordering follows filesystem and time synchronization, the scheduler and existing METEOR boot recovery. A new boot requires fresh sample acquisition evidence. No actual reboot was performed for testing.

## Units and configuration

New units, also copied to /etc/systemd/system:

- /root/rf-watchkeeper/rf-watchkeeper-health.service
- /root/rf-watchkeeper/rf-watchkeeper-health.timer

The timer is enabled and active; it checks every five minutes and starts two minutes after boot. The last health service result is success with exit status 0. Scheduler restoration is provided by ExecStopPost.

Configuration: /root/rf-watchkeeper/rf-health-config.json. V4MAIN01 is enabled/required; 43300001 is disabled. Thresholds: GREEN under 15 minutes, YELLOW 15–30 minutes, RED over 30 minutes. Legitimate busy jobs are protected. Stale idle activity is tested directly instead of generating an alarm merely because no job was scheduled. Current automatic recovery targets the primary V4; integrating a reconnected required second receiver needs its scheduler/backend added before enabling its recovery.

The early METEOR readiness probe runs in the 10–15 minute lead window without changing pass times. For today's M2-4 recording it succeeded at 14:28:08 EEST, approximately 13½ minutes before recording. The existing capture preflight then succeeded at 14:39:59 EEST.

## Database

The application's actual database is /root/rf-watchkeeper/data/watchkeeper.db. The root-level watchkeeper.db is an empty legacy file and was left untouched.

Four additive tables were created:

| Table | Purpose |
|---|---|
| rf_health_jobs | Serial, job, start/end, deadline, PID/boot ID, capture_ok, sample evidence, exit code, failure reason, separate application result |
| rf_health_events | Timestamp, serial, action, recovery result/detail and boot ID |
| rf_health_state | Latest monitor classification and detail |
| rf_health_reboot_guard | Durable atomic hourly reboot guard |

An indexed receiver/completion-time lookup and additive boot-ID migration are included. All pre-existing table definitions are unchanged. SQLite quick_check returns ok. Original data was backed up before migration. Intentionally interrupted ordinary jobs are recorded as cancelled rather than receiver failures.

One initial run of the older METEOR tests wrote simulated entries into the newly added health tables. Those entries were retained under TEST-SIMULATION, its mock-created reboot guard was cleared, and the regression fixture was corrected to use a temporary health database per test. Subsequent tests do not affect production receiver state. No real reboot occurred, and no historical satellite records were changed by this correction.

## Verification

58 tests pass: 11 new watchdog safety tests, 5 existing AIS tests, and 42 existing METEOR recovery/history tests.

The tests cover zero-message reception, a partial output line, sample-less failure, hard AIS timeout and process-group cleanup, controlled stale-owner termination, protection of valid/unknown owners, protection of active satellite work, escalating recovery with reboot rate limiting, durable hourly guard, and restoring the scheduler after interrupted recovery. They use temporary health databases and dummy processes.

Live checks confirmed:

- Timer enabled/active; health service exits successfully.
- Direct V4 sample probe: exit 0, 512000 valid IQ bytes.
- FM, Tower, AIS and ATIS all produced successful real capture reports.
- AIS still completes its normal 120-second jobs and records sample DSP evidence separately from decoded ships.
- Dashboard renders receiver health, with zero browser errors, and shows disabled 43300001 in a neutral style.
- During real METEOR recording the health service exited successfully, reported BUSY and performed no recovery actions. The recorder PID remained 92709 and rtl_sdr PID 93192; IQ size grew from 32243712 to 93847552 bytes across verification snapshots.
- The full M2-4 recording completed at 14:55:23 EEST with 419954688 IQ bytes, exit code 0 and capture_ok=1. The existing capture architecture restarted the ordinary scheduler, which then completed a successful FM reference capture at 14:55:59 EEST. The health service returned success and the receiver returned to GREEN.
- All original satellite unit files match their saved hashes. All persisted planned pass times, device, gain, frequency and sample rates match the pre-installation snapshot. Future sample rates remain 256000.

Testing limits: no deliberate hardware hang, physical USB reset or real watchdog reboot was induced. Recovery/reboot decisions were tested safely with controlled processes and mocked commands. Today's RF capture and scheduler restoration were observed; satellite image decoding is outside this watchdog verification.

## Scheduled METEOR recordings

The original METEOR dispatcher, planner, processing and cleanup timers remain intact. Managed passes are launched by the existing dispatcher; no new per-pass timers were substituted.

| Satellite | Recording starts | Recording stops | Sample rate | State at verification |
|---|---|---|---:|---|
| M2-4 | 05 Oct 2026 14:41:42 EEST | 05 Oct 2026 14:55:24 EEST | 256000 | attempted |
| M2-3 | 05 Oct 2026 21:27:23 EEST | 05 Oct 2026 21:41:08 EEST | 256000 | planned |
| M2-4 | 06 Oct 2026 04:26:50 EEST | 06 Oct 2026 04:40:04 EEST | 256000 | planned |
| M2-3 | 06 Oct 2026 11:11:37 EEST | 06 Oct 2026 11:25:11 EEST | 256000 | planned |
| M2-4 | 06 Oct 2026 16:00:29 EEST | 06 Oct 2026 16:13:51 EEST | 256000 | planned |
| M2-3 | 06 Oct 2026 21:04:12 EEST | 06 Oct 2026 21:17:51 EEST | 256000 | planned |

Original timer snapshot:

```text
Mon 2026-10-05 11:56:08 UTC       3s Mon 2026-10-05 11:55:37 UTC      26s ago rf-watchkeeper-meteor-dispatch.timer        rf-watchkeeper-meteor-dispatch.service
Mon 2026-10-05 11:56:21 UTC      16s Mon 2026-10-05 11:55:21 UTC      43s ago rf-watchkeeper-meteor-legacy-register.timer rf-watchkeeper-meteor-legacy-register.service
Mon 2026-10-05 11:57:41 UTC 1min 36s Mon 2026-10-05 11:52:41 UTC 3min 23s ago rf-watchkeeper-meteor-process.timer         rf-watchkeeper-meteor-process.service
Mon 2026-10-05 12:00:00 UTC 3min 55s Mon 2026-10-05 11:00:00 UTC    56min ago rf-watchkeeper-meteor-plan.timer            rf-watchkeeper-meteor-plan.service
Mon 2026-10-05 12:01:04 UTC 4min 59s Mon 2026-10-05 11:52:51 UTC 3min 13s ago rf-watchkeeper-health.timer                 rf-watchkeeper-health.service
Tue 2026-10-06 02:00:00 UTC      14h Mon 2026-10-05 02:00:00 UTC       9h ago rf-watchkeeper-meteor-cleanup.timer         rf-watchkeeper-meteor-cleanup.service
```

## Files changed

New files:

- /root/rf-watchkeeper/rf_health.py
- /root/rf-watchkeeper/rf_health_monitor.py
- /root/rf-watchkeeper/rf_sample_relay.py
- /root/rf-watchkeeper/rf-health-config.json
- /root/rf-watchkeeper/rf-watchkeeper-health.service
- /root/rf-watchkeeper/rf-watchkeeper-health.timer
- /root/rf-watchkeeper/test_rf_health.py
- /root/rf-watchkeeper/RF_HEALTH.md
- /root/rf-watchkeeper/collect_verification.py

Modified existing files:

- /root/rf-watchkeeper/job_manager.py
- /root/rf-watchkeeper/ais_collector.py
- /root/rf-watchkeeper/atis_pipeline.py
- /root/rf-watchkeeper/satellite_capture.py
- /root/rf-watchkeeper/meteor_recovery.py
- /root/rf-watchkeeper/dashboard.py
- /root/rf-watchkeeper/dashboard.html
- /root/rf-watchkeeper/satellite_v4_preflight.sh
- /root/rf-watchkeeper/run_ais_gain_test.sh
- /root/rf-watchkeeper/test_meteor_recovery.py
- /root/sdr_demo/scheduler.py

The shared audio scheduler change adds sample counting while preserving commands, gain, recording and audio playback. Service unit files are also installed in /etc/systemd/system.

Source/database/plan backups: /root/rf-watchkeeper/backups/rf-health-20261005T112419Z. Additional rf-health backup directories contain later refinements. No unrelated source was overwritten: the initial installer compared original hashes before editing and refused changed files.

## Version control

The EVK application directory has no .git metadata and no Git executable. Therefore remote git status and git diff --stat are unavailable; no commit or push was made. An equivalent before/after comparison was generated with local Git using --no-index; it compares saved originals against final source, not an EVK repository.

```text
 .../rf-watchkeeper/RF_HEALTH.md"                   |  39 ++++
 .../rf-watchkeeper/ais_collector.py"               |  72 ++++--
 .../rf-watchkeeper/atis_pipeline.py"               |   6 +
 .../rf-watchkeeper/collect_verification.py"        |  49 ++++
 .../rf-watchkeeper/dashboard.html"                 |  21 +-
 .../rf-watchkeeper/dashboard.py"                   |  17 +-
 .../rf-watchkeeper/job_manager.py"                 |  42 +++-
 .../rf-watchkeeper/meteor_recovery.py"             |   5 +
 .../rf-watchkeeper/rf-health-config.json"          |  13 ++
 .../rf-watchkeeper/rf-watchkeeper-health.service"  |  14 ++
 .../rf-watchkeeper/rf-watchkeeper-health.timer"    |  11 +
 .../rf-watchkeeper/rf_health.py"                   | 203 ++++++++++++++++
 .../rf-watchkeeper/rf_health_monitor.py"           | 256 +++++++++++++++++++++
 .../rf-watchkeeper/rf_sample_relay.py"             |  23 ++
 .../rf-watchkeeper/run_ais_gain_test.sh"           |  49 +++-
 .../rf-watchkeeper/satellite_capture.py"           |  29 ++-
 .../rf-watchkeeper/satellite_v4_preflight.sh"      |  94 +-------
 .../rf-watchkeeper/test_meteor_recovery.py"        |   8 +
 .../rf-watchkeeper/test_rf_health.py"              | 189 +++++++++++++++
 .../sdr_demo/scheduler.py"                         |  34 ++-
 20 files changed, 1047 insertions(+), 127 deletions(-)
```

Deliverables: rf-watchkeeper-health.patch (reviewable source patch), rf-watchkeeper-health-changes.zip (20 final files), rf-health-verification.json (live evidence), rf-health-dashboard.png (verified live UI), RF_HEALTH.md (operation notes).
