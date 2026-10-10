# Operation and service layout

Inspected **10 October 2026**. Live project: `/root/rf-watchkeeper`; primary backend: `/root/sdr_demo/scheduler.py`. Inspect ownership/reservations before intervention. Ordinary scheduling intentionally stops during managed METEOR capture; an inactive successful oneshot is normal between timer activations.

| Unit | Role / observed scheduling |
|---|---|
| `rf-watchkeeper-dashboard.service` | Active; dashboard/API port 8080 |
| `rf-watchkeeper-scheduler.service` | Active; adaptive V4 sharing. Speaker-volume drop-in requires `evk-speaker-volume.service` at 30% |
| `rf-watchkeeper-atis-process.service` | Active; Tower acoustic classification and production ATIS device1 ASR/optional Genie |
| `rf-watchkeeper-atis-shadow.service` | Active; separate durable candidate queue, lowest-priority accelerator leases |
| `rf-watchkeeper-atis-validation.service` / `.timer` | Candidate discovery without inference; 90 s after boot then every 60 s; timer active |
| `rf-watchkeeper-tower-anomaly-shadow.service` / `.timer` | Bounded diagnostic batches; 2 min after boot then 60 s after inactivity; timer active; batch drop-in sets 70 s timeout |
| `rf-watchkeeper-interpreter.service` | Active legacy saved-event Genie bridge; activity does not establish successful interpretation |
| `rf-watchkeeper-health.service` / `.timer` | 2 min after boot then every 5 min; timer active |
| `rf-watchkeeper-meteor-plan.service` / `.timer` | Hourly planning; 2 min after boot |
| `rf-watchkeeper-meteor-dispatch.service` / `.timer` | Claims due pass; 3 min after boot then 30 s after inactivity |
| `meteor-auto-capture.service` | Claimed capture; bounded 40 min, stop-hook recovery |
| `rf-watchkeeper-meteor-process.service` / `.timer` | Docker/SatDump file processing; 4 min after boot then 5 min after inactivity |
| `rf-watchkeeper-meteor-recover.service` | Enabled boot repair/resume |
| `rf-watchkeeper-meteor-cleanup.service` / `.timer` | Daily 02:00 UTC plus 15-min maintenance drop-in; **both deletion gates false** |
| `rf-watchkeeper-meteor-legacy-register.service` / `.timer` | Legacy metadata registration; 45 s after boot then 60 s |
| `satellite-v4-preflight.service` | Legacy guarded preflight/reboot helper |
| `rf-watchkeeper-sensors.service`, `rf-watchkeeper-ais.service`, `rf-watchkeeper.service` | Optional/standalone/legacy receiver paths disabled; normal AIS uses the scheduler |

METEOR timers were active; capture/process/health oneshots need not be continuously running. Historical dated satellite/preflight timers are evidence, not a fresh-install activation list. Manual reservations participate in guards. Effective definitions include drop-ins; public snapshots are in [deploy/systemd](../deploy/systemd). Root duplicate units are older snapshots. The speaker guard executable/unit and external ASR/model environments remain acquisition prerequisites; exported drop-ins alone do not supply them.

```sh
cd /root/rf-watchkeeper
systemctl status rf-watchkeeper-dashboard.service rf-watchkeeper-scheduler.service
systemctl status rf-watchkeeper-atis-process.service rf-watchkeeper-atis-shadow.service
systemctl list-timers --all
systemctl cat rf-watchkeeper-scheduler.service rf-watchkeeper-tower-anomaly-shadow.service
journalctl -u rf-watchkeeper-scheduler.service -n 50 --no-pager
curl --max-time 10 -f http://localhost:8080/api/state
curl --max-time 10 -f http://localhost:8080/api/meteor/schedule
```

Commands above are read-only and bounded; state can time out despite an active dashboard. Review journals/retained results rather than restarting everything. Inspect pending inference and METEOR ownership before a necessary component restart; preserve newer records, local observer config and pins. No forced probe/reset/reboot/service restart occurred in this audit. [Recovery](watchdog-and-recovery.md), [troubleshooting](troubleshooting.md), [installation/update procedure](installation.md).

The audit exports already installed source/units to GitHub and synchronizes documentation only to the EVK. It does not redeploy runtime, enable optional units, repair Genie/DMA failures or validate reboot persistence. [Completion evidence](evidence/repository-audit-20261010/completion.md).
