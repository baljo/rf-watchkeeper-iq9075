# Airband capture and Tower screening

Inspected 10 October 2026. [RF jobs](rf-jobs.md) is the scheduling reference: Tower **120.950 MHz AM**, 15 s probes targeting 60 s starts, 10 s quiet tail, 75 s limit, **07:00–23:00 Europe/Helsinki**; ATIS **136.450 MHz AM**, 90 s every at least 600 s all day. METEOR ownership can delay/skip either. FM reference is disabled.

`atis_pipeline.capture()` takes the serial-selected receiver lock and runs `rtl_fm` into 8 kHz mono signed 16-bit WAV. Capture/sample status and application outcome remain distinct. Capture skips below 512 MiB free. Tower's `TowerHold` examines DC-free 20 ms RMS frames with 240 ms sustained activity over RMS 40; noise can extend a hold, so energy is not proof of speech.

Tower no longer runs automatic ASR or ATIS-specific interpretation. `tower_classification.py` uses saved activity/segmentation evidence to classify `voice_candidate`, `probably_non_voice` or `uncertain`; these are listening-review suggestions, not transcript accuracy. It writes separate classification metadata while preserving original captures and historical transcripts. `atis_pipeline.py` scans Tower captures for this classification independently of ATIS inference.

The automatic AD worker is **shadow diagnostics**, separate from capture/screening. The optional review filter requires a completed valid finite AD score **at or above its recorded threshold** and no saved human label. Acoustic voice/uncertain classifications cannot bypass AD. It returns the newest 20 eligible records; disabling the filter shows inclusive latest history. [AD failure handling, labels and limitations](tower-anomaly.md).

Tower audio uses **30-day retention with permanent pins**, not a latest-20 deletion window. Latest 20 is a display limit. Historical already-missing WAVs are not recreated; metadata remains visible. [Retention](data-retention.md).

ATIS uses full-message device1 HTP inference, conservative parsing and separate shadow/validation queues; see [ATIS](atis.md). Original ASR and normalized/derived outputs remain identifiable. Missing fresh model output is failure; retained text must not be silently reused.

Earlier [5 October operating report](evidence/airband-ops-20261005/report.md) records Tower 29.184 s, interval 185.706 s and ATIS 89.088 s. Those quiet examples and old transcription/05:00–01:30/latest-20 retention behavior are historical. Current poor Tower audio led to ASR deferral; no new accuracy or RF sensitivity claim is made by this audit.
