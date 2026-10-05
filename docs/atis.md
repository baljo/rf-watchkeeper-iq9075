# Vaasa ATIS

The deployed workload records **136.450 MHz AM**, approximately **90 s every 10 minutes**, all day, requesting 8 kHz PCM and 49.6 dB gain. Shared scheduling/METEOR can delay or skip a slot. [Airband](airband.md) describes the common capture, segmentation, ASR, normalization and cleanup pipeline.

ATIS attempts optional Genie/Qwen3-4B interpretation after valid base ASR. Tentative field evidence must match transcript text and field labels; weather numbers remain unverified. Current Genie failures leave valid base transcripts as `partial_success`. Retained live deployment validation measured 89.088 s and partial success.

`/api/atis` and `/api/atis/audio` expose current processing/review state and retained audio. Quiet finalized results can have metadata without audio. Original ASR, normalization and tentative interpretation remain distinguishable.

[ATIS_POC.md](../ATIS_POC.md) preserves the October 2 snapshot (older 30-minute interval and pre-dashboard state). [Earlier processing evidence](evidence/airband-text-20261005/completion-report.md) precedes the [current operating report](evidence/airband-ops-20261005/report.md). Current scheduling follows the latter.

Open validation: labelled reference cycles, numeric/field accuracy, Finnish/language selection, QNN execution profiling, reviewed change alerts and positive archive sizing. This remains experimental aviation-information monitoring.
