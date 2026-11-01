# ADS-B deployment completion check — 1 November 2026

The 12-hour reception lease is **running**, not yet a completed unattended
12-hour observation. Expiry is 2 November 2026 07:00:45.977 UTC. The final
restoration of this long session remains future work performed by the device.

## Verified evidence

* Live OS, architecture, commands, USB identity and open descriptors were
  inspected using SSH. Prior owner: scheduler `rtl_fm`, V4MAIN01. No second SDR
  was enumerated. Host tools were not used to open an already-owned receiver.
* `systemctl list-units --all`, `list-unit-files`, `list-timers`, unit source,
  health-monitor and METEOR capture paths were inspected. Existing broad
  acquisition suspension was absent. No discovered cron executable was present.
* Existing `debian:bookworm-slim` ran ARM64 with apt-get inside the container.
  Native host gcc/make/cmake/pkg-config/apt/dump1090/readsb were not discovered.
  `docker build -t rf-watchkeeper-adsb:20261101 .` succeeded, with compile/link
  output retained privately in `adsb-session/build.log`. Vendor driver and
  decoder commit IDs, binary hashes, image ID and help output are in provenance.
  Host RTL-SDR library/tools remained unchanged.
* `python3 -m unittest -v test_session`: **3 passed** on EVK. Tests exercise
  every split point of an escaped Beast frame, expired-watchdog dispatch, and
  restoration that never starts previously inactive/disabled receivers.
* Trial `20261101T185708Z`, 45 seconds: caught a Docker proxy/listener startup
  race. Three observed decoder attempts failed when an early TCP connection
  closed. Independent watchdog restored original RF states at 18:58:02 UTC.
  The listener race was corrected with bounded reconnects. It was not a
  successful capture trial; its failure and restoration remain recorded.
* Trial `20261101T185831Z`, 90 seconds: decoder ran and sampled; a deliberate
  `systemctl restart rf-watchkeeper-adsb.service` retained the expiry. Automatic
  capture termination and watchdog restoration completed at 19:00:32 UTC;
  83 aircraft JSON snapshots, zero valid messages/aircraft, SQLite quick_check
  `ok`. The archived before/after unit states show no disabled receiver
  spuriously started. Scheduler and the two previously active conflicting
  timers resumed; inactive one-shots were not explicitly replayed.
* Main lease `20261101T190045Z` launched using `python3 session.py start`
  (default 43200 seconds). A controlled service restart at approximately
  19:02:16 UTC retained the same 07:00:45.977 UTC expiry. Original sampler PID
  was replaced; data remained in the same database and registry. Current
  attempt count is recorded in frozen verification; a manual restart is an
  attempt, not an inferred crash.
  Final source was reloaded at 19:07:28–19:07:31 UTC after moving startup
  failures inside the retry bound and conservatively leaving raw DF18 address
  attribution to the decoder's annotated snapshots. The original expiry
  remained unchanged; the final observation is attempt 3.
* Read-only `systemctl show`, guard-file inspection, `docker port`,
  `timedatectl`, decoder log, sample counters and `PRAGMA quick_check` verified
  the running final path. Sole published container port is loopback 30005.
  All eight observed unrelated dashboard/processing/planning/retention units
  were active. Existing unit enablement was not changed.
* A proposed live scheduler-start guard probe was rejected by automatic
  approval review because it could reclaim the shared receiver. It was not
  executed or bypassed. Guard verification used read-only inspection instead.
  A proposed watchdog-timer restart test was also rejected due to possible
  deadline delay; the running timer was left untouched and audited read-only.

See [verification.json](verification.json) for exact dated states, tests, counts,
source hashes and timer evidence. The audit script reads no aircraft objects
or private observer configuration. Public evidence has no precise coordinates;
actual flight messages/positions and private change logs stay on the EVK.

## Standing workflow completion

1. Actual live device inspected: passed.
2. Exact changes: new session source, Dockerfile, tests and audit saved in Git
   and on EVK; generated unit definitions are reproducible from `install()`.
   Original RF source/configuration/data was not changed. Private lease and
   trial restoration archives record operational changes.
3. Tests/commands/failures/skips: recorded above and in frozen verification.
4. Dated shared project log: appended with temporary state and limitations.
5. Current status, architecture and acquisition operations: appended with links
   to the new session guide; existing historical text retained.
6. Rollback: `python3 adsb-session/session.py restore`, with original states
   archived and verified before lease removal; see guide for later removal.
7. Implemented, tested, deployed and currently active: verified. Full requested
   duration and final main-session restoration are **not yet observed**.
8. Capture service restart persistence: checked without extending expiry.
   Timer restart was not tested. Two automatic trial restorations observed. Reboot/power loss,
   daemon-wide failure, missing USB, disk pressure and long-duration behavior
   were not induced. The absolute deadline/boot guard and independent timer
   are installed; this is not a passing reboot or 12-hour endurance claim.
9. Current counts: frozen from live database/health, initially zero aircraft.
10. Privacy: source/evidence reviewed before staging; private folder ignored;
    no raw location data published, no observer coordinates passed to decoder.
11. Unrelated project decisions/services: preserved; no change to Tower ASR,
    audio/METEOR retention or classification thresholds.

Normal canonical Git publication is recorded by the commit containing this
report. No optional dashboard/list/map integration was attempted; reliable
private capture and restoration took priority. Front-end filtering/LNA need is
inconclusive; no hardware or bias-tee power was changed.
