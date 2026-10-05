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
