# Airband capture and text

Current [RF jobs](rf-jobs.md): Tower 120.950 MHz AM, 30 s every at least 180 s within 05:00–01:30 Europe/Helsinki; ATIS 136.450 MHz AM, 90 s every at least 600 s all day. Periodic FM is disabled. Cadence is approximate on a shared receiver.

## Processing path

1. `job_manager.py` reserves an independent slot after the METEOR guard clears. `atis_pipeline.capture()` obtains the device lock and runs serial-selected `rtl_fm` AM demodulation to 8 kHz mono signed 16-bit WAV. Capture duration/sample evidence are separate from application outcome.
2. `airband_text.activity_regions()` evaluates 20 ms energy frames, sustained candidates, 1.2 s pauses and 200 ms padding, splitting non-overlapping clips up to 28 s. Continuous/noisy audio is conservatively retained. This activity gate is not validated speech/noise discrimination.
3. Preparation removes DC, applies bounded gain, creates 16 kHz clips and pads very short input. Installed `asr_native/voice-ai-ref` uses Qualcomm Whisper small QCS9075 v0.50.2 with English requested. HTP/QNN is requested; actual accelerator placement is unverified.
4. Prior clip JSON is deleted before each model attempt. Valid empty output is `no_speech`; missing/new-output errors are failures, preventing reuse of stale text.
5. Spelling normalization joins Q N H/ILS/ATIS and normalizes niner/fife, retaining raw text/change lists. It does not infer uncertain numbers, callsigns or stations.
6. Tower exposes base transcripts without ATIS-specific Genie. ATIS optionally extracts evidence-checked fields; failure/preemption can leave `partial_success`. Worker and model loops yield to satellite ownership.
7. Tower/ATIS APIs expose pending/interrupted/no_activity/failed/partial_success distinctly. Finalized quiet WAVs and temporary clip WAV/JSON/logs are removed; capture, segmentation, transcript/status metadata survives. Positive/uncertain audio remains.

Capture skips below 512 MiB free. Historical recordings are untouched by the new silence rule. Positive/uncertain archive growth still needs review.

## Evidence and limits

[28-test deployment report](evidence/airband-ops-20261005/report.md): live Tower 29.184 s, retained interval 185.706 s, ATIS 89.088 s. Tower examples were quiet; no positive received Tower utterance was established. Synthetic fixtures prove wiring only. Saved native ATIS replay establishes model operation, not labelled accuracy. APIs returned 200 again during this documentation task. Numeric/weather accuracy, Finnish recognition and accelerator performance remain unverified. See [ATIS](atis.md) and [testing](testing-and-validation.md).


## Tower capture visibility — 2026-10-06

Tower displays the latest 20 capture attempts, including no_activity, at the top of Airband. Times use Europe/Helsinki. Available audio has playback/download controls; expired audio retains capture metadata. Silent live Tower WAVs remain within the latest 20 capture folders; older processed silence is pruned without touching speech, reference, ATIS or satellite material. See [project log](project-log.md).
