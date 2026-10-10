# Architecture and data flow

Reconciled against deployed source/configuration and installed units on **10 October 2026**. [Current status](current-status.md) records evidence and remaining gates. Historical implementation reports are dated evidence, not current defaults.

## Receiver and CPU workloads

`job_manager.py` uses `adaptive_rf.py` and `sdr_demo.scheduler` (deployed at `/root/sdr_demo/scheduler.py`, exported under `backends/sdr_demo/`). The primary scheduler selects V4MAIN01 for Tower, ATIS and AIS. `satellite_schedule.py` guards reservations; METEOR stops/restores ordinary scheduling while holding the device. File-only SatDump decoding does not own the SDR. [Allocation and cadence](rf-jobs.md).

`atis_pipeline.capture()` demodulates Airband through serial-selected `rtl_fm` into 8 kHz mono PCM. Tower screening uses saved acoustic evidence through `tower_classification.py`, independently of speech inference. `tower_anomaly.py` scores window features against the retained model; bounded `tower_anomaly_shadow.py` adds shadow diagnostics and persistent failure state. Human labels live in `evaluation/tower-anomaly/human-review/`; `tower_validation.py` computes cumulative diagnostics. Tower ASR is deferred. [Tower status](tower-anomaly.md).

AIS-catcher supplies dual-channel messages through `ais_collector.py`; `ais_store.py` stores validated target positions/identity and met/hydro observations. `rf_store.py` stores sensor/audio and sample-health data in `data/watchkeeper.db`; the empty root-level database is legacy. Optional 433 reception is disabled. [AIS](ais.md), [433 MHz](433mhz.md).

## ATIS accelerator and derived evidence

Production `atis_pipeline.py` retains full ATIS coverage, prepares high-pass/resampled clips through `atis_shadow.prepare()`, and launches `atis_runtime_device1.py` using the candidate environment. That runtime executes encoder/decoder QNN HTP contexts with `deviceID=1` and cleanup on interruption. Per-clip hash/execution evidence is retained under the capture's `runtime-device1/`. `inference_resource.py` serializes accelerator leases, gives production waiters priority and makes shadow work defer. Shared resource control also covers saved-audio ASR and Genie interpretation.

Original ASR, conservative normalization, `atis_lexicon.py` corrections, `atis_parser.py` fields and optional Genie remain separate. `atis_consensus.py` derives agreement only from consecutive captures anchored to the newest; it cannot outvote disagreement or establish numeric truth. Production publication completes before separate `atis_shadow.py` enqueue. Its durable queue is `data/atis-shadow/jobs.sqlite3`. `atis_validation.py` maintains a distinct human-reference/evaluation database under `data/atis-validation/`. [ATIS details and external dependencies](atis.md).

## Satellite products, retention and presentation

`meteor_pipeline.py` coordinates planning, capture, decode/retry and gated retention. `satellite_capture.py` writes cu8 IQ; `satdump_evk.py` checks pinned runtime/image identity and invokes isolated SatDump. `meteor_frequency.py` provides a bounded recorded-rate offset survey. `meteor_store.py` indexes history/products in `data/watchkeeper-meteor.db`; `meteor_retention.py` classifies raw IQ with protection and execution gates. [METEOR](meteor.md).

`tower_retention.py` provides 30-day Tower audio retention and permanent reference pinning; classification/review metadata survives audio expiry. ATIS review/shadow holds are distinct from permanent pins. [Retention](data-retention.md).

`dashboard.py` serves `dashboard.html` on port 8080, reading histories and controlled audio/image routes. Review POSTs use session tokens. It is a trusted-LAN service without public multi-user authentication. Numeric observer/map centres are public approximations in the export and private locally. [Dashboard](dashboard.md), [privacy](location-privacy.md).

`rf_health.py`/`rf_health_monitor.py` distinguish sample progress from useful application results and perform bounded, reservation-aware recovery. Real reboot acceptance remains unverified. Active processes or successful isolated HTP execution do not establish unattended reliability: the completed integrated run failed. [Recovery](watchdog-and-recovery.md), [utilization evidence](evk-utilization-status-20261009.md).
