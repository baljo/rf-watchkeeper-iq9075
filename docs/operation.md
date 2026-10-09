# Operation and service inventory

The live project is `/root/rf-watchkeeper`. Inspect ownership before intervention: ordinary scheduling intentionally stops while METEOR owns V4. Avoid competing receivers, forced probes or reboots during reservations.

Installed definitions were inspected on 5 October; snapshots are in `deploy/systemd/`. Drop-ins and current code can override original base-unit comments.

| Unit | Role / scheduling |
| --- | --- |
| `rf-watchkeeper-dashboard.service` | Enabled dashboard, port 8080 |
| `rf-watchkeeper-scheduler.service` | Enabled V4 scheduler; external drop-in requires installed 30% speaker guard |
| `rf-watchkeeper-atis-process.service` | Enabled low-priority Tower/ATIS worker |
| `rf-watchkeeper-interpreter.service` | Enabled legacy interpretation bridge; does not certify Genie success |
| `rf-watchkeeper-health.service` / `.timer` | Two minutes after boot, then every five minutes |
| `rf-watchkeeper-meteor-plan.service` / `.timer` | Hourly planning; two minutes after boot |
| `rf-watchkeeper-meteor-dispatch.service` / `.timer` | Claims due pass; three minutes after boot, then 30 s after inactivity |
| `meteor-auto-capture.service` | Claimed capture; 40-minute bound and stop-hook recovery |
| `rf-watchkeeper-meteor-process.service` / `.timer` | Docker/SatDump queue; four minutes after boot, then five minutes after inactivity |
| `rf-watchkeeper-meteor-recover.service` | Enabled boot repair/resume |
| `rf-watchkeeper-meteor-cleanup.service` / `.timer` | Maintenance daily 02:00 UTC plus 15-minute active interval from drop-in; deletion gates false |
| `rf-watchkeeper-meteor-legacy-register.service` / `.timer` | Registers historical metadata; 45 s after boot, then every 60 s |
| `satellite-v4-preflight.service` | Legacy preflight through guarded health/reboot helper |
| `rf-watchkeeper-sensors.service` | Disabled optional 433 receiver |
| `rf-watchkeeper-ais.service`, `rf-watchkeeper.service` | Disabled standalone/legacy paths; ordinary AIS uses primary scheduler |

Historical dated `meteor-m23-*`, `meteor-m24-*` and `satellite-v4-preflight-*` timers remain as prior evidence; inspected historical timers were disabled. Manual reservations participate in guards.

```sh
cd /root/rf-watchkeeper
systemctl status rf-watchkeeper-dashboard.service rf-watchkeeper-scheduler.service
systemctl status meteor-auto-capture.service rf-watchkeeper-health.timer
systemctl list-timers --all
journalctl -u rf-watchkeeper-scheduler.service -n 50 --no-pager
curl -f http://localhost:8080/api/state
curl -f http://localhost:8080/api/meteor/schedule
```

These are read-only checks. See [troubleshooting](troubleshooting.md), [RF jobs](rf-jobs.md) and [retention](data-retention.md).


Tower AD terminal failure handling and recovery: [9 October audit](tower-failure-fix-20261009.md). Automatic shadow diagnostics verified in a short window; sustained capacity and reboot verification remain outstanding.
