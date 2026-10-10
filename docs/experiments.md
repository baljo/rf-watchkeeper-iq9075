# Experiments and evidence

Use the [project log](project-log.md) for dated changes and [workflow](workflow.md) for evidence requirements. Retain original experiment artifacts; a filename or backup timestamp does not establish a successful result.

| Area | Existing evidence reused | Established result/limit |
| --- | --- | --- |
| Saved speech and Qualcomm ASR/Genie | [AUDIO_WORKFLOW.md](../AUDIO_WORKFLOW.md), `asr-runs/`, `audio-runs/`, `aviation-runs/`, `htp-profile-runs/`, `genie-probes/` | Orchestration and experimental outputs; labelled RF accuracy and accelerator placement need explicit validation |
| ATIS | [ATIS_POC.md](../ATIS_POC.md), `atis-stage-20261002/`, `recordings/atis/` | Scheduled experimental capture/processing; weather-field reliability incomplete |
| AIS | `logs/ais-gain-test/`, `logs/ais-gain-test-2min-fixed/`, `ais-validation-stage-20261003/` | Retained gain trials and validation artifacts; do not infer an optimal gain or RF sensitivity solely from message counts |
| METEOR native decoder | [AUTONOMOUS_EVK.md](../AUTONOMOUS_EVK.md), `meteor-native-stage-20261003/` | Documented native offline decode without imagery for September 29 IQ; successful exit alone is insufficient |
| Import/history | `data/satellite-import-stage-20261003/`, `backups/satellite-import-20261003T183401Z/verification.json` | Retained route/20-test verification and unchanged original capture evidence |
| Useful products followed by crash | [patch](evidence/meteor-satdump-crash.patch), [regression](evidence/meteor-crash-regression.json), [53-test output](evidence/meteor-crash-tests.txt) | Three identical product sets; partial success, diagnostics retained, retries suppressed |
| Health/recovery | [RF_HEALTH.md](../RF_HEALTH.md), `rf-health-stage/`, `backups/rf-health-20261005T112419Z/` | Installed sample accounting and successful journal checks; real new-watchdog reboot and long-run reliability not established |

## Gaps requiring new evidence

- Exact original deployment dates for the dashboard, full AIS integration and earliest scheduler revisions; retained files prove existence, not a complete change chronology.
- Second-SDR interference mechanism, measured impact, antenna/cabling/filter/USB inventory and demonstrated remedy.
- Real reboot validation of the new watchdog and post-capture scheduler restoration beyond the observed inspection window.
- Repeatable METEOR quality measures across live passes, RF continuity and a diagnosis/fix for SatDump's underlying SIGSEGV. The classification fix preserves useful output; it does not repair SatDump.
- Airband/ATIS human-labelled accuracy, reliable weather fields, acceleration profiling and completed reviewed alerts.
- Exact time/actor/rationale of every historical sample-rate change; current 256000 configuration and plan are verified, old 1024000 captures remain correctly historical.

Append later findings or corrections to the engineering log; do not fill these gaps using inferred chat history.

## AIS Hydro timing evidence (2026-10-05)

[Measured packet, observation and value-change cadence](ais-hydro-cadence.md): water level at Vaasa/Pietarsaari demonstrates sub-10-minute observation steps; weather sites do not. Frozen raw data, scripts and full statistics retained with the engineering log entry.

## Publication reconciliation — 5 October 2026

The current Airband deployment adds Tower transcription and shortened cadence; recognition accuracy remains open. METEOR scheduler restoration was observed in the later Airband report and publication inspection, closing that particular earlier observation gap. This does not establish all-pass restoration or real reboot acceptance. The earlier reviewed cleanup is complete; automatic deletion gates remain disabled. See [testing](testing-and-validation.md) and [retention](data-retention.md).

## Reconciliation — 10 October 2026

Older Tower-transcription and accelerator-placement-unverified summaries above describe earlier experiments. Current Tower ASR is deferred; acoustic screening/AD shadow and human review are separate. The corrected device1 HTP path has isolated execution evidence and a passing scoped overlap demonstration, but completed integrated acceptance failed. [Definitive utilization status](evk-utilization-status-20261009.md), [current ATIS](atis.md), [Tower](tower-anomaly.md).

Outstanding experiments: native/DMA/Genie repair plus a new passing unattended run; full workload profiling and drop/preemption evidence; Tower backlog capacity/labelled calibration; numeric/Finnish/reference accuracy; SatDump underlying SIGSEGV and live-image repeatability; optional second-SDR interference; fresh installation and real watchdog reboot acceptance. Source export is not completion of those experiments.
