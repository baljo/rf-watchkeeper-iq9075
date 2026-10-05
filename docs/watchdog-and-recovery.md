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
