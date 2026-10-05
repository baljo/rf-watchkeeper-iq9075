# RF jobs and resource arbitration

Verified against installed source/configuration after the 5 October 2026 18:42 UTC Airband deployment.

| Job | Frequency | Configuration | Actual scheduling |
| --- | --- | --- | --- |
| Tower | 120.950 MHz AM | 30 s; 8 kHz PCM; gain 19.7 dB; priority 30 | Minimum 180 s start interval; Helsinki 05:00 inclusive–01:30 exclusive next day |
| ATIS | 136.450 MHz AM | 90 s; 8 kHz PCM; gain 49.6 dB; priority 20 | Minimum 600 s start interval; all day |
| AIS | 162.000 MHz configured center | Configured 120 s; priority 0 | `job_manager.schedule()` caps background dwell to 30 s when Tower recording is configured |
| FM reference | 95.600 MHz FM | 35 s retained configuration | Disabled operationally |
| Satellite placeholder | 137.100 MHz | 600 s retained placeholder | Disabled; managed METEOR handles passes |

The scheduler explicitly selects V4MAIN01, with a one-second ordinary handoff. Tower/ATIS have separate persisted last-slot timestamps in `logs/`; slots can be delayed by shared ownership and are not replayed in catch-up bursts. Bundled `Helsinki.tzif` supplies DST-aware scheduling on this image.

`job_manager.py` reuses `/root/sdr_demo/scheduler.py` (preserved under `backends/sdr_demo/`). Before each ordinary slot it checks managed satellite ownership/reservations and manual timers; Airband capture/model loops also recheck and yield. Failed guard inspection blocks competing work. Intentional skips/cancellation do not count as RF failures.

METEOR capture stops V4 scheduling and restores it afterwards. Offline decoding owns files, not the SDR. The retained Airband report observed satellite-driven restoration at 18:41:08 UTC; the scheduler was active again during this documentation task. This verifies those observations, not universal recovery reliability.

Optional `jobs-sensors.jsonc` selects 43300001 for 433.920 MHz Nexus-TH, 70-second dwell/60-second handoff; service and health requirement are disabled. See [Airband](airband.md), [AIS](ais.md), [METEOR](meteor.md), [services](operation.md) and [watchdog](watchdog-and-recovery.md).
