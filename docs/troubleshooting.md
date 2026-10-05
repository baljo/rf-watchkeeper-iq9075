# Troubleshooting

Start with ownership/status checks; do not make AIS and satellite compete for V4.

```sh
systemctl status meteor-auto-capture.service rf-watchkeeper-scheduler.service
systemctl list-timers --all
curl -f http://localhost:8080/api/meteor/schedule
ps -eo pid,ppid,args | grep -E 'rtl_|AIS-catcher|satellite_capture|meteor_pipeline'
lsusb
journalctl -u rf-watchkeeper-health.service -n 50 --no-pager
```

| Symptom | Inspect | Action |
| --- | --- | --- |
| V4 disappears/stream stalls | USB enumeration/kernel logs, sample age and byte counts | Check cable/power/hub in safe RF window; use guarded recovery and preserve logs; no generic hub reset verified |
| `usb_claim_interface error -6` | Receiver processes, active/manual satellite units | Identify owner; stop only confirmed stale bounded owners after reservations clear |
| Scheduler holds V4 before METEOR | Plan/dispatch/capture journals and scheduler PID | Check managed handover/recovery; do not force competing receiver |
| Failed scheduler label during pass | Intentional stop timing and later restoration | AIS cancellation can leave exit-code label; confirm later restoration |
| AIS and satellite fail for hours | RF sample health separately from application result | Quiet AIS/poor imagery alone is insufficient; stale failed samples warrant guarded recovery |
| FC0012 correlates with interference | Disabled state/topology/comparison conditions | Keep optional receiver disabled; mechanism/remedy needs controlled comparison |
| METEOR no images | Recorded rate, offsets, logs, channel lines/all attempts | Retain IQ through grace/review; nominal 137.900 MHz is not proof of centered LRPT |
| Images then return 139/-11 | Valid PNGs/channel counts and crash diagnostic | Preserve partial-success evidence; crash is not fixed |
| Tower/ATIS no text | Window/slot/guard, samples, segmentation, fresh ASR output | Silence is normal; missing output is failure; never reuse stale text |
| ATIS partial success | Base ASR versus Genie status | Review available transcript/audio; optional Genie currently fails |
| FM interference/weak indoor signal | Frequency/gain, antenna placement/filter diagnostics | Plan controlled placement/filter tests; periodic FM remains disabled |
| Old sensor values | Reading age and receiver DISABLED | Treat as history |
| Disk growth | Raw disposition/gates, positive audio archive | Review evidence; do not shorten grace or delete useful references |

Exact antenna/filter inventory and V4-only USB reset are gaps. Read [retention](data-retention.md) and [watchdog](watchdog-and-recovery.md) before active actions. No RF setting/service change occurred for documentation.

Before proposing another fault test, consult the [watchdog stage classification](testing-and-validation.md#watchdog-stage-classification--5-october-2026). A successful simulated reboot/resume is not a real reboot recovery. Current safe-stage evidence does not justify repeating injection tests; leave risky reboot acceptance explicitly unvalidated. Before sharing logs/configs/patches, apply the [location privacy policy](location-privacy.md), including numeric map centres and historical snapshot contents.
