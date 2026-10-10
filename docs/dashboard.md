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

Tower displays the latest 20 capture attempts, including no_activity, at the top of Airband. Times use Europe/Helsinki. Available audio has playback/download controls; expired audio retains capture metadata. The latest 20 is a display limit. Current Tower audio retention is 30 days with permanent pins protected; older already-missing audio remains missing. This supersedes the October 6 silent-audio rolling window. See [project log](project-log.md).

## AIS map reception history — verified 8 October 2026

Both the regional and local AIS maps use the shared Recent / 24 hours / 7 days selector (default 24 hours). Changing it redraws both maps. Recent uses existing live target timeouts (moving targets 30 minutes, stationary/unknown-speed positions 1 hour, base stations 24 hours; identity-only targets 2 hours). Live API inventory can include identities without plottable positions.

`/api/state` adds `ais_history_targets`: `historical_targets(168, 500)` reads the latest retained position per MMSI from ais_targets, orders by position_seen descending, includes positions within seven days, validates coordinates and a 250 km observer radius, and caps at 500. The browser filters position_seen against server_time for 24/168 hours, rejecting future timestamps. Static identity messages update last_seen without refreshing position_seen. This is last-known reception history, not a track of every past position or current vessel locations. Local range filters may reduce displayed counts.

Hover text gives Position received with browser-local timestamp and elapsed reception age. Historical targets outside the live positioned MMSI set are faded to opacity 0.65 and receive name/MMSI plus age labels; other targets older than 30 minutes fade to 0.30. Local map labels are spaced with connector lines where displaced. Reception age describes the last position message, not current vessel freshness.

See [dated validation, tests, restart, rollback and showcase evidence](ais-dashboard-completion-20261008.md). Counts in that report are time-dependent observations, never fixed expected totals.

## Current Airband/review behavior — 10 October 2026

Tower displays acoustic classification, diagnostic score/threshold, review state and playable retained audio; ASR is deferred. The optional queue is newest 20 **unreviewed completed valid AD scores >= recorded threshold**, not all acoustic voice candidates. GET `/api/tower?review=anomaly_candidate` selects it; `candidate_voice` is a compatibility alias. GET `/api/tower/reviews` includes cumulative validation; token-protected POST `/api/tower/review` saves human labels and refreshes the queue. Any saved classification removes the item. Inclusive history remains with the filter off. [Tower details](tower-anomaly.md).

ATIS presents original ASR, normalization, field status/counts, latest individual and consecutive-capture consensus separately. `?recording=<id>` selects individual history/audio. GET `/api/atis/shadow` exposes the separate candidate queue; GET/POST `/api/atis/validation` supports human references and strict raw-field evaluation, with write-token protection. The validation timer discovers candidates without inference. Parser completeness and consensus agreement do not certify accuracy. [ATIS](atis.md).

Times in Airband use Europe/Helsinki; AIS reception-age hover times are browser-local. Missing/expired audio can retain metadata and review evidence. API controls do not expose public authentication; do not publish session tokens or private observer/map coordinates.

The 10 October inspection obtained 200 from Tower, ATIS, METEOR, schedule and saved-audio endpoints; `/api/state` timed out at 10 s. This is current failure evidence, not a blanket healthy-dashboard claim. The completed four-hour observation also recorded state timeouts. [Audit](current-status.md).

Follow-up at 06:55 UTC / 09:55 Helsinki: three `/api/state` requests returned 200 in 0.135 s each; `/api/atis/shadow` returned 200 in 0.017 s. `/api/atis/validation` and `/api/tower/reviews` each exceeded a 4 s timeout. Recovery of state responses does not invalidate the earlier timeout or certify the slower review endpoints.
