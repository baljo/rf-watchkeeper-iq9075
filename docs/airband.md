# Airband capture and Tower screening

## Tower/ATIS retention and Rally suspension — 14 October 2026

Ordinary Tower audio now expires after **14 days**, ATIS after **7 days**, from the original UTC recording ID. Review queues and terminal processing failures do not prevent expiry; permanent pins/references and genuine running jobs remain protected. Metadata/databases and ASR outputs remain. The daily `rf-watchkeeper-audio-retention.timer` runs at 02:30 UTC and stays operational when acquisition is suspended. This supersedes older 30-day Tower and unbounded ATIS statements below; satellite cleanup policy remains unchanged.

`python3 acquisition_control.py suspend|status|resume` in `/root/rf-watchkeeper` manages acquisition and processing services/timers, including legacy satellite schedules, with persistent start guards and restoration of their saved state. Dashboard and both retention timers remain available; dashboard shows **RF Watchkeeper suspended**. Implemented, deployed and controlled live verification passed; acquisition was restored to enabled. Controlled deletion removed exactly 521 expired ATIS WAVs / 733,579,616 bytes, with Tower/ATIS metadata and databases unchanged. 37 focused regression tests and 101 satellite tests passed. Old Tower display/queue fixture failures reproduce with the previous implementation. Reboot and later unattended daily cleanup remain unverified. Three historical damaged-metadata Tower folders remain fail-closed (225,324 audio bytes).

See [operator commands and rollback](acquisition-mode.md), [configuration and retention details](../config/examples/audio-retention-policy.md), and [completion evidence](evidence/retention-suspend-20261014/completion.md).

Inspected 10 October 2026. [RF jobs](rf-jobs.md) is the scheduling reference: Tower **120.950 MHz AM**, 15 s probes targeting 60 s starts, 10 s quiet tail, 75 s limit, **07:00–23:00 Europe/Helsinki**; ATIS **136.450 MHz AM**, 90 s every at least 600 s all day. METEOR ownership can delay/skip either. FM reference is disabled.

`atis_pipeline.capture()` takes the serial-selected receiver lock and runs `rtl_fm` into 8 kHz mono signed 16-bit WAV. Capture/sample status and application outcome remain distinct. Capture skips below 512 MiB free. Tower's `TowerHold` examines DC-free 20 ms RMS frames with 240 ms sustained activity over RMS 40; noise can extend a hold, so energy is not proof of speech.

Tower no longer runs automatic ASR or ATIS-specific interpretation. `tower_classification.py` uses saved activity/segmentation evidence to classify `voice_candidate`, `probably_non_voice` or `uncertain`; these are listening-review suggestions, not transcript accuracy. It writes separate classification metadata while preserving original captures and historical transcripts. `atis_pipeline.py` scans Tower captures for this classification independently of ATIS inference.

The automatic AD worker is **shadow diagnostics**, separate from capture/screening. The optional review filter requires a completed valid finite AD score **at or above its recorded threshold** and no saved human label. Acoustic voice/uncertain classifications cannot bypass AD. It returns the newest 20 eligible records; disabling the filter shows inclusive latest history. [AD failure handling, labels and limitations](tower-anomaly.md).

Tower audio uses **30-day retention with permanent pins**, not a latest-20 deletion window. Latest 20 is a display limit. Historical already-missing WAVs are not recreated; metadata remains visible. [Retention](data-retention.md).

ATIS uses full-message device1 HTP inference, conservative parsing and separate shadow/validation queues; see [ATIS](atis.md). Original ASR and normalized/derived outputs remain identifiable. Missing fresh model output is failure; retained text must not be silently reused.

Earlier [5 October operating report](evidence/airband-ops-20261005/report.md) records Tower 29.184 s, interval 185.706 s and ATIS 89.088 s. Those quiet examples and old transcription/05:00–01:30/latest-20 retention behavior are historical. Current poor Tower audio led to ASR deferral; no new accuracy or RF sensitivity claim is made by this audit.
