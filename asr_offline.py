# Transcribe recorded speech through Qualcomm VoiceAI, retain runtime evidence and optionally publish a normalized dashboard event. 2026-09-17 20:30 EEST — Thomas Vikström.
"""Offline experiment; requires the existing Watchkeeper recorded.py module."""
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import platform
import re
import subprocess
import sys
import time
import uuid
import wave

from recorded import emit, save, sha256

ROOT = Path(__file__).resolve().parent


def normalize_result(raw, elapsed, duration, input_path, run_id):
    if not isinstance(raw, dict) or not isinstance(raw.get("text"), str):
        raise ValueError("Backend result lacks transcription text")
    # The reference runner prefixes each segment even when its transcript is empty.
    text = re.sub(r"\[\d+ms\s*-\s*\d+ms\]", " ", raw["text"]).strip()
    if not text:
        raise ValueError("Backend returned no transcription; inspect runtime.log")
    return {
        "event_type": "transcription", "job_id": "airband_offline",
        "decoder": "qualcomm_voiceai", "model": "whisper_tiny-qcs9075",
        "backend": "VoiceAI ASR Community 2.7.1.0 / QNN",
        "accelerator_requested": "HTP / Hexagon V73",
        "accelerator_verified": False,
        "acceleration_note": "HTP context models requested; runtime evidence must be reviewed before claiming accelerator execution.",
        "text": text, "language": raw.get("language"),
        "processing_seconds": elapsed, "audio_seconds": duration,
        "real_time_factor": elapsed / duration,
        "input_file": str(input_path), "input_sha256": sha256(input_path),
        "run_id": run_id, "raw": raw,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("wav", type=Path)
    parser.add_argument("--bundle", type=Path, default=ROOT / "asr_native")
    parser.add_argument("--language", default="en")
    parser.add_argument("--job-id", default="airband_offline")
    parser.add_argument("--frequency", type=int, help="Recording frequency in Hz, when known")
    parser.add_argument("--timeout", type=float, default=180)
    parser.add_argument("--inspect-runtime", action="store_true", help="Collect mapped backend libraries and diagnostic evidence")
    parser.add_argument("--event-log", type=Path, help="Append the normalized transcription to a separate JSONL dashboard feed")
    args = parser.parse_args(argv)
    run = None
    try:
        if platform.system() != "Linux" or platform.machine() not in ("aarch64", "arm64"):
            raise ValueError("Run this ARM64 experiment on the EVK")
        if not 0 < args.timeout <= 3600:
            raise ValueError("Timeout must be between 0 and 3600 seconds")
        if args.frequency is not None and args.frequency <= 0:
            raise ValueError("Frequency must be positive")
        source = args.wav.resolve()
        with wave.open(str(source), "rb") as wav:
            if (wav.getnchannels(), wav.getsampwidth(), wav.getframerate(), wav.getcomptype()) != (1, 2, 16000, "NONE"):
                raise ValueError("Input must be mono 16 kHz signed 16-bit PCM WAV")
            duration = wav.getnframes() / 16000
        if not 0 < duration <= 30:
            raise ValueError("Use a short speech clip of 30 seconds or less for this first test")
        bundle = args.bundle.resolve()
        for name in ("voice-ai-ref", "model/encoder_model_htp.bin", "model/decoder_model_htp.bin", "model/vocab.bin", "model/libnnvad_model.so"):
            if not (bundle / name).is_file():
                raise ValueError("Missing bundle file: " + str(bundle / name))
        run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ-") + uuid.uuid4().hex[:8]
        run = ROOT / "asr-runs" / run_id
        run.mkdir(parents=True)
        env = os.environ.copy()
        env["LD_LIBRARY_PATH"] = str(bundle / "lib") + ":/usr/lib" + (":" + env["LD_LIBRARY_PATH"] if env.get("LD_LIBRARY_PATH") else "")
        command = [str(bundle / "voice-ai-ref"), "-m", str(bundle / "model"), "-f", str(source), "-o", str(run / "result.json"), "-l", args.language, "-t", "transcribe"]
        save(run / "request.json", {"command": command, "input_sha256": sha256(source), "mode": "offline", "timeout": args.timeout,
                                   "runner_sha256": sha256(bundle / "voice-ai-ref"), "language": args.language,
                                   "job_id": args.job_id, "frequency_hz": args.frequency,
                                   "inspect_runtime": args.inspect_runtime})
        samples = {"libraries": set(), "maps_samples": 0, "read_errors": set()}
        if args.inspect_runtime:
            import asr_evidence
        start = time.monotonic()
        with (run / "runtime.log").open("wb") as log:
            with subprocess.Popen(command, env=env, stdout=log, stderr=subprocess.STDOUT) as process:
                try:
                    code = (asr_evidence.observe(process, args.timeout, samples) if args.inspect_runtime
                            else process.wait(timeout=args.timeout))
                except BaseException:
                    process.kill()
                    process.wait()
                    raise
        elapsed = time.monotonic() - start
        if args.inspect_runtime:
            evidence = asr_evidence.report(samples, (run / "runtime.log").read_text(encoding="utf-8", errors="replace"), code)
            save(run / "runtime-evidence.json", evidence)
            print("Runtime evidence: " + str(run / "runtime-evidence.json"), file=sys.stderr)
        if code:
            raise RuntimeError("VoiceAI exited with code " + str(code))
        raw = json.loads((run / "result.json").read_text(encoding="utf-8"))
        event = normalize_result(raw, elapsed, duration, source, run_id)
        event["job_id"] = args.job_id
        event["language_requested"] = args.language
        event["runtime_inspection_enabled"] = args.inspect_runtime
        if args.frequency is not None:
            event["frequency_hz"] = args.frequency
        with (run / "events.jsonl").open("a", encoding="utf-8") as stream:
            emit(stream, event)
        if args.event_log:
            args.event_log.parent.mkdir(parents=True, exist_ok=True)
            with args.event_log.open("a", encoding="utf-8") as stream:
                emit(stream, event)
        print("Runtime diagnostics: " + str(run / "runtime.log"), file=sys.stderr)
        return 0
    except (OSError, ValueError, RuntimeError, subprocess.TimeoutExpired, wave.Error) as error:
        if run:
            save(run / "failure.json", {"error": str(error), "asr_verified": False})
        print("ASR test failed: " + str(error), file=sys.stderr)
        if run:
            print("Inspect: " + str(run / "runtime.log"), file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
