# Dashboard disconnect investigation — 11 October 2026

All times Helsinki (UTC+3) unless stated otherwise. No observer coordinates or private network identifiers included.

## Timeline and diagnosis

- 10:53:18: automatic M2-3 capture service started.
- 10:53:25: capture intentionally stopped the RF scheduler; preflight acquired 512000 bytes successfully.
- 10:55:24: IQ recording started at 256000 samples/s, planned through 11:08:46.930.
- 11:00:58 inspection: dashboard active, NRestarts=0; capture active. Dashboard journal had no request events because `log_message` was disabled.
- 11:01:47–48: six isolated state calls returned HTTP 200 in 0.121–0.204 s.
- Concurrent state/audio/ATIS/shadow/Tower/METEOR/schedule reproduction: state 5.032737 s, subsequent state 1.273/0.649/0.503/0.190 s; audio 8.802596 s, Tower 5.762515 s, METEOR 3.300517 s. All returned 200. The browser's five-second abort explains a disconnect followed by reconnect even with a live service.

AudioWorkflow.catalog recursively discovers and sorts WAV files for every two-second progress request. Overlapping expensive requests in the same Python dashboard process can delay state handling. Catalog caching reduces repeated work; the longer deadline tolerates cold/refresh scans. This is a demonstrated contributing bug, not proof that every reported disconnect had this cause. Historical integrated-run state timeouts remain a separate unresolved acceptance issue.

Memory available ~25 GB, no swap usage; sampled CPU idle 73–82%, no I/O wait. No matching kernel OOM/I/O/link/reset events. NetworkManager showed no transition in the inspected interval; Tailscale emitted PCP mapping warnings at 10:51:42 and 10:56:49, with UDP still available and mapping recovered at 10:57:13. Local-loopback reproduction establishes that network loss is unnecessary to cause this symptom. Historical resource peaks and browser failure timestamps were not retained.

Capture source/service inspection found scheduler stop/start actions, no dashboard stop/restart or dependency coupling. Expected: receiver reservation and scheduler pause. Unexpected: dashboard connection flapping.

## Change and checks

`audio_workflow.py`: 30-second catalog display cache, serialized refresh, copy isolation, fresh selection validation. `dashboard.html`: 15-second state timeout. `dashboard.py`: UTC route/header timing, omitting client addresses, queries and payloads. No RF, retention, inference or satellite configuration changes.

Staged `PYTHONPATH=/root/rf-watchkeeper python3 /tmp/test_audio_catalog_cache.py`: 2 tests passed (cache expiry/isolation and deleted-selection rejection). `python3 -m py_compile /tmp/dashboard.py /tmp/audio_workflow.py`: passed. One initial test command failed because Windows command-shell quoting treated the entire remote command as a filename; the corrected invocation passed.

Reboot and a new full unattended run are unverified. Exact original browser disconnect times cannot be reconstructed.

## Deployment and expanded regression

Capture completed at 11:08:47 with 391.0 MiB retained and `pending_decode`; this establishes successful IQ capture, not successful satellite decoding. Dashboard-only restart at 11:09:45 activated the cache, timeout and logging. The first deployment script encountered invalid UTF-8 in the live HTML after backing up/copying Python source but before restart. Recovery applied a byte-level timeout substitution, preserving all other live HTML bytes and local map configuration.

New logging then demonstrated that catalog caching alone was insufficient: review/validation work took 29–41 s and state requests still took up to 21.38 s. The final fix runs each state snapshot in a separate bounded Python subprocess, outside the GIL used by review requests. Maximum two simultaneous state workers, 12 s worker timeout, 503 on timeout/capacity/error; frontend deadline remains 15 s. Worker CLI `--snapshot-only` does not start the server or audio workflow. No new systemd service or dependency is required.

Final dashboard-only restart deployed this additional isolation after capture ended. `python3 -m unittest test_dashboard_state_isolation test_audio_catalog_cache`: four tests passed. Staged snapshot emitted valid online schema; compilation passed. Tests cover cache expiry/copy isolation, stale selection rejection, preserving configured paths/output and worker-slot release after repeated timeouts.

11:13:36 concurrent state/audio/ATIS/shadow/Tower/METEOR/schedule/validation check: six state responses HTTP 200, 0.408/0.344/0.322/0.328/0.336/0.359 s. Tower 11.316 s, validation 12.760 s, audio 12.802 s (cold/contended); all eventually HTTP 200. Dashboard and scheduler active, no automatic dashboard restart. Warm catalog requests previously measured 0.0017–0.0019 s. Heavy-panel delays remain; this repair protects state generation rather than claiming every endpoint is fast.

Implemented, tested, deployed and production-active; service-restart persistence verified. Browser reload is needed for an already-open page's new deadline. Another full METEOR pass/browser session and unattended/reboot acceptance are not yet verified. No capture was interrupted, reboot performed or radio settings changed.

## Rollback and completion gates

Restore the three original files from EVK `backups/dashboard-disconnect-20261011/`, then restart only `rf-watchkeeper-dashboard.service` after checking capture and audio-job state. The live HTML receives only the timeout substitution so private local map configuration is preserved. Public source retains its sanitized map defaults.

Changes, focused tests, operations/current-status documentation and dated log are tracked in canonical Git. Original files/private evidence remain EVK-only; a source patch is retained with public evidence. Deployment/restart checks passed; reboot and unattended acceptance remain explicitly open. Hardware/RF acceptance, native DMA/Genie faults and decoder acceptance are outside this scoped repair.
