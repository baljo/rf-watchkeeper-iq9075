# Run saved speech through existing VoiceAI and Genie components with dashboard progress and retained evidence. 2026-09-20 20:13 EEST — Thomas Vikström.
"""One bounded offline job at a time; no receiver access or new dependencies."""
import copy
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import threading
import uuid
import wave

from interpret import genie_summary, make_event, fallback_summary

LANGUAGES = {"en", "fi", "sv", "fi,en"}
BUSY = {"queued", "transcribing", "summarizing"}


def now():
    return datetime.now(timezone.utc).isoformat()


def wav_info(path, check_data=False):
    with wave.open(str(path), "rb") as wav:
        duration = wav.getnframes() / wav.getframerate()
        supported = (wav.getnchannels(), wav.getsampwidth(), wav.getframerate(), wav.getcomptype()) == (1, 2, 16000, "NONE")
        if not supported or not 0 < duration <= 30:
            raise ValueError("Requires mono PCM16, 16 kHz, 0–30 seconds. Prepare a short speech clip first.")
        if check_data and len(wav.readframes(wav.getnframes())) != wav.getnframes() * 2:
            raise ValueError("The WAV data is incomplete")
    return round(duration, 3)


class AudioWorkflow:
    def __init__(self, root, event_log, genie_config):
        self.root = Path(root).resolve()
        self.event_log = Path(event_log)
        self.genie_config = Path(genie_config)
        self.lock = threading.RLock()
        self.worker = None
        self.state = {"state": "idle", "detail": "Choose a saved recording to begin.", "source": "replay"}
        self.status_file = self.root / "audio-runs" / "latest.json"
        try:
            previous = json.loads(self.status_file.read_text(encoding="utf-8"))
            if isinstance(previous, dict) and previous.get("state") in BUSY | {"completed", "failed", "interrupted", "completed_with_fallback"}:
                self.state = previous
                if previous["state"] in BUSY:
                    self.state.update(state="interrupted", detail="Dashboard restarted during this run. Select Run again to retry.")
        except (OSError, ValueError):
            pass

    def catalog(self):
        result = {}
        for folder in ("asr_native", "aviation-fixtures", "recordings"):
            base = self.root / folder
            for path in sorted(base.glob("**/*.wav"))[:300]:
                if len(result) >= 200:
                    break
                resolved = path.resolve()
                # Exclude symlinks leading outside this recording directory.
                if base.resolve() not in resolved.parents or self.root not in resolved.parents:
                    continue
                relative = path.relative_to(self.root).as_posix()
                if relative.startswith("recordings/") and "atis" in relative.lower():
                    continue  # Scheduled ATIS belongs to its own reviewed-results panel.
                key = hashlib.sha256(relative.encode()).hexdigest()[:24]
                item = {"id": key, "name": relative, "ready": False}
                try:
                    item.update(audio_seconds=wav_info(resolved), ready=True)
                except (OSError, ValueError, wave.Error, EOFError) as exc:
                    item["reason"] = str(exc)
                result[key] = item
        return result

    def recording(self, key):
        item = self.catalog().get(key)
        if not item or not item["ready"]:
            raise ValueError("Select an available short 16 kHz speech recording.")
        return (self.root / item["name"]).resolve(), item

    def snapshot(self):
        with self.lock:
            result = copy.deepcopy(self.state)
            if "atis" in str(result.get("recording", "")).lower() and (result.get("transcription") or {}).get("model") == "whisper_tiny-qcs9075":
                result.update(state="unreliable", detail="Earlier ATIS replay used the unsuitable tiny model. Use Scheduled ATIS above; recognition still needs review.")
                result["transcription"] = None
                result["interpretation"] = None
            return result

    def update(self, **fields):
        with self.lock:
            self.state.update(fields, updated_at=now())
            self.status_file.parent.mkdir(parents=True, exist_ok=True)
            temporary = self.status_file.with_suffix(".tmp")
            temporary.write_text(json.dumps(self.state, ensure_ascii=False, allow_nan=False), encoding="utf-8")
            temporary.replace(self.status_file)

    def start(self, recording_id, language):
        if language not in LANGUAGES:
            raise ValueError("Unsupported language selection")
        # Reject stale IDs too: never rerun scheduled ATIS with the generic tiny backend.
        for candidate in (self.root / "recordings").glob("**/*.wav"):
            relative = candidate.relative_to(self.root).as_posix()
            if "atis" in relative.lower() and hashlib.sha256(relative.encode()).hexdigest()[:24] == recording_id:
                raise ValueError("Use the Scheduled ATIS panel; the old tiny-model replay is unsuitable for ATIS.")
        path, item = self.recording(recording_id)
        wav_info(path, check_data=True)
        with self.lock:
            if self.worker and self.worker.is_alive():
                raise RuntimeError("A recording is already being processed. Wait for it to finish.")
            run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ-") + uuid.uuid4().hex[:8]
            self.state = {"run_id": run_id, "recording_id": recording_id, "recording": item["name"],
                          "audio_seconds": item["audio_seconds"], "language_requested": language,
                          "source": "replay", "started_at": now()}
            self.update(state="queued", detail="Recording queued for VoiceAI.")
            self.worker = threading.Thread(target=self.run, args=(path, language, run_id), daemon=True)
            self.worker.start()
            return self.snapshot()

    def transcribe(self, path, language, directory):
        command = [sys.executable, str(self.root / "asr_offline.py"), str(path),
                   "--language", language, "--job-id", "dashboard-replay", "--timeout", "180"]
        # Do not pass --event-log: this coordinator owns publication and interpretation.
        with (directory / "asr.stdout").open("wb") as out, (directory / "asr.stderr").open("wb") as err:
            process = subprocess.Popen(command, stdout=out, stderr=err, start_new_session=os.name == "posix")
            try:
                code = process.wait(timeout=210)
            except BaseException:
                if os.name == "posix":
                    try:
                        os.killpg(process.pid, signal.SIGKILL)
                    except ProcessLookupError:
                        pass
                else:
                    process.kill()
                process.wait()
                raise
        if code:
            details = (directory / "asr.stderr").read_text(encoding="utf-8", errors="replace")[-2000:]
            raise RuntimeError("VoiceAI failed: " + (details.strip() or "exit " + str(code)))
        for line in reversed((directory / "asr.stdout").read_text(encoding="utf-8").splitlines()):
            try:
                event = json.loads(line)
            except ValueError:
                continue
            if isinstance(event, dict) and event.get("schema_version") == 1 and event.get("event_type") == "transcription" and event.get("source") == "replay" and event.get("text", "").strip():
                return event
        raise RuntimeError("VoiceAI returned no normalized speech event.")

    def publish(self, directory, event):
        line = json.dumps(event, ensure_ascii=False, allow_nan=False) + "\n"
        for path in (directory / "events.jsonl", self.event_log):
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("a", encoding="utf-8") as stream:
                stream.write(line)

    def run(self, path, language, run_id):
        directory = self.root / "audio-runs" / run_id
        try:
            directory.mkdir(parents=True)
            self.update(state="transcribing", detail="VoiceAI is transcribing the saved recording.")
            event = self.transcribe(path, language, directory)
            event.update(interpretation_owner="audio_workflow", workflow_run_id=run_id)
            self.publish(directory, event)
            transcript = {k: event.get(k) for k in ("text", "language", "model", "backend", "audio_seconds", "processing_seconds", "run_id", "accelerator_verified", "acceleration_note")}
            self.update(state="summarizing", detail="Genie is summarizing the transcript.", transcription=transcript)
            error = None
            try:
                summary = genie_summary(event, self.genie_config)
                backend = "genie-qnn"
            except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as exc:
                summary, backend, error = fallback_summary(event), "deterministic-fallback", str(exc)
            interpretation = make_event(event, summary, backend, error)
            interpretation["workflow_run_id"] = run_id
            self.publish(directory, interpretation)
            self.update(state="completed_with_fallback" if error else "completed",
                        detail="Transcript ready; Genie unavailable, showing a plain transcript summary." if error else "Transcription and Genie summary are ready.",
                        interpretation={"summary": summary, "backend": backend, "backend_error": error}, finished_at=now())
        except Exception as exc:
            self.update(state="failed", detail=str(exc), finished_at=now())
        finally:
            if directory.exists():
                (directory / "result.json").write_text(json.dumps(self.snapshot(), ensure_ascii=False, indent=2), encoding="utf-8")
