# Dashboard and APIs

`rf-watchkeeper-dashboard.service` runs `dashboard.py --host 0.0.0.0 --port 8080`. Browse `http://<EVK-address>:8080` on the trusted local network. Session-token checks protect write operations; this is not public multi-user authentication.

| Route | Purpose |
| --- | --- |
| `/` | Overview/health, AIS map, saved audio, Tower, ATIS, sensors and satellite panels |
| `/api/state` | Scheduler/receiver health, AIS targets/met-hydro and current sensor state |
| `/api/nexus/history` | Historical sensor charts |
| `/api/audio` | Saved-audio workflow status/inventory |
| `/api/audio/file/<id>` | Controlled saved-audio access |
| `/api/tower`, `/api/atis` | Airband status, transcript and review information |
| `/api/tower/audio`, `/api/atis/audio` | Retained Airband audio; quiet finalized results may have none |
| `/api/meteor` | Satellite history/products and retention state |
| `/api/meteor/schedule` | Planned geometry, schedule and capture conditions |
| `/api/meteor/image/<id>` | Indexed image access with controlled path resolution |
| `POST /api/audio/run` | Session-authorized saved-audio processing |
| `POST /api/meteor/pin` | Session-authorized Keep/reference protection |

AIS map distinguishes local/regional targets, base stations and data age. Sensor history remains visible when the receiver is disabled. Overview health separates samples from application outcome. Satellite history preserves attempts, historical rates and crash diagnostics.

Read-only checks of state, Tower, ATIS, audio, METEOR and schedule returned HTTP 200 during this task. Route availability does not prove recognition accuracy or uptime. Image-route evidence is retained in [METEOR regression](evidence/meteor-crash-regression.json). Never publish session-token values. See [operation](operation.md).


## Tower capture visibility — 2026-10-06

Tower displays the latest 20 capture attempts, including no_activity, at the top of Airband. Times use Europe/Helsinki. Available audio has playback/download controls; expired audio retains capture metadata. Silent live Tower WAVs remain within the latest 20 capture folders; older processed silence is pruned without touching speech, reference, ATIS or satellite material. See [project log](project-log.md).

## AIS map reception history — verified 8 October 2026

Both the regional and local AIS maps use the shared Recent / 24 hours / 7 days selector (default 24 hours). Changing it redraws both maps. Recent uses existing live target timeouts (moving targets 30 minutes, stationary/unknown-speed positions 1 hour, base stations 24 hours; identity-only targets 2 hours). Live API inventory can include identities without plottable positions.

`/api/state` adds `ais_history_targets`: `historical_targets(168, 500)` reads the latest retained position per MMSI from ais_targets, orders by position_seen descending, includes positions within seven days, validates coordinates and a 250 km observer radius, and caps at 500. The browser filters position_seen against server_time for 24/168 hours, rejecting future timestamps. Static identity messages update last_seen without refreshing position_seen. This is last-known reception history, not a track of every past position or current vessel locations. Local range filters may reduce displayed counts.

Hover text gives Position received with browser-local timestamp and elapsed reception age. Historical targets outside the live positioned MMSI set are faded to opacity 0.65 and receive name/MMSI plus age labels; other targets older than 30 minutes fade to 0.30. Local map labels are spaced with connector lines where displaced. Reception age describes the last position message, not current vessel freshness.

See [dated validation, tests, restart, rollback and showcase evidence](ais-dashboard-completion-20261008.md). Counts in that report are time-dependent observations, never fixed expected totals.
