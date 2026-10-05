# Schedule existing RF backends and publish normalized job transitions and dashboard status. 2026-09-16 22:52 EEST — Thomas Vikström.
"""RF Watchkeeper milestone 1; standard library only, Python 3.8+."""
import argparse
import contextlib
from datetime import datetime, timezone
import json
import logging
import math
import os
from pathlib import Path
import shutil
import signal
import sys
import threading
import time

import watchkeeper
import rf_health
import subprocess
import atis_pipeline
from zoneinfo import ZoneInfo

# Reuse the tested demo's FM/AM pipeline instead of duplicating its commands/lifecycle.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from sdr_demo import scheduler as demo

ROOT = Path(__file__).resolve().parent
LOG = logging.getLogger("job_manager")
IMPLEMENTED = {"nexus", "fm", "am", "ais"}


def finite(value, name, minimum=0):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value < minimum:
        raise ValueError("Invalid " + name)
    return value


def load_config(path):
    # JSONC support is deliberately limited to whole-line // comments.
    text = "\n".join(line for line in path.read_text(encoding="utf-8").splitlines()
                     if not line.lstrip().startswith("//"))
    config = json.loads(text)
    if not isinstance(config, dict) or not isinstance(config.get("jobs"), list):
        raise ValueError("Configuration must contain a jobs list")
    finite(config.get("handoff_seconds", 1), "handoff_seconds")
    finite(config.get("ppm", 0), "ppm", -100000)
    if not isinstance(config.get("device", "0"), (int, str)):
        raise ValueError("device must be an index or serial")
    if not isinstance(config.get("audio_device", "default"), str):
        raise ValueError("audio_device must be a string")
    ids = set()
    for job in config["jobs"]:
        if not isinstance(job, dict):
            raise ValueError("Each job must be an object")
        for key in ("id", "name", "mode"):
            if not isinstance(job.get(key), str) or not job[key].strip():
                raise ValueError("Each job needs a nonempty " + key)
        if job["id"] in ids:
            raise ValueError("Duplicate job id: " + job["id"])
        ids.add(job["id"])
        if type(job.get("enabled")) is not bool:
            raise ValueError("enabled must be true or false")
        finite(job.get("frequency_hz"), "frequency_hz", 1)
        finite(job.get("dwell_seconds"), "dwell_seconds", 0.01)
        finite(job.get("priority", 0), "priority", -100000)
        if job.get("gain_db") is not None:
            finite(job["gain_db"], "gain_db", -100)
        if job["mode"] not in IMPLEMENTED | {"ais", "satellite"}:
            raise ValueError("Unknown mode: " + job["mode"])
        if job["enabled"] and job["mode"] not in IMPLEMENTED:
            raise ValueError("Placeholder cannot be enabled yet: " + job["id"])
        if job["mode"] == "nexus" and job["frequency_hz"] != watchkeeper.FREQUENCY:
            raise ValueError("Nexus backend currently requires 433920000 Hz")
        if job.get("atis_recording") or job.get("tower_recording"):
            if job["mode"] != "am" or job["frequency_hz"] != (120950000 if job.get("tower_recording") else 136450000) or job.get("sample_rate") != 8000:
                raise ValueError("ATIS requires AM 136450000 Hz at 8000 Hz")
            finite(job.get("interval_seconds", 1800), "interval_seconds", 180)
            if job["dwell_seconds"] > 120:
                raise ValueError("ATIS capture is limited to 120 seconds")
        if job["mode"] == "am":
            rate = finite(job.get("sample_rate", 24000), "sample_rate", 1)
            if int(rate) != rate:
                raise ValueError("sample_rate must be an integer")
    return config


def in_window(job, now=None):
    if not job.get('tower_recording'):
        return True
    try:
        zone = ZoneInfo('Europe/Helsinki')
    except KeyError:
        # The EVK image has no system tzdata. Bundle the IANA zone file locally.
        with (ROOT/'Helsinki.tzif').open('rb') as source:
            zone = ZoneInfo.from_file(source, key='Europe/Helsinki')
    local = (now or datetime.now(timezone.utc)).astimezone(zone)
    minute = local.hour*60+local.minute
    return minute >= 300 or minute < 90

def ordered_jobs(config):
    # Every enabled job gets one slot per cycle; priority only changes order.
    return sorted((j for j in config["jobs"] if j["enabled"]),
                  key=lambda j: -j.get("priority", 0))


def demo_job(job):
    return dict(job, kind=job["mode"], seconds=job["dwell_seconds"])


class Publisher:
    def __init__(self, stream, status_path, mode):
        self.stream, self.status_path, self.mode = stream, status_path, mode
        self.current = None
        self.next_heartbeat = 0

    def transition(self, state, job=None, reason=None, cycle=0):
        event = {"schema_version": 1, "event_type": "scheduler_state",
                 "received_at": datetime.now(timezone.utc).isoformat(),
                 "source": "live" if self.mode == "live" else "simulation",
                 "mode": self.mode, "state": state, "cycle": cycle,
                 "job_id": job["id"] if job else None,
                 "job": job["name"] if job else None,
                 "frequency_hz": job["frequency_hz"] if job else None,
                 "processing_mode": job["mode"] if job else None,
                 "dwell_seconds": job["dwell_seconds"] if job else None,
                 "reason": reason}
        encoded = json.dumps(event, ensure_ascii=False, allow_nan=False)
        self.stream.write(encoded + "\n")
        self.stream.flush()
        print(encoded, flush=True)
        self.current = event
        self.tick(force=True)

    def tick(self, force=False):
        if not force and time.monotonic() < self.next_heartbeat:
            return
        data = dict(self.current, updated_at=datetime.now(timezone.utc).isoformat(),
                    pid=os.getpid(), owner="scheduler")
        self.status_path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.status_path.with_name(self.status_path.name + ".tmp")
        temporary.write_text(json.dumps(data), encoding="utf-8")
        temporary.replace(self.status_path)
        self.next_heartbeat = time.monotonic() + 2


def wait_slot(seconds, stop, publisher):
    deadline = time.monotonic() + seconds
    while not stop.is_set():
        publisher.tick()
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            break
        stop.wait(min(0.1, remaining))


def dependency_error(config, job):
    if job["mode"] == "nexus":
        try:
            return None if watchkeeper.find_decoder(config.get("rtl433")) else "rtl_433 not found"
        except ValueError as error:
            return str(error)
    if job["mode"] == "ais":
        missing = []
        if not Path("/root/AIS-catcher").is_file():
            missing.append("/root/AIS-catcher")
        if not (ROOT / "ais_collector.py").is_file():
            missing.append(str(ROOT / "ais_collector.py"))
        return "Missing: " + ", ".join(missing) if missing else None

    receiver, sink = demo.commands(config, demo_job(job))
    missing = [cmd[0] for cmd in (receiver, sink) if cmd and not shutil.which(cmd[0])]
    return "Missing: " + ", ".join(missing) if missing else None


def execute(config, job, output, stop, publisher):
    if publisher.mode == "simulation":
        wait_slot(job["dwell_seconds"], stop, publisher)
        return True
    if job.get("atis_recording") or job.get("tower_recording"):
        return atis_pipeline.capture(config, job, stop, publisher)
    if job["mode"] == "nexus":
        binary = watchkeeper.find_decoder(config.get("rtl433"))
        argv = watchkeeper.command(binary, str(config.get("device", "0")),
                                   config.get("ppm", 0), job.get("gain_db"))
        return watchkeeper.live(argv, publisher.stream, stop,
                                duration=job["dwell_seconds"], on_tick=publisher.tick) == 0

    if job["mode"] == "ais":
        argv = [
            "/usr/bin/python3",
            str(ROOT / "ais_collector.py"),
            "--seconds",
            str(job["dwell_seconds"]),
        ]
        LOG.info("COMMAND %s", " ".join(argv))
        if job.get("_rf_health_id"):
            argv += ["--health-id", str(job["_rf_health_id"])]
        process = subprocess.Popen(argv, start_new_session=True)
        hard_deadline = time.monotonic() + job["dwell_seconds"] + 20

        try:
            while process.poll() is None:
                if time.monotonic() >= hard_deadline:
                    rf_health.finish(job.get("_rf_health_id"), False, reason="AIS collector exceeded dwell plus 20-second hard timeout")
                    os.killpg(process.pid, signal.SIGTERM)
                    try:
                        process.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        os.killpg(process.pid, signal.SIGKILL)
                        process.wait(timeout=3)
                    return False
                if stop.is_set():
                    os.killpg(process.pid, signal.SIGTERM)
                    try:
                        process.wait(timeout=5)
                    except __import__("subprocess").TimeoutExpired:
                        os.killpg(process.pid, signal.SIGKILL)
                        process.wait(timeout=3)
                    return False
                publisher.tick()
                stop.wait(0.2)

            return process.returncode == 0
        finally:
            if process.poll() is None:
                os.killpg(process.pid, signal.SIGTERM)
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    os.killpg(process.pid, signal.SIGKILL)
                    process.wait(timeout=3)

    return demo.run_job(config, demo_job(job), output, stop, on_tick=publisher.tick)


def schedule(config, output, stop, publisher, cycles=0):
    jobs = ordered_jobs(config)
    cycle = 0
    had_failure = False
    while not stop.is_set() and (cycles == 0 or cycle < cycles):
        cycle += 1
        attempted = 0
        for job in jobs:
            if stop.is_set():
                break
            if job['mode'] == 'ais' and any(j.get('tower_recording') for j in jobs):
                job = dict(job, dwell_seconds=min(job['dwell_seconds'], 30))
            if job.get('atis_recording') or job.get('tower_recording'):
                if not in_window(job) or not atis_pipeline.due(job, output):
                    continue
                atis_pipeline.reserve(job, output)
                reason = None if publisher.mode == 'simulation' else atis_pipeline.satellite_reason(job['dwell_seconds'])
                if reason:
                    publisher.transition('skipped', job, 'Intentional METEOR skip: '+reason, cycle)
                    continue
            reason = None if publisher.mode == "simulation" else dependency_error(config, job)
            if reason:
                publisher.transition("skipped", job, reason, cycle)
                continue
            if publisher.mode == 'live' and str(config.get('device')) == 'V4MAIN01':
                reservation = atis_pipeline.satellite_reason(job['dwell_seconds'])
                if reservation:
                    publisher.transition('skipped', job, 'Intentional METEOR skip: '+reservation, cycle)
                    continue
            attempted += 1
            publisher.transition("running", job, cycle=cycle)
            health_id = None
            if publisher.mode == "live" and str(config.get("device")) == "V4MAIN01":
                health_id = rf_health.begin(job["id"], job["dwell_seconds"])
                job["_rf_health_id"] = health_id
            try:
                success = execute(config, job, output, stop, publisher)
            except Exception as error:
                if health_id:
                    rf_health.finish(health_id, False, reason=str(error))
                publisher.transition("failed", job, str(error), cycle)
                raise  # Uncertain cleanup must never hand off the receiver.
            if health_id:
                if stop.is_set() or success == 'skipped':
                    rf_health.cancel(health_id, 'Scheduler stopped or intentionally skipped; receiver released')
                rf_health.finish(health_id, False, reason="Cancelled" if stop.is_set() else "Backend returned without sample evidence")
            publisher.transition("cancelled" if stop.is_set() else "skipped" if success == 'skipped' else "completed" if success else "failed",
                                 job, "Stop requested" if stop.is_set() else publisher.current.get('reason') if success == 'skipped' else None if success else "Backend exited early; inspect diagnostics", cycle)
            had_failure = had_failure or (not success and not stop.is_set())
            if stop.is_set():
                break
            publisher.transition("waiting", cycle=cycle)
            wait_slot(config.get("handoff_seconds", 1), stop, publisher)
        if not attempted and not stop.is_set():
            publisher.transition("waiting", reason="No jobs due in current operating window", cycle=cycle)
            wait_slot(1, stop, publisher)
    publisher.transition("stopped", reason="Stop requested" if stop.is_set() else "Requested cycles completed", cycle=cycle)
    return int(had_failure)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=ROOT / "jobs.jsonc")
    parser.add_argument("--output", type=Path, help="Default: logs (live) or simulation-logs")
    parser.add_argument("--cycles", type=int, default=0, help="0 means continuous")
    parser.add_argument("--simulate", action="store_true")
    parser.add_argument("--dry-run", action="store_true", help="Validate and display schedule without opening hardware")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    stop = threading.Event()
    for sig in (signal.SIGINT, signal.SIGTERM):
        signal.signal(sig, lambda *_: stop.set())
    try:
        config = load_config(args.config)
        if args.cycles < 0:
            raise ValueError("cycles must be nonnegative")
        if not ordered_jobs(config):
            raise ValueError("Enable at least one implemented job")
        if args.dry_run:
            for job in ordered_jobs(config):
                print("{}: {} Hz / {} / {} seconds / priority {}".format(
                    job["id"], job["frequency_hz"], job["mode"], job["dwell_seconds"], job.get("priority", 0)))
            return 0
        if not args.simulate and not sys.platform.startswith("linux"):
            raise ValueError("Live mode requires Linux; use --simulate here")
        output = args.output or ROOT / ("simulation-logs" if args.simulate else "logs")
        output.mkdir(parents=True, exist_ok=True)
        lock = contextlib.nullcontext() if args.simulate else watchkeeper.device_lock(str(config.get("device", "0")))
        with lock:
            with (output / "events.jsonl").open("a", encoding="utf-8") as stream:
                publisher = Publisher(stream, output / "status.json", "simulation" if args.simulate else "live")
                publisher.transition("starting")
                return schedule(config, output, stop, publisher, args.cycles)
    except (OSError, ValueError, TypeError, RuntimeError) as error:
        LOG.error("Scheduler stopped: %s", error)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
