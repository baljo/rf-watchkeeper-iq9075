> Repository layout, 10 October 2026: this preserved guide moved from `AUDIO_WORKFLOW.md`. Relative code/configuration commands below assume the application root as the working directory. Historical deployment/stage paths remain dated evidence; follow [current installation](../installation.md) and topic guides.

> Documentation status, 2026-10-05: Historical September 20 workflow/validation guide. See [current architecture](../architecture.md), [ATIS status](../atis.md) and the [engineering log](../project-log.md) for later verified developments.

# Saved speech on the dashboard

Implemented locally September 20, 2026. EVK inference validation is the next step.

## First EVK test

Install the audio update package, then open http://192.168.178.46:8080 and refresh. Scroll to **Recorded speech lab**, choose **asr_native/control-speech.wav**, leave **English**, listen if desired, and click **Transcribe & summarize**.

Expected: queued -> transcribing -> summarizing -> completed. The transcript should match the familiar English control. Recording duration should be about 7.81 seconds; processing time is separate. A Genie failure is explicitly marked **completed with fallback** and shows a plain transcript summary instead of claiming an LLM result. A failed ASR produces no invented transcript.

The browser plays the recording on the phone/tablet/laptop, independently of the EVK speaker route. Neither replay nor the installer opens an SDR or stops the scheduler. The installer briefly restarts the dashboard and, if it was active, the interpreter. Avoid installing during an existing interpretation run.

## Files and behavior

- `audio_workflow.py` coordinates one job at a time using `asr_offline.py` and `interpret.py`.
- Eligible files: WAV under `asr_native/`, `aviation-fixtures/`, or `recordings/`, mono signed PCM16 at 16 kHz, nonempty and at most 30 seconds. Other WAV files appear disabled with a preparation explanation. This release does not trim or resample automatically; use the existing `scripts/prepare_asr.py` for supported 16/48 kHz mono files.
- Language options: English, Finnish, Swedish, or experimental Finnish+English. This passes language codes to the existing native runner; FI/EN detection quality is not verified yet. No confidence values are invented.
- Results retain `source=replay`. A `workflow_run_id` ties transcript and interpretation to the selected recording.
- ASR retains its existing `asr-runs/` diagnostics. The coordinator keeps stdout/stderr, paired events and result status under `audio-runs/<run-id>/`, with `audio-runs/latest.json` for progress/restart recovery.
- Events also append to the existing dashboard ASR feed. Dashboard-owned transcriptions carry `interpretation_owner=audio_workflow`; the updated background interpreter skips them, preventing duplicate summaries. CLI ASR events still use the background interpreter as before.
- Summary prompts receive transcript/language rather than processing telemetry. Original raw events remain intact. This removes the earlier duration-confusion input, but does not guarantee LLM accuracy.
- The existing Genie config defaults to `/root/genie/qwen3-4b-iq9075/genie_config.absolute.json`; override with dashboard `--genie-config` if needed.
- API: `GET /api/audio` (catalog/status), `GET /api/audio/file/<opaque-id>` (eligible audio only), `POST /api/audio/run` (recording ID/language). Writes require the dashboard session token. No arbitrary paths/commands or file uploads. This remains a trusted-LAN dashboard, not an authenticated internet service.
- Reloading the browser does not cancel a run. Restarting the dashboard interrupts its job; the next start marks that run interrupted rather than silently repeating it. History remains on disk; this first UI displays the latest workflow run.

## Validation and next checkpoint

Local unit/API tests cover successful mocked ASR/Genie, paired event ownership, concurrent request rejection, invalid recordings/paths, failure/fallback, restart recovery and the summary input contract. These are orchestration tests, not Qualcomm inference evidence. Browser inspection confirms the bright layout, real local recording catalog and controls.

Next: run the English control on the EVK, verify one transcript plus one interpretation and browser playback, then repeat an aviation fixture. Inspect intelligibility before trying a noisy RF clip. Verify Finnish/English on labeled real clips later. Live scheduled capture, segmentation, automatic preprocessing, queue history/cancel and Meteor imagery are subsequent slices.

## Installation and rollback

Unzip the small update into a staging directory and run `sh install_audio_update.sh` there. It backs up changed files under `update-backups/`, preserves jobs/config/models/logs, checks Python syntax, restarts affected services and checks `/api/audio` on the current port 8080. On install/health-check failure it restores previously existing files. New unused module/doc files may remain after rollback; existing RF configuration is unchanged.

For manual rollback, copy the backed-up dashboard/interpreter files from the printed backup directory into `/root/rf-watchkeeper/` and restart dashboard/interpreter. Do not restore an old whole-project folder over current recordings or configuration.
