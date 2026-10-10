> Repository layout, 10 October 2026: this preserved guide moved from `RF_HEALTH.md`. Relative code/configuration commands below assume the application root as the working directory. Historical deployment/stage paths remain dated evidence; follow [current installation](../installation.md) and topic guides.

> Documentation status, 2026-10-05: See [reliability evidence and limits](../reliability.md), [hardware status](../hardware.md) and the [engineering log](../project-log.md). This guide describes installed monitoring; successful checks do not establish real reboot validation or long-run acceptance.

# RF receiver watchdog

The receiver watchdog uses real sample activity, never a requirement for decoded traffic. V4 jobs report to `data/watchkeeper.db`; the empty legacy root-level `watchkeeper.db` is not the application's database.

`rf-watchkeeper-health.timer` runs every five minutes, beginning two minutes after boot. The service follows filesystem/time synchronization, the RF scheduler and METEOR boot recovery. Its stop hook restores the scheduler if a health check was interrupted after pausing ordinary jobs; active satellite reservations take priority.

Receiver configuration is in `rf-health-config.json`: V4MAIN01 is enabled and required; 43300001 is disabled. Keep the legacy receiver disabled while disconnected. The staged recovery implementation currently operates on the primary V4; a future second required receiver needs its scheduler and sample-reporting backend integrated before enabling its recovery.

Age thresholds are GREEN under 900 seconds, YELLOW from 900 to 1800 seconds, and RED over 1800 seconds. Valid active RF jobs and satellite reservations are shown as busy rather than treated as failed. Stale idle activity causes a short sample probe, avoiding alarms simply because nothing was scheduled. Each boot requires fresh successful capture evidence.

The probe selects the receiver serial explicitly and captures 256000 IQ samples at 256000 samples/sec with an eight-second timeout. It requires exactly 512000 bytes of varied unsigned IQ data and a normal exit. Temporary data is removed. This test setting does not change scheduled satellite settings.

The monitor checks persisted managed passes and existing manual satellite timer triggers. It performs a stronger probe in the 10–15 minute period before recording and records the pass ID to avoid repeatedly interrupting ordinary work. Existing two-minute capture preflights remain in place. It changes neither pass times nor sample rates.

Recovery proceeds through sample probing, bounded cleanup of provably expired V4 processes, a verified receiver-only USB recovery hook if configured, scheduler restart and another sample probe, then last-resort reboot. Unknown or continuous owners are protected. No generic USB hub reset is installed: this EVK has no verified V4-only reset facility. `usb_recovery_command` remains null. Do not configure it with a generic bus reset.

The shared reboot guard is durable in SQLite, transactionally limited to one automatic reboot per hour, and used by both the monitor and managed METEOR recovery. Watchdog reboot is suppressed inside seven minutes of a scheduled recording or during any active satellite reservation. Existing managed per-pass reboot reservations and post-boot resume logic are preserved. A real reboot was not performed to test this implementation.

AIS keeps its native device, gain, AGC, bandwidth and decoder path. Its native sample-processing benchmark provides evidence independent of AIS message count; zero messages can therefore be healthy. The parent enforces dwell plus 20 seconds, the native AIS process has a secondary bounded run time, and children are cleaned up as a process group. Its output reader cannot block indefinitely on an unterminated line.

FM and Tower retain the existing audio pipeline, with a transparent PCM byte counter. ATIS uses recorded PCM sample count. METEOR captures and their IQ preflights record IQ byte evidence and exit status. The gain diagnostic uses the same AIS evidence and excludes satellite windows. Intentional early service cancellation is retained in health history but does not count as a receiver failure.

New tables are `rf_health_jobs`, `rf_health_events`, `rf_health_state`, and `rf_health_reboot_guard`. The sample-job table includes a boot ID via an additive migration. Existing tables and records are preserved. Controlled regression simulations are retained separately as TEST-SIMULATION and cannot affect primary receiver health.

Useful read-only checks:

```
systemctl status rf-watchkeeper-health.timer
systemctl show rf-watchkeeper-health.service -p Result -p ExecMainStatus
journalctl -u rf-watchkeeper-health.service
```

`python3 rf_health_monitor.py --force-probe --no-reboot` performs a live readiness check, briefly releasing ordinary jobs when safe, with reboot disabled. `--simulate` exercises decision reporting without probing or controlling services. `python3 -m unittest test_rf_health` tests quiet AIS, hard deadlines, guarded recovery, controlled stale-process cleanup, shared reboot limiting, and interrupted-check restoration using temporary health databases.

The Overview dashboard displays health, latest capture, heartbeat age, separate application outcome, recent failures and recovery history. The intentionally disconnected receiver displays DISABLED.

Original source, database and satellite plan snapshots are retained under `backups/rf-health-20261005T112419Z`; follow-up changes have additional rf-health backup directories. The EVK directory has no Git metadata or installed Git, so this change was not committed or pushed. A review patch and equivalent snapshot diff statistics are provided separately.
