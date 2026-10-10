# RF jobs and resource arbitration

Adaptive scheduler deployed and validated on 6 October 2026. Earlier fixed-slot evidence remains in the project log.

| Job | Frequency | Configuration | Actual scheduling |
| --- | --- | --- | --- |
| Tower | 120.950 MHz AM | 15 s probe; 10 s quiet tail; 75 s hard limit; 8 kHz PCM; gain 19.7 dB | Target 60 s start interval; Helsinki 07:00 inclusive–23:00 exclusive |
| ATIS | 136.450 MHz AM | 90 s; 8 kHz PCM; gain 49.6 dB; priority 20 | Minimum 600 s start interval; all day |
| AIS | 162.000 MHz configured center | 45 s maximum chunks | Home workload; chunks shortened to the next Tower/ATIS due time |
| FM reference | 95.600 MHz FM | 35 s retained configuration | Disabled operationally |
| Satellite placeholder | 137.100 MHz | 600 s retained placeholder | Disabled; managed METEOR handles passes |

Priority is METEOR > active Tower hold > due ATIS > due Tower probe > AIS. One synchronous backend runs at a time, so ATIS cannot interrupt an active Tower hold. The next overdue periodic job runs once, without replaying missed slots. Longer holds, ATIS and METEOR delay the nominal Tower cadence.

The scheduler explicitly selects V4MAIN01, with a one-second ordinary handoff. Tower/ATIS have separate persisted last-slot timestamps in `logs/`; slots can be delayed by shared ownership and are not replayed in catch-up bursts. Bundled `Helsinki.tzif` supplies DST-aware scheduling on this image.

`job_manager.py` reuses `/root/sdr_demo/scheduler.py` (preserved under `backends/sdr_demo/`). Before each ordinary slot it checks managed satellite ownership/reservations and manual timers; Airband capture/model loops also recheck and yield. Failed guard inspection blocks competing work. Intentional skips/cancellation do not count as RF failures.

METEOR capture stops V4 scheduling and restores it afterwards. Offline decoding owns files, not the SDR. The retained Airband report observed satellite-driven restoration at 18:41:08 UTC; the scheduler was active again during this documentation task. This verifies those observations, not universal recovery reliability.

Optional `jobs-sensors.jsonc` selects 43300001 for 433.920 MHz Nexus-TH, 70-second dwell/60-second handoff; service and health requirement are disabled. See [Airband](airband.md), [AIS](ais.md), [METEOR](meteor.md), [services](operation.md) and [watchdog](watchdog-and-recovery.md).

## Adaptive tuning and observability

`jobs-v4.jsonc` enables `adaptive_hopping`. Tower settings are `dwell_seconds: 15`, `interval_seconds: 60`, `quiet_seconds: 10`, `max_listen_seconds: 75`, and `activity_rms: 40`. The hard maximum must not exceed 90 seconds. The 07:00–23:00 Helsinki operating window applies. ATIS remains 90 seconds every 600 seconds. AIS decoding and storage are unchanged, including both channels.

Tower uses DC-free 20-ms PCM RMS frames and requires 240 ms of sustained energy above the configurable threshold. Detection runs inside capture before ASR. Low-amplitude energy above threshold can extend a recording even when ASR finds no words. Continuous noise may also extend it; the 75-second limit prevents indefinite occupation. This conservative threshold is a starting value, not calibrated proof of speech or RF sensitivity. The capture metadata contains threshold, peak RMS, activity timestamp, trigger and extension. Startup delay is accounted for in the quiet tail.

Independent `tower-last-slot.json` and `atis-last-slot.json` preserve attempted start times. Corrupt/future-clock state is reset with one interval of backoff. A METEOR skip does not consume cadence. `logs/adaptive-metrics.json` persists probe/run counts, extensions, Tower PCM seconds, AIS slot wall seconds, and METEOR skips (one per continuous guard episode, plus in-flight preemptions). Existing JSONL transitions and sample health records remain authoritative for individual outcomes.

The guard fails closed, covers managed trigger/preflight through record_stop (already including configured pre/post margins), and retains manual satellite service/timer checks. It checks before every opening, every second during Tower/ATIS and AIS, and before each extended deadline. METEOR's existing stop-and-restore mechanism and device lock remain intact. AIS preemption terminates its process group; Airband always reaps rtl_fm. Unknown cleanup stops scheduling so systemd clears the service cgroup before restart. No USB reset or reboot was added.

## Current window and temporary pause

`job_manager.tower_active()` enforces 07:00–23:00 Europe/Helsinki and checks optional local `tower-recording-pause.json` (`until`, timezone-aware timestamp) before admitting Tower. An expired pause file does not disable Tower indefinitely. Older 05:00–01:30 descriptions are superseded. Tower ASR is deferred; capture/acoustic screening and AD shadow diagnostics remain separate. The configured priority number does not override the explicit adaptive due-job order described above.
