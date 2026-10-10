# RF health watchdog and recovery

Detailed implementation: [RF_HEALTH.md](../RF_HEALTH.md); dated evidence: [reliability](reliability.md). The watchdog detects silent receiver/pipeline failure using **real sample activity**, independently of decoded AIS, speech or images.

AIS reports native sample-processing evidence; audio reports PCM, ATIS/Tower recorded PCM, METEOR IQ/preflight bytes and exit status. Intentional satellite cancellation is separate from RF failure. V4MAIN01 is enabled/required; disabled 43300001 displays DISABLED.

Age thresholds: GREEN below 900 s, YELLOW 900–1800 s, RED above 1800 s. Valid active ownership/reservations display busy; each boot needs fresh samples. Stale idle evidence triggers a probe rather than a failure solely from unscheduled inactivity. The five-minute timer supports a once-per-pass stronger check 10–15 minutes before capture.

The serial-selected probe requests 256,000 samples at 256 kS/s with an eight-second timeout, requiring exactly 512,000 varied cu8 bytes and normal exit. Temporary data is removed. Probe settings do not change satellite capture policy.

Recovery: probe → bounded cleanup of provably expired owners → verified receiver-only USB hook if configured → scheduler restart/reprobe → last-resort reboot. Unknown/continuous owners are protected. `usb_recovery_command` is null; no verified V4-only USB reset exists and no generic hub reset is installed.

Shared durable SQLite state limits automatic reboots to one per hour across health and managed METEOR recovery. Health reboot is suppressed during active satellite ownership or within seven minutes of scheduled recording. Managed recovery retains per-pass reboot reservations/post-boot resume; interrupted health checks restore ordinary scheduling only when satellite ownership permits.

Tables: `rf_health_jobs`, `rf_health_events`, `rf_health_state`, `rf_health_reboot_guard`. Dashboard Overview exposes age, latest capture, outcome and recovery history.

```sh
systemctl show rf-watchkeeper-health.service -p Result -p ExecMainStatus
journalctl -u rf-watchkeeper-health.service -n 50 --no-pager
```

`rf_health_monitor.py --force-probe --no-reboot` is an active check that may pause ordinary RF; inspect reservations first. This task performed no probe/recovery/restart/reboot. Simulated tests and observed checks do not establish real reboot acceptance or long-term reliability.

## Validation audit — 5 October 2026

Inspection of current source, systemd snapshots, test cases, retained evidence, initial Git import and live read-only state confirmed this recovery already exists. No recovery code was added. [Stage classification and evidence](testing-and-validation.md#watchdog-stage-classification--5-october-2026) distinguishes controlled tests from real hardware recovery. Safe control stages have adequate existing evidence, so this audit repeated no fault injection or recovery test. USB reset and a real reboot remain explicit limitations.

The actual monitor first pauses ordinary scheduling, cleans provably overdue owners and refuses protected owners before its first direct probe; it then retries cleanup/probing, optionally invokes a verified USB hook, reprobes, restarts/stops the scheduler for another protected probe, and finally considers reboot. Service restoration occurs in `finally` or the systemd stop hook. Reboot consumes the shared durable guard before requesting `systemctl reboot`. METEOR uses a separate persisted per-pass reservation and resume timer with one-attempt protection, clock synchronization and remaining-window/other-satellite checks.

At 19:34:57 UTC (22:34:57 EEST), V4MAIN01 was GREEN, 43300001 DISABLED; scheduler, dashboard, Airband worker and health timer were active, health service Result=success/ExecMainStatus=0. State/Tower/ATIS/METEOR/schedule APIs returned HTTP 200. No capture was active; next managed recording starts 6 October at 04:26:50 EEST. [Read-only evidence](evidence/watchdog-audit-state.json). This is a momentary state, not long-run acceptance.

## Current operational limits — 10 October 2026

Health timer and primary services remain active; no new fault injection, forced recovery, USB/DSP reset or reboot was performed. Sample progress still does not imply successful interpretation. Corrected ATIS workers are deployed on device1, but retained DMA growth, Genie failures and dashboard timeouts failed integrated acceptance. Do not reset DSP mappings or restart unrelated services as an undocumented workaround; preserve evidence and protect imminent/active satellite ownership. [Failure details](evk-utilization-status-20261009.md), [current services](operation.md).

Recovery after individual METEOR captures has dated successful observations; full watchdog reboot/end-to-end resume and sustained all-workload reliability remain unverified. Repair/retry Tower failures individually using preserved failure records; never bulk-clear terminal JSON or delete failed/unverified satellite raw IQ. [Tower recovery](tower-failure-fix-20261009.md), [retention](data-retention.md).
