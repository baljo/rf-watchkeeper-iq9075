> Documentation status, 2026-10-05: Historical October 2 proof-of-concept record. See [current Airband/ATIS status](docs/atis.md) for installed routes and remaining validation. The capability remains experimental/incomplete.

# ATIS development — October 2, 2026

Installed on the Dragonwing EVK in `/root/rf-watchkeeper`.

The V4 rotation now includes a low-priority Vaasa ATIS job at 136.450 MHz: AM, 8 kHz demodulator output, 49.6 dB tuner gain, 90-second capture, at most once every 1,800 seconds. Existing FM, Tower and AIS job settings are preserved. All those jobs receive their normal slot before ATIS. The interval is checked at cycle boundaries, so it is approximate rather than aligned to :00 and :30. Missed satellite slots are skipped, without catch-up captures.

Satellite services and timer definitions are unchanged. ATIS checks active METEOR/satellite services and upcoming satellite timers before capture and periodically during it. It needs the complete capture duration plus a five-minute buffer. Failure to inspect the schedule blocks ATIS. The existing satellite capture stops the normal V4 scheduler, which now also stops an in-progress ATIS capture. Incomplete captures are retained with an interrupted label and excluded from processing.

Automatic processing uses the existing isolated Qualcomm Whisper small QCS9075 v0.50.2 model and the existing Genie/Qwen3-4B QNN configuration. It runs at reduced CPU/I/O priority, defers before satellite windows and interrupts model subprocesses if satellite work becomes due. It avoids starting when the existing ASR/Genie executables are already running; this is a best-effort busy check, not a shared inference lock with the dashboard.

The original WAV is retained. A DC-removed, level-adjusted listening copy and overlapping 28-second 16 kHz inputs are generated. Raw ASR outputs and runtime logs are retained. Empty ASR and SPECTROGRAM FAIL are treated as failures. Genie receives transcript content without runtime metadata. Structured fields require supporting quotes in the ASR text and relevant labels. All values remain tentative: a quote supports the model's source, not the correctness of the ASR or field assignment. Malformed output is marked failed rather than repaired or presented as a valid result.

Outputs live in `/root/rf-watchkeeper/recordings/atis/<UTC timestamp>/`:

- `raw.wav`: original captured AM audio.
- `listen.wav`: listening copy.
- `capture.json`: settings, duration and completion status.
- `transcript.json`: overlapping experimental ASR segments.
- `interpretation.json`: tentative Genie fields, uncertainty or failure.
- `processed.json`: processing status and content hash.
- `clip-*.json`, `clip-*.log`, `genie.log`: underlying evidence.

`recordings/atis/latest.json` points to the latest processed capture and lists possible field changes. Changes are explicitly unverified and can reflect transcription variation. Results are not yet integrated into a new dashboard view or automatic notifications.

Eight ATIS tests cover active/imminent satellite blocking, failed schedule inspection, avoiding the earlier service-description false match, persisted intervals, protected original audio, bounded model inputs, and rejection of unsupported fields. Existing scheduler tests passed: seven passed, one skipped on Windows. Saved-audio trials ran ASR and Genie on the EVK. The installed tiny model failed to transcribe the improved audio; the isolated small model recovered meaningful content but unreliable weather numbers. Full HTP graph placement and end-to-end acceleration have not been profiled; successful Qualcomm execution and configured QnnHtp alone are not definitive accelerator verification.

Installation backup: `/root/rf-watchkeeper/update-backups/atis-20261002T190557Z/`.

The first scheduled capture was verified at 22:08:58 EEST on October 2. It produced 89.088 seconds of audio, followed by a saved Qualcomm small transcript and an experimental Genie interpretation. FM and Tower reception resumed while model processing ran. The retained interpretation suggested information Uniform, time 1850 and runway 16; all other fields were left missing. The raw transcript also contains unreliable numeric sequences and inconsistent transition-level wording, so missing fields and ASR hallucination handling remain development work. Completed processing was saved at 22:11:16 EEST. Both new/modified services and the existing sensor, dashboard and interpreter services remained active. No satellite unit files changed.

Next work: listen-label a short reference cycle; score information identifier, runway, wind, cloud and QNH individually against human labels and the PC small.en baseline; improve weather segmentation; profile QNN graph execution and latency on the same inputs; add the dashboard ATIS panel, storage retention, and reviewable change alerts. No aviation decision should depend on tentative automatic numbers.
