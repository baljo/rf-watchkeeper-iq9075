# Architecture

Verified by installed source, unit definitions and read-only APIs on 2026-10-05. See [project log](project-log.md) for dated milestones and [workflow](workflow.md) for recording changes.

- `job_manager.py` delegates receiver work to `/root/sdr_demo/scheduler.py`. The primary scheduler owns V4MAIN01 for ordinary jobs; the separate sensor unit selects 43300001. [RF jobs](rf-jobs.md) describes scheduling and handoff.
- `rf_store.py` stores sensor/audio records in `data/watchkeeper.db`; `ais_collector.py` and `ais_store.py` supply AIS targets and met/hydro observations. The empty root-level `watchkeeper.db` is a legacy file, not the live database.
- `dashboard.py` serves `dashboard.html` and controlled APIs on port 8080 through `rf-watchkeeper-dashboard.service`. Current routes include `/api/state`, `/api/nexus/history`, `/api/audio`, `/api/atis`, `/api/meteor` and `/api/meteor/schedule`. Image files are served through `/api/meteor/image/<id>`.
- `audio_workflow.py`, `asr_offline.py` and `interpret.py` coordinate saved speech with retained diagnostics. Reuse [AUDIO_WORKFLOW.md](../AUDIO_WORKFLOW.md), a dated implementation/validation guide.
- `atis_pipeline.py` and `atis_view.py` provide experimental recorded ATIS processing and dashboard data; see [ATIS status](atis.md).
- `meteor_pipeline.py` coordinates planning, capture, decoding and opt-in retention. `satellite_capture.py` records IQ; `satdump_evk.py` runs the isolated decoder. `meteor_store.py` keeps product history in `data/watchkeeper-meteor.db`. See [METEOR](meteor.md).
- `rf_health.py` and `rf_health_monitor.py` record sample evidence and guarded recovery in additive health tables in the main database. See [reliability](reliability.md) and the preserved [RF_HEALTH.md](../RF_HEALTH.md).

Persistent evidence is retained in `logs/`, `sensor-logs/`, `recordings/`, `data/meteor-auto/`, experiment stages and `backups/`. The dashboard is a trusted-LAN service; existing saved-audio write operations require a session token, not internet-grade user authentication.

At the 2026-10-05 11:44 UTC inspection, the main database contained 15,245 Nexus measurements, 42 AIS targets and 18,762 met/hydro rows; the METEOR database contained nine passes and 79 image rows. Counts are an observation, not fixed requirements. See [inspection evidence](evidence/documentation-inspection.json).

## Current Airband/publication reconciliation — 5 October 2026

Tower is now recorded/transcribed through the common Airband pipeline, not playback-only. `/api/tower` and `/api/tower/audio` join the ATIS routes. Current cadence, disabled FM and capped AIS background dwell are authoritative in [RF jobs](rf-jobs.md). [Dashboard](dashboard.md) gives the full route inventory; [operation](operation.md) describes installed systemd services/timers; [installation](installation.md) identifies external prerequisites.

Retention is policy-classified and execution-gated, with the separately authorized reviewed cleanup recorded in [data retention](data-retention.md). The empty canonical GitHub repository was reconciled through a local checkout because EVK had neither Git metadata nor Git executable. Runtime source hashes match the read-only [publication inspection](evidence/publication-inspection.json); exported service definitions are snapshots, not runtime changes.
