# Run bounded RTL-SDR jobs and expose heartbeat callbacks to RF Watchkeeper. 2026-09-16 22:52 EEST â€” Thomas VikstrÃ¶m.
"""Python 3.8+; Linux for hardware mode. No third-party Python dependencies."""
import argparse
import contextlib
import json
import logging
import math
import os
from pathlib import Path
import shlex
import shutil
import signal
import subprocess
import sys
import threading
import time

LOG = logging.getLogger("sdr")


def positive(value):
    value = float(value)
    if not math.isfinite(value) or value <= 0:
        raise ValueError("Durations and frequencies must be finite and positive")
    return value


def load_config(path):
    config = json.loads(Path(path).read_text(encoding="utf-8"))
    if not config.get("jobs"):
        raise ValueError("Configure at least one job")
    for job in config["jobs"]:
        if job["kind"] not in ("fm", "am", "sensors"):
            raise ValueError("Unknown job kind: " + job["kind"])
        if not isinstance(job["name"], str) or not job["name"]:
            raise ValueError("Each job needs a name")
        positive(job["seconds"])
        positive(job["frequency_hz"])
    positive(config.get("handoff_seconds", 1))
    return config


def commands(config, job):
    """Backend boundary: return receiver argv and optional audio sink argv."""
    device = str(config.get("device", 0))
    common = ["-d", device, "-p", str(config.get("ppm", 0))]
    gain = job.get("gain_db")
    if gain is not None:
        common += ["-g", str(gain)]
    frequency = str(int(job["frequency_hz"]))
    if job["kind"] == "sensors":
        # Empty config prevents local rtl_433 settings adding frequencies/outputs.
        receiver = ["rtl_433", "-c", "0"] + common + [
            "-f", frequency, "-s", "250000", "-F", "json"]
        for protocol in job.get("protocols", []):
            receiver += ["-R", str(int(protocol))]
        return receiver, None
    if job["kind"] == "fm":
        rate = 16000
        mode = ["-M", "wbfm", "-s", "200000", "-r", str(rate), "-E", "deemp"]
    else:
        rate = int(job.get("sample_rate", 24000))
        positive(rate)
        mode = ["-M", "am", "-s", str(rate)]
    receiver = ["rtl_fm"] + common + ["-f", frequency] + mode
    sink = ["aplay", "-D", config.get("audio_device", "default"),
            "-t", "raw", "-r", str(rate), "-f", "S16_LE", "-c", "1"]
    return receiver, sink


def stop_processes(processes):
    """Stop the RF producer first, then allow downstream audio processes to drain."""
    if not processes:
        return

    producer = processes[0]

    if producer.poll() is None:
        try:
            producer.terminate()
        except ProcessLookupError:
            pass

    try:
        producer.wait(timeout=3)
    except subprocess.TimeoutExpired:
        LOG.warning("Force-stopping producer PID %s", producer.pid)
        producer.kill()
        producer.wait(timeout=3)

    # Closing the producer gives tap/aplay EOF so WAV metadata can be finalized.
    deadline = time.monotonic() + 3
    for process in processes[1:]:
        try:
            process.wait(timeout=max(0.05, deadline - time.monotonic()))
            continue
        except subprocess.TimeoutExpired:
            pass

        if process.poll() is None:
            try:
                process.terminate()
            except ProcessLookupError:
                pass

        try:
            process.wait(timeout=1)
        except subprocess.TimeoutExpired:
            LOG.warning("Force-stopping downstream PID %s", process.pid)
            process.kill()
            process.wait(timeout=2)

def run_job(config, job, output, stop, simulate=False, on_tick=None):
    receiver, sink = commands(config, job)
    LOG.info("ACTIVE job=%s frequency=%.6fMHz duration=%ss mode=%s",
             job["name"], job["frequency_hz"] / 1e6, job["seconds"],
             "simulation" if simulate else "hardware")
    LOG.info("COMMAND %s%s", shlex.join(receiver),
             " | " + shlex.join(sink) if sink else "")
    if simulate:
        stop.wait(float(job["seconds"]))
        LOG.info("STOP job=%s", job["name"])
        return True
    sys.path.insert(0, '/root/rf-watchkeeper')
    import rf_health
    health_id = job.get("_rf_health_id")
    evidence_path = output / ("rf-samples-" + str(os.getpid()) + ".json")
    if evidence_path.exists():
        evidence_path.unlink()
    processes = []
    success = True
    try:
        with contextlib.ExitStack() as stack:
            diagnostics = stack.enter_context((output / "tools.log").open("ab", buffering=0))
            diagnostics.write(("\n--- " + time.strftime("%Y-%m-%d %H:%M:%S") +
                               " " + job["name"] + " ---\n").encode("utf-8"))
            destination = subprocess.PIPE if sink else stack.enter_context(
                (output / "sensors.jsonl").open("ab", buffering=0))
            try:
                producer = subprocess.Popen(receiver, stdout=destination, stderr=diagnostics,
                                            start_new_session=(os.name == "posix"))
                processes.append(producer)
                if sink:
                    relay = subprocess.Popen([sys.executable, "/root/rf-watchkeeper/rf_sample_relay.py", str(evidence_path)],
                        stdin=producer.stdout, stdout=subprocess.PIPE, stderr=diagnostics, start_new_session=True)
                    processes.append(relay)
                    producer.stdout.close()
                    try:
                        if job["kind"] == "fm":
                            recording_dir = Path("/root/rf-watchkeeper/recordings/fm")
                            recording_dir.mkdir(parents=True, exist_ok=True)

                            stamp = time.strftime("%Y%m%dT%H%M%S")
                            wav_path = recording_dir / (
                                "fm_" + stamp + "_" +
                                str(int(job["frequency_hz"])) + "Hz.wav"
                            )

                            tap_command = [
                                sys.executable,
                                "/root/rf-watchkeeper/audio_tap.py",
                                "--output", str(wav_path),
                                "--db", "/root/rf-watchkeeper/data/watchkeeper.db",
                                "--frequency-hz", str(int(job["frequency_hz"])),
                                "--rate", "16000",
                                "--seconds", "30",
                            ]

                            tap_process = subprocess.Popen(
                                tap_command,
                                stdin=relay.stdout,
                                stdout=subprocess.PIPE,
                                stderr=diagnostics,
                                start_new_session=(os.name == "posix"),
                            )
                            processes.append(tap_process)
                            relay.stdout.close()

                            player = subprocess.Popen(
                                sink,
                                stdin=tap_process.stdout,
                                stdout=subprocess.DEVNULL,
                                stderr=diagnostics,
                                start_new_session=(os.name == "posix"),
                            )
                            processes.append(player)
                            tap_process.stdout.close()

                        else:
                            processes.append(subprocess.Popen(
                                sink,
                                stdin=relay.stdout,
                                stdout=subprocess.DEVNULL,
                                stderr=diagnostics,
                                start_new_session=(os.name == "posix"),
                            ))
                            relay.stdout.close()

                    except BaseException:
                        relay.stdout.close()
                        raise
                deadline = time.monotonic() + float(job["seconds"])
                while not stop.is_set():
                    if on_tick:
                        on_tick()
                    exited = [p for p in processes if p.poll() is not None]
                    if exited:
                        LOG.error("Job %s exited early (codes %s); see tools.log",
                                  job["name"], [p.returncode for p in exited])
                        success = False
                        break
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        break
                    stop.wait(min(0.1, remaining))
            finally:
                try:
                    stop_processes(processes)
                except (OSError, subprocess.TimeoutExpired) as error:
                    raise RuntimeError("Cannot confirm receiver cleanup; stopping scheduler") from error
    except OSError as error:
        LOG.error("Job %s failed: %s", job["name"], error)
        success = False
    finally:
        LOG.info("STOP job=%s", job["name"])
    sample_bytes = 0
    try:
        sample_bytes = json.loads(evidence_path.read_text())["sample_bytes"]
    except (OSError, ValueError, KeyError):
        pass
    if evidence_path.exists():
        evidence_path.unlink()
    if health_id:
        if stop.is_set():
            rf_health.cancel(health_id, 'Audio job intentionally released by scheduler stop')
        rf_health.finish(health_id, success and not stop.is_set() and producer.returncode in (0, -15, -2),
                         sample_bytes, "PCM bytes", producer.returncode, "No samples / early exit / forced cleanup")
    return success


@contextlib.contextmanager
def device_lock(device):
    import fcntl
    import hashlib
    token = hashlib.sha256(str(device).encode()).hexdigest()[:16]
    # Keep the lock file: unlinking a locked inode introduces a race.
    with open("/tmp/dragonwing-sdr-" + token + ".lock", "a") as handle:
        try:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise RuntimeError("Another scheduler owns this device")
        yield


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=Path(__file__).with_name("jobs.json"))
    parser.add_argument("--output", type=Path, default=Path("sdr-logs"))
    parser.add_argument("--cycles", type=int, default=0, help="0 repeats until Ctrl+C")
    parser.add_argument("--simulate", action="store_true", help="Timed demo without hardware or fake sensor data")
    parser.add_argument("--dry-run", action="store_true", help="Print commands and exit without hardware")
    args = parser.parse_args(argv)
    if args.cycles < 0:
        parser.error("--cycles must be nonnegative")
    try:
        config = load_config(args.config)
        for job in config["jobs"]:
            receiver, sink = commands(config, job)
            if args.dry_run:
                print(job["name"], str(job["seconds"]) + "s:", shlex.join(receiver),
                      "| " + shlex.join(sink) if sink else "")
        if args.dry_run:
            return 0
        if not args.simulate and os.name != "posix":
            raise ValueError("Hardware mode requires Linux; use --simulate on this computer")
    except (OSError, ValueError, KeyError, TypeError) as error:
        parser.error(str(error))
    args.output.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s",
                        handlers=[logging.StreamHandler(), logging.FileHandler(
                            args.output / "scheduler.log", encoding="utf-8")])
    stop = threading.Event()
    for sig in (signal.SIGINT, signal.SIGTERM):
        signal.signal(sig, lambda *_: stop.set())
    jobs = []
    for job in config["jobs"]:
        receiver, sink = commands(config, job)
        missing = [cmd[0] for cmd in (receiver, sink) if cmd and not shutil.which(cmd[0])]
        if missing and not args.simulate:
            LOG.warning("SKIP job=%s missing=%s", job["name"], ",".join(missing))
        else:
            jobs.append(job)
    if not jobs:
        LOG.error("No runnable jobs; install rtl_fm, aplay and/or rtl_433")
        return 1
    failed = False
    lock = contextlib.nullcontext() if args.simulate else device_lock(config.get("device", 0))
    try:
        with lock:
            cycle = 0
            while not stop.is_set() and (args.cycles == 0 or cycle < args.cycles):
                cycle += 1
                LOG.info("CYCLE %s", cycle)
                for job in jobs:
                    if stop.is_set():
                        break
                    if not run_job(config, job, args.output, stop, args.simulate):
                        failed = True
                    stop.wait(float(config.get("handoff_seconds", 1)))
    except (RuntimeError, OSError, subprocess.TimeoutExpired) as error:
        LOG.error("Scheduler stopped: %s", error)
        return 1
    LOG.info("Scheduler stopped; receiver released")
    return int(failed)


if __name__ == "__main__":
    raise SystemExit(main())
