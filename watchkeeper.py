# Normalize Nexus-TH events for standalone or bounded scheduler reception. 2026-09-16 22:52 EEST — Thomas Vikström.
"""RF Watchkeeper v1: Python 3.8+, standard library only; Linux live mode."""
import argparse
import contextlib
from datetime import datetime, timezone
import json
import logging
import math
import os
from pathlib import Path
import selectors
import shlex
import shutil
import signal
import subprocess
import sys
import threading
import time

import rf_store

LOG = logging.getLogger("watchkeeper")
FREQUENCY = 433920000


def number(event, key, low, high, integer=False):
    value = event.get(key)
    if (isinstance(value, bool) or not isinstance(value, (int, float))
            or not math.isfinite(value) or not low <= value <= high
            or (integer and int(value) != value)):
        raise ValueError("Invalid or missing " + key)
    return int(value) if integer else float(value)


def normalize(event, source="live"):
    """One schema for accepted observations; decoder time is preserved unmodified."""
    if not isinstance(event, dict):
        raise ValueError("Expected a JSON object")
    if event.get("model") != "Nexus-TH":
        return None
    sensor_id = number(event, "id", 0, 255, True)
    channel = number(event, "channel", 1, 3, True)
    battery = event.get("battery_ok")
    if not isinstance(battery, (bool, int)) or battery not in (0, 1):
        raise ValueError("Invalid or missing battery_ok")
    return {
        "schema_version": 1,
        "event_type": "sensor_reading",
        "received_at": datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z"),
        "source": source,
        "decoder": "rtl_433",
        "frequency_hz": FREQUENCY,
        "model": "Nexus-TH",
        "device_key": "Nexus-TH:{}:{}".format(sensor_id, channel),
        "sensor_id": sensor_id,
        "channel": channel,
        "temperature_c": number(event, "temperature_C", -204.8, 204.7),
        "humidity_pct": number(event, "humidity", 0, 100),
        "battery_ok": bool(battery),
        "raw": event,
    }


def emit(line, destination, source):
    try:
        event = normalize(json.loads(line), source)
        if event is None:
            return False
        encoded = json.dumps(event, ensure_ascii=False, allow_nan=False, separators=(",", ":"))
    except (ValueError, TypeError) as error:
        LOG.warning("Skipping invalid decoder event: %s", error)
        return False
    # Persist the JSONL journal first; it remains the recovery source of truth.
    destination.write(encoded + "\n")
    destination.flush()

    # SQLite is the query/history index. Its failure must not stop RF collection.
    try:
        rf_store.store_nexus(event)
    except Exception as error:
        LOG.error(
            "SQLite Nexus persistence failed; JSONL journal preserved event: %s",
            error,
        )

    print(encoded, flush=True)
    return True


def find_decoder(explicit):
    if explicit:
        resolved = shutil.which(explicit)
        if not resolved:
            raise ValueError("rtl_433 not executable: " + explicit)
        return resolved
    return shutil.which("rtl_433") or shutil.which("/root/rtl433-test/rtl_433") or None


def command(binary, device, ppm, gain):
    rtl433_device = device if device.startswith(":") else ":" + device
    argv = [binary, "-c", "0", "-d", rtl433_device, "-f", str(FREQUENCY),
            "-s", "250000", "-p", str(ppm), "-R", "19", "-F", "json"]
    if gain is not None:
        argv += ["-g", str(gain)]
    return argv


@contextlib.contextmanager
def device_lock(device):
    # Same lock convention as the SDR scheduler prevents concurrent ownership.
    import fcntl
    import hashlib
    token = hashlib.sha256(device.encode()).hexdigest()[:16]
    with open("/tmp/dragonwing-sdr-" + token + ".lock", "a") as handle:
        try:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise RuntimeError("Device is in use by Watchkeeper or the SDR scheduler")
        yield


def write_status(path, state):
    path.parent.mkdir(parents=True, exist_ok=True)
    data = {"schema_version": 1, "state": state, "pid": os.getpid(),
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "job": "Nexus-TH sensors", "frequency_hz": FREQUENCY}
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(json.dumps(data), encoding="utf-8")
    temporary.replace(path)


def live(argv, destination, stop, status_path=None, duration=None, on_tick=None):
    LOG.info("Listening: %s", shlex.join(argv))
    process = subprocess.Popen(argv, stdout=subprocess.PIPE, stderr=None, start_new_session=True)
    try:
        with selectors.DefaultSelector() as selector:
            selector.register(process.stdout, selectors.EVENT_READ)
            pending = b""
            heartbeat = 0
            deadline = time.monotonic() + duration if duration is not None else None
            while not stop.is_set():
                if deadline is not None and time.monotonic() >= deadline:
                    return 0
                if on_tick:
                    on_tick()
                if status_path and time.monotonic() >= heartbeat:
                    write_status(status_path, "running")
                    heartbeat = time.monotonic() + 2
                if not selector.select(timeout=0.25):
                    continue
                chunk = os.read(process.stdout.fileno(), 65536)
                if not chunk:
                    if pending:
                        emit(pending.decode("utf-8", errors="replace"), destination, "live")
                    if stop.is_set():
                        return 0
                    LOG.error("Decoder stream ended unexpectedly")
                    return 1
                pending += chunk
                while b"\n" in pending:
                    line, pending = pending.split(b"\n", 1)
                    if line.strip():
                        emit(line.decode("utf-8", errors="replace"), destination, "live")
                if len(pending) > 1048576:
                    raise RuntimeError("Decoder emitted an oversized unterminated event")
    finally:
        if process.poll() is None:
            process.terminate()
        try:
            process.wait(timeout=3)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=3)
        process.stdout.close()
        LOG.info("Receiver stopped (exit=%s)", process.returncode)
        if status_path:
            write_status(status_path, "stopped" if stop.is_set() else "failed")
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rtl433", help="Path to decoder; defaults to PATH, then /root/rtl433-test/rtl_433")
    parser.add_argument("--device", default="0")
    parser.add_argument("--ppm", type=int, default=0)
    parser.add_argument("--gain", type=float, help="Tuner gain in dB; omitted uses automatic gain")
    parser.add_argument("--log", type=Path, default=Path(__file__).resolve().parent / "logs" / "events.jsonl")
    parser.add_argument("--replay", type=Path, help="Normalize an existing raw rtl_433 JSONL file without hardware")
    parser.add_argument("--status", type=Path, help="Dashboard heartbeat file; default: status.json beside event log")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s", stream=sys.stderr)
    stop = threading.Event()
    for sig in (signal.SIGINT, signal.SIGTERM):
        signal.signal(sig, lambda *_: stop.set())
    try:
        if args.gain is not None and not math.isfinite(args.gain):
            raise ValueError("Gain must be finite")
        if args.replay and args.replay.resolve() == args.log.resolve():
            raise ValueError("Replay input and output must differ")
        binary = None
        if not args.replay:
            if not sys.platform.startswith("linux"):
                raise ValueError("Live reception requires Linux; use --replay on other systems")
            binary = find_decoder(args.rtl433)
            if not binary:
                raise ValueError("rtl_433 not found; use --rtl433 /path/to/rtl_433")
        lock = contextlib.nullcontext() if args.replay else device_lock(args.device)
        with lock:
            args.log.parent.mkdir(parents=True, exist_ok=True)
            with args.log.open("a", encoding="utf-8") as destination:
                LOG.info("Appending normalized events to %s", args.log)
                if args.replay:
                    with args.replay.open(encoding="utf-8") as source:
                        for line in source:
                            if stop.is_set():
                                break
                            if line.strip():
                                emit(line, destination, "replay")
                    return 0
                status_path = args.status or args.log.with_name("status.json")
                if status_path.resolve() == args.log.resolve():
                    raise ValueError("Status and event log paths must differ")
                write_status(status_path, "starting")
                try:
                    return live(command(binary, args.device, args.ppm, args.gain), destination, stop, status_path)
                except Exception:
                    write_status(status_path, "failed")
                    raise
    except (OSError, ValueError, RuntimeError, subprocess.TimeoutExpired) as error:
        LOG.error("Watchkeeper stopped: %s", error)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
