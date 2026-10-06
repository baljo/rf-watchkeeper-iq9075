# Adaptive RF hopping — 6 October 2026

Implemented on canonical `baljo/rf-watchkeeper-iq9075` and deployed through the existing EVK SSH connection. Current scheduler/capture files matched canonical main before editing; Tower recent/history/retention work was already present and reused.

## Behavior

METEOR > active Tower hold > due ATIS > due Tower probe > AIS. Tower probes last 15 wall seconds, target 60-second start intervals in the existing Helsinki operating window, and use sustained DC-free PCM RMS energy (40-unit threshold, 240-ms confirmation) to hold until about 10 seconds quiet, capped at 75 wall seconds. ASR remains downstream. AIS fills the gaps in up-to-45-second chunks shortened to the next due slot. ATIS remains 90 seconds every 600 seconds. A long periodic slot that cannot fit before a satellite reservation can defer to a shorter safe slot. FM and 433 remain disabled.

Existing device lock, serial, gain, collection/database paths, processing, raw transcripts, and satellite stop/restore mechanism remain. Guards cover managed trigger/preflight through post-margin record_stop plus manual services/timers, fail closed, and recheck in-flight slots every second. Airband reaps rtl_fm and closes its pipe; AIS preemption terminates its process group. Uncertain cleanup stops the scheduler for existing systemd cgroup cleanup/restart. No reboot or USB reset.

Cadence state survives restart; corrupt/future state backs off one interval. Attempt counters persist before capture. Metrics record probes, extensions, Tower PCM seconds, AIS slot wall seconds, ATIS attempts, and satellite deferrals/guard episodes/preemptions. Individual outcomes remain in existing JSONL and receiver sample-health records.

## Validation

- 48 native scheduler/Airband tests passed, including 16 new scheduler/activity/capture/preemption tests and the 32 existing Airband/Tower tests. Existing health/AIS/METEOR recovery/retention/history/import suites: 111 passed using the configured satellite virtual environment. A deployed subset of 20 tests passed separately; it is not added to these totals. Initial isolated test setup needed the bundled timezone file and correct backend path; satellite suites require their configured virtual environment.
- Capture-loop injection proves weak sustained energy without ASR, click/DC rejection, resumed activity, 10-second quiet tail, 75-second hard cap, METEOR exclusion and active Tower/AIS preemption with child cleanup. Managed trigger and post-margin boundaries are mocked, with no actual pass modified/interrupted.
- Live observation began 15:48:44 UTC (18:48:44 EEST). The final source loaded at 15:54:00 UTC. Multiple deliberate guarded reloads during deployment retained cadence/state; they were not failure restarts. One pre-existing fixed Tower capture and one AIS filler were cancelled during reload, and their evidence/history remains.
- Six completed adaptive Tower captures in the ownership-observation window, 14.08–14.336 seconds of PCM each. Unblocked starts were 61.537–61.689 seconds apart. One interval was 131.233 seconds because normal ATIS occupied the receiver. Nine attempted Tower probes were recorded by the later final check, with 126.976 accumulated PCM seconds and no activity extensions.
- Normal ATIS started 15:50:09 UTC, completed with 89.088 seconds PCM, and reached partial_success through the existing processor. Tower resumed afterward. This is operational processing evidence, not a claim of transcript/weather accuracy.
- AIS filled gaps, normally about 43–44 seconds, with a 22-second filler ending at ATIS due time. Received 96 channel-A and 64 channel-B messages by final check; collection/storage source is unchanged. Accumulated filler wall seconds: 374.240 at final check.
- 207 one-second process observations: zero samples with multiple RF owners; maximum one rtl_fm/AIS-catcher/rtl_sdr process. This bounded observation does not certify indefinite reliability.
- Scheduler, worker, dashboard, interpreter and health timer active. Scheduler NRestarts=0; no failed sample-health jobs since deployment. Dashboard, state, Tower, ATIS and METEOR APIs returned HTTP 200 on configured port 8080. The initial verifier used port 8765; corrected successful API results appear in the public aggregate evidence. Detailed trace remains on the EVK.
- Tower API still returns 20 recent attempts; a no_activity WAV downloaded via its exact capture URL and parsed as mono 8 kHz, 14.08 seconds. Existing history and rolling-silence tests pass. dashboard.py and atis_view.py hashes unchanged. Live dashboard HTML is byte-for-byte unchanged except the cadence label; private live map settings were preserved. All inline public dashboard scripts pass Node syntax checks. Deployed scheduler/capture/module/config hashes match the committed candidates.

## Limits and tuning

No positive live Tower transmission arrived in the observation window. Energy-driven extension is verified through injected PCM; its real-signal sensitivity/noise discrimination remains to be tuned. Continuous noise above threshold can cause a bounded hold. Adjust `activity_rms`, `quiet_seconds`, `max_listen_seconds`, `dwell_seconds`, and `interval_seconds` in jobs-v4.jsonc, then restart the scheduler outside a protected pass. Start threshold is 40 versus observed quiet peak RMS about 13–16; this does not establish calibrated RF sensitivity. Tower's 05:00–01:30 Helsinki operating window is preserved. Recognition/language accuracy, optional Genie failures, and long-run/hardware-fault acceptance remain pre-existing limits.

No satellite capture/planner/retention files, recordings/history schemas, receiver gain, private observer settings, or unrelated services were changed. New public files contain no precise observer coordinates.

Backups: `/root/rf-watchkeeper/backups/adaptive-rf-20261006T154844Z`, `...T155204Z`, final `...T155400Z`. Runtime evidence/staged tests: `/root/rf-watchkeeper/adaptive-stage-20261006/`. [Public aggregate validation](live-validation.json), [native Airband tests](tests.txt), [deployed subset](deployed-tests.txt), and one-time deployment/verification scripts are retained here.
