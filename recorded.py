# Capture RF samples and replay recorded IQ/audio into isolated normalized Watchkeeper test events. 2026-09-16 23:03 EEST — Thomas Vikström.
"""Recorded-signal tests; no third-party Python packages. See RECORDED.md."""
import argparse
from array import array
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import signal
import subprocess
import sys
import threading
import time
import uuid
import wave

import watchkeeper
from job_manager import demo

ROOT = Path(__file__).resolve().parent
STOP = threading.Event()


def sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1048576), b""):
            digest.update(chunk)
    return digest.hexdigest()


def save(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")


def emit(stream, event):
    event = dict(event, schema_version=1, source="replay",
                 received_at=datetime.now(timezone.utc).isoformat())
    line = json.dumps(event, ensure_ascii=False, allow_nan=False)
    stream.write(line + "\n")
    stream.flush()
    print(line, flush=True)


def run_process(argv, output, diagnostics, timeout, capture_duration=None):
    """File-backed output avoids pipe deadlocks; cleanup is bounded even on Ctrl+C."""
    process = subprocess.Popen(argv, stdout=output, stderr=diagnostics)
    start = time.monotonic()
    try:
        while process.poll() is None:
            if STOP.is_set():
                raise RuntimeError("Cancelled")
            elapsed = time.monotonic() - start
            if capture_duration is not None and elapsed >= capture_duration:
                return
            if elapsed >= timeout:
                raise RuntimeError("Backend timed out")
            STOP.wait(0.05)
        if process.returncode != 0:
            raise RuntimeError("Backend exited with code {}; see diagnostics.log".format(process.returncode))
        if capture_duration is not None:
            raise RuntimeError("Audio receiver exited before the capture duration")
    finally:
        if process.poll() is None:
            process.terminate()
        try:
            process.wait(timeout=3)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=3)


def audio_metrics(path):
    with wave.open(str(path), "rb") as audio:
        channels, width, rate, frames = audio.getnchannels(), audio.getsampwidth(), audio.getframerate(), audio.getnframes()
        if width != 2 or channels not in (1, 2) or audio.getcomptype() != "NONE" or not frames:
            raise ValueError("Use a nonempty mono/stereo 16-bit PCM WAV")
        count, energy, peak = 0, 0, 0
        while True:
            block = audio.readframes(8192)
            if not block:
                break
            samples = array("h")
            samples.frombytes(block)
            if sys.byteorder != "little":
                samples.byteswap()
            count += len(samples)
            energy += sum(value * value for value in samples)
            peak = max(peak, max(abs(value) for value in samples))
        if count != frames * channels:
            raise ValueError("Truncated WAV data")
        return {"sample_rate_hz": rate, "channels": channels, "frames": frames,
                "duration_seconds": frames / rate, "rms": math.sqrt(energy / count) / 32768,
                "peak": peak / 32768, "sample_format": "s16le"}


def capture(args):
    if not sys.platform.startswith("linux"):
        raise ValueError("Live recording requires the Linux EVK")
    args.directory.mkdir(parents=True, exist_ok=False)  # never overwrite a reference recording
    frequency = args.frequency or {"nexus": 433920000, "fm": 98400000, "am": 120950000}[args.kind]
    if args.kind == "nexus" and frequency != watchkeeper.FREQUENCY:
        raise ValueError("Nexus capture currently requires 433920000 Hz")
    started = datetime.now(timezone.utc).isoformat()
    with watchkeeper.device_lock(args.device):
        with (args.directory / "diagnostics.log").open("wb") as diagnostics:
            if args.kind == "nexus":
                binary = watchkeeper.find_decoder(args.rtl433)
                if not binary:
                    raise ValueError("rtl_433 not found")
                path = args.directory / "nexus_433.92M_250k.cu8"
                argv = watchkeeper.command(binary, args.device, args.ppm, args.gain)
                argv += ["-T", str(args.seconds), "-w", str(path.resolve())]
                with (args.directory / "raw-events.jsonl").open("wb") as output:
                    run_process(argv, output, diagnostics, args.seconds + 20)
                rate, fmt = 250000, "cu8"
                if not path.exists() or path.stat().st_size < 2 or path.stat().st_size % 2:
                    raise ValueError("Capture did not produce complete CU8 IQ pairs")
            else:
                path = args.directory / (args.kind + ".wav")
                rate, fmt = (48000 if args.kind == "fm" else 24000), "wav-s16le"
                job = {"kind": args.kind, "frequency_hz": frequency,
                       "gain_db": args.gain, "sample_rate": rate}
                argv, _ = demo.commands({"device": args.device, "ppm": args.ppm}, job)
                pcm = args.directory / "capture.s16"
                with pcm.open("wb") as output:
                    run_process(argv, output, diagnostics, args.seconds + 10, args.seconds)
                size = pcm.stat().st_size
                if size < 2:
                    raise ValueError("No audio captured")
                with wave.open(str(path), "wb") as wav, pcm.open("rb") as raw:
                    wav.setnchannels(1)
                    wav.setsampwidth(2)
                    wav.setframerate(rate)
                    remaining = size - size % 2
                    while remaining:
                        chunk = raw.read(min(remaining, 1048576))
                        wav.writeframesraw(chunk)
                        remaining -= len(chunk)
                pcm.unlink()
    save(args.directory / "capture.json", {"schema_version": 1, "kind": args.kind,
         "captured_at": started, "file": path.name, "sha256": sha256(path),
         "frequency_hz": frequency, "sample_rate_hz": rate, "sample_format": fmt,
         "requested_seconds": args.seconds, "device": args.device, "ppm": args.ppm,
         "gain_db": args.gain, "command": argv})
    print("Recording saved: " + str(path))


def replay(args):
    source = args.file.resolve(strict=True)
    if args.kind == "nexus" and source.suffix.lower() != ".cu8":
        raise ValueError("Nexus IQ replay expects unsigned 8-bit interleaved IQ (.cu8)")
    if args.kind == "nexus" and (source.stat().st_size == 0 or source.stat().st_size % 2):
        raise ValueError("IQ input must contain complete CU8 sample pairs")
    identity = sha256(source)
    backend = watchkeeper.find_decoder(args.rtl433) if args.kind == "nexus" else None
    if args.kind == "nexus" and not backend:
        raise ValueError("rtl_433 not found")
    # Auto-generated isolated directories: live events/status are never opened.
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid.uuid4().hex[:8]
    output = ROOT / "replay-runs" / run_id
    output.mkdir(parents=True)
    report = {"schema_version": 1, "run_id": run_id, "source": "replay", "input_file": str(source),
              "input_sha256": identity, "kind": args.kind, "sample_rate_hz": args.sample_rate if backend else None,
              "backend": str(backend) if backend else "python-wave-pcm",
              "backend_sha256": sha256(Path(backend)) if backend else None, "iterations": []}
    reference = json.loads(args.expect.read_text(encoding="utf-8")) if args.expect else None
    try:
        with (output / "events.jsonl").open("w", encoding="utf-8") as stream:
            for iteration in range(1, args.repeat + 1):
                if STOP.is_set():
                    raise RuntimeError("Cancelled")
                start = time.monotonic()
                semantic = []
                metadata = {"run_id": run_id, "iteration": iteration, "input_sha256": identity,
                            "input_file": source.name}
                if backend:
                    # Prefix explicitly overrides any conflicting rate/type in the filename.
                    input_spec = "cu8:{}sps:433.92M:".format(args.sample_rate) + str(source)
                    argv = [backend, "-c", "0", "-r", input_spec, "-R", "19", "-F", "json"]
                    with (output / "decoded-{}.jsonl".format(iteration)).open("wb") as raw, \
                            (output / "diagnostics.log").open("ab") as diagnostics:
                        run_process(argv, raw, diagnostics, args.timeout)
                    with (output / "decoded-{}.jsonl".format(iteration)).open(encoding="utf-8") as raw:
                        for line in raw:
                            if not line.strip():
                                continue
                            event = watchkeeper.normalize(json.loads(line), source="replay")
                            if event is not None:
                                semantic.append({k: event[k] for k in ("event_type", "model", "device_key",
                                    "sensor_id", "channel", "temperature_c", "humidity_pct", "battery_ok", "frequency_hz")})
                                event["replay"] = metadata
                                emit(stream, event)
                    if len(semantic) < args.min_events:
                        raise ValueError("Only {} Nexus events; expected at least {}. Capture a transmission first.".format(len(semantic), args.min_events))
                else:
                    metrics = audio_metrics(source)
                    event = dict(metrics, event_type="audio_recording", recording_kind=args.kind,
                                 backend="python-wave-pcm", acceleration="none", replay=metadata)
                    if args.play:
                        with (output / "diagnostics.log").open("ab") as diagnostics:
                            run_process(["aplay", str(source)], subprocess.DEVNULL, diagnostics,
                                        max(args.timeout, metrics["duration_seconds"] + 10))
                    emit(stream, event)
                    semantic.append(dict(metrics, event_type="audio_recording", recording_kind=args.kind))
                digest = hashlib.sha256(json.dumps(semantic, sort_keys=True, allow_nan=False).encode()).hexdigest()
                report["iterations"].append({"iteration": iteration, "events": len(semantic),
                    "semantic_sha256": digest, "processing_seconds": time.monotonic() - start})
            results = report["iterations"]
            if len({r["semantic_sha256"] for r in results}) != 1:
                raise ValueError("Repeated runs produced different normalized results")
            if reference:
                if any(reference.get(k) != report[k] for k in ("input_sha256", "kind", "sample_rate_hz")):
                    raise ValueError("Expected report refers to different input or settings")
                if reference.get("status") != "passed" or not reference.get("iterations"):
                    raise ValueError("Expected report must be a successful baseline")
                if results[0]["semantic_sha256"] != reference["iterations"][0]["semantic_sha256"]:
                    raise ValueError("Normalized output does not match the baseline")
            report["status"] = "passed"
            emit(stream, {"event_type": "replay_result", "status": "passed", "replay": {"run_id": run_id},
                          "iterations": len(results), "events_per_iteration": results[0]["events"]})
    except Exception as error:
        report["status"], report["error"] = "failed", str(error)
        with (output / "events.jsonl").open("a", encoding="utf-8") as stream:
            emit(stream, {"event_type": "replay_result", "status": "failed", "reason": str(error),
                          "replay": {"run_id": run_id}})
        raise
    finally:
        save(output / "report.json", report)
        print("Report: " + str(output / "report.json"), file=sys.stderr)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="action", required=True)
    cap = sub.add_parser("capture")
    cap.add_argument("kind", choices=("nexus", "fm", "am"))
    cap.add_argument("directory", type=Path)
    cap.add_argument("--seconds", type=float, default=90)
    cap.add_argument("--device", default="0")
    cap.add_argument("--frequency", type=int)
    cap.add_argument("--ppm", type=int, default=0)
    cap.add_argument("--gain", type=float)
    cap.add_argument("--rtl433")
    rep = sub.add_parser("replay")
    rep.add_argument("kind", choices=("nexus", "fm", "airband"))
    rep.add_argument("file", type=Path)
    rep.add_argument("--rtl433")
    rep.add_argument("--sample-rate", type=int, default=250000)
    rep.add_argument("--repeat", type=int, default=2)
    rep.add_argument("--min-events", type=int, default=1)
    rep.add_argument("--timeout", type=float, default=180)
    rep.add_argument("--expect", type=Path)
    rep.add_argument("--play", action="store_true", help="Play WAV through aplay as well as checking it")
    args = parser.parse_args(argv)
    STOP.clear()
    for sig in (signal.SIGINT, signal.SIGTERM):
        signal.signal(sig, lambda *_: STOP.set())
    try:
        if args.action == "capture":
            if not math.isfinite(args.seconds) or args.seconds <= 0 or args.seconds > 600:
                raise ValueError("Capture duration must be between 0 and 600 seconds")
            if args.gain is not None and not math.isfinite(args.gain):
                raise ValueError("Gain must be finite")
            capture(args)
        else:
            if args.repeat < 1 or args.min_events < 1 or args.sample_rate < 1 or not math.isfinite(args.timeout) or args.timeout <= 0:
                raise ValueError("Repeat, minimum events, sample rate and timeout must be positive")
            replay(args)
        return 0
    except (OSError, ValueError, RuntimeError, wave.Error, subprocess.TimeoutExpired) as error:
        print("Recorded test failed: " + str(error), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
