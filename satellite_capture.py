# Record METEOR IQ with exclusive V4 ownership and persistent guarded reboot recovery; 2026-10-04 22:15 EEST, Thomas Vikström.
import argparse
import json
import signal
import subprocess
import time
import tempfile
import meteor_recovery as recovery
import rf_health
import fcntl
from datetime import datetime, timedelta
from pathlib import Path


RTL_SDR = "/usr/local/bin/rtl_sdr"
SCHEDULER = "rf-watchkeeper-scheduler.service"
OUTDIR = Path("/root/rf-watchkeeper/recordings/satellite")


def parse_time(value):
    dt = datetime.fromisoformat(value)
    if dt.tzinfo is None:
        raise ValueError("Time must include timezone offset, e.g. +03:00")
    return dt


def device_visible(serial):
    try:
        result = subprocess.run(
            ["rtl_test", "-t"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        text = (result.stdout or "") + (result.stderr or "")
        return serial in text, text
    except subprocess.TimeoutExpired as exc:
        text = diagnostic_text(exc.stdout) + diagnostic_text(exc.stderr)
        return serial in text, text


def diagnostic_text(value):
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return value or ""


def iq_preflight(args):
    sample_count = 256000
    expected_bytes = sample_count * 2  # Unsigned 8-bit I and Q per sample.
    diagnostics = {
        "sample_count": sample_count,
        "timeout_seconds": 5,
        "expected_bytes": expected_bytes,
        "minimum_bytes": expected_bytes // 2,
        "attempt_count": 0,
        "byte_count": 0,
        "success": False,
        "attempts": [],
    }
    for attempt in range(1, 4):
        if datetime.now().astimezone() >= record_stop:
            break
        print(f"INFO: IQ preflight attempt {attempt}/3", flush=True)
        result = {
            "attempt": attempt,
            "started_at": datetime.now().astimezone().isoformat(),
            "returncode": None,
            "stdout": "",
            "stderr": "",
            "timed_out": False,
            "byte_count": 0,
            "success": False,
        }
        probe_health_id = rf_health.begin('METEOR IQ preflight', 8, args.device)
        try:
            with tempfile.TemporaryDirectory(prefix="satellite-iq-preflight-") as directory:
                path = Path(directory) / "probe.cu8"
                cmd = [
                    RTL_SDR,
                    "-d", args.device,
                    "-f", str(args.frequency),
                    "-s", str(args.sample_rate),
                    "-g", str(args.gain),
                    "-n", str(sample_count),
                    str(path),
                ]
                result["command"] = cmd
                with subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE) as probe:
                    try:
                        stdout, stderr = probe.communicate(timeout=5)
                    except subprocess.TimeoutExpired:
                        result["timed_out"] = True
                        probe.kill()
                        stdout, stderr = probe.communicate()
                    except BaseException:
                        probe.kill()
                        probe.communicate()
                        raise
                    result["returncode"] = probe.returncode
                result["stdout"] = diagnostic_text(stdout)
                result["stderr"] = diagnostic_text(stderr)
                result["byte_count"] = path.stat().st_size if path.exists() else 0
                result["success"] = (
                    result["returncode"] == 0
                    and not result["timed_out"]
                    and expected_bytes // 2 <= result["byte_count"] <= expected_bytes
                    and result["byte_count"] % 2 == 0
                )
        except OSError as exc:
            result["error"] = str(exc)
            result["success"] = False
        diagnostics["attempts"].append(result)
        rf_health.finish(probe_health_id, result['success'], result['byte_count'], 'IQ bytes',
                         result['returncode'], 'METEOR IQ preflight failed or timed out')
        diagnostics["attempt_count"] = attempt
        diagnostics["byte_count"] = result["byte_count"]
        diagnostics["success"] = result["success"]
        if result["byte_count"] == 0:
            print("INFO: IQ preflight zero bytes", flush=True)
        print("IQ preflight: " + json.dumps(result), flush=True)
        if result["success"]:
            return diagnostics
        if attempt < 3:
            time.sleep(1)
    return diagnostics


def scheduler_start():
    subprocess.run(
        ["systemctl", "start", SCHEDULER],
        check=False,
    )


def scheduler_stop():
    subprocess.run(
        ["systemctl", "stop", SCHEDULER],
        check=True,
        timeout=30,
    )


def wait_until(target, message):
    while True:
        remaining = (target - datetime.now().astimezone()).total_seconds()

        if remaining <= 0:
            return

        if remaining > 60:
            print(f"{message}: {remaining:.0f} seconds remaining")
            time.sleep(min(60, remaining))
        else:
            time.sleep(remaining)


parser = argparse.ArgumentParser()
parser.add_argument("--satellite", required=True)
parser.add_argument("--start", required=True,
                    help="Predicted 10-degree START time")
parser.add_argument("--stop", required=True,
                    help="Predicted 10-degree STOP time")
parser.add_argument("--frequency", type=int, default=137900000)
parser.add_argument("--sample-rate", type=int, default=256000)
parser.add_argument("--gain", type=float, default=49.6)
parser.add_argument("--device", default="V4MAIN01")
parser.add_argument("--pre-margin", type=int, default=90)
parser.add_argument("--post-margin", type=int, default=90)
parser.add_argument("--preflight-seconds", type=int, default=120)
parser.add_argument("--recovery-record", default=None, help="Managed pass record for post-reboot completion")
args = parser.parse_args()

pass_start = parse_time(args.start)
pass_stop = parse_time(args.stop)

record_start = pass_start - timedelta(seconds=args.pre_margin)
record_stop = pass_stop + timedelta(seconds=args.post_margin)
preflight_time = record_start - timedelta(seconds=args.preflight_seconds)

now = datetime.now().astimezone()

if record_stop <= now:
    raise SystemExit("ERROR: pass window already expired")

OUTDIR.mkdir(parents=True, exist_ok=True)

stamp = record_start.strftime("%Y%m%d_%H%M%S")
base = f"{args.satellite}_{stamp}_{args.frequency}"
iq_path = OUTDIR / f"{base}.cu8"
meta_path = OUTDIR / f"{base}.json"

metadata = {
    "satellite": args.satellite,
    "pass_start_10deg": pass_start.isoformat(),
    "pass_stop_10deg": pass_stop.isoformat(),
    "record_start": record_start.isoformat(),
    "record_stop": record_stop.isoformat(),
    "pre_margin_seconds": args.pre_margin,
    "post_margin_seconds": args.post_margin,
    "frequency_hz": args.frequency,
    "sample_rate_sps": args.sample_rate,
    "gain_db": args.gain,
    "device_serial": args.device,
    "iq_file": str(iq_path),
    "status": "initializing",
}

# Preserve the observer, orbital elements and pass geometry before recording.
# Missing predictions must never prevent a scheduled RF capture.
try:
    from pass_conditions import capture_snapshot
    metadata['pass_conditions'] = capture_snapshot(metadata)
except Exception as error:
    metadata['conditions_warning'] = 'Pass predictions unavailable: ' + str(error)
if iq_path.exists() and iq_path.stat().st_size:
    raise SystemExit("ERROR: existing IQ recording; refusing to overwrite")
recovery_path = recovery.state_path(args.satellite, args.start)
if recovery_path.exists():
    previous = json.loads(recovery_path.read_text())
    if previous.get('state') == 'resuming':
        print("INFO: post-reboot capture resumed", flush=True)
        metadata['reboot_recovery_attempted'] = True
meta_path.write_text(json.dumps(metadata, indent=2) + "\n")

print()
print(f"Satellite:          {args.satellite}")
print(f"10° pass:           {pass_start} -> {pass_stop}")
print(f"Recording window:   {record_start} -> {record_stop}")
print(f"Margins:            -{args.pre_margin}s / +{args.post_margin}s")
print(f"Frequency:          {args.frequency / 1e6:.6f} MHz")
print(f"Sample rate:        {args.sample_rate} S/s")
print(f"Gain:               {args.gain} dB")
print(f"Device:             {args.device}")
print(f"Output:             {iq_path}")
print()

visible, output = device_visible(args.device)

if not visible:
    metadata["status"] = "failed_initial_device_check"
    metadata["device_check_output"] = output
    meta_path.write_text(json.dumps(metadata, indent=2) + "\n")
    raise SystemExit(f"ERROR: {args.device} is not currently visible")

print(f"Initial device check: {args.device} visible")

if datetime.now().astimezone() < preflight_time:
    wait_until(preflight_time, "Waiting for preflight")

visible, output = device_visible(args.device)

if not visible:
    metadata["status"] = "failed_preflight_device_check"
    metadata["device_check_output"] = output
    meta_path.write_text(json.dumps(metadata, indent=2) + "\n")
    scheduler_start()
    raise SystemExit(
        f"ERROR: {args.device} disappeared before the pass; capture cancelled"
    )

print(f"Preflight check: {args.device} visible")

reboot_pending = False

health_control = (rf_health.ROOT / "data/rf-health-control.lock").open("a")
fcntl.flock(health_control, fcntl.LOCK_EX)
health_id = rf_health.begin("METEOR capture", max(1, (record_stop-datetime.now().astimezone()).total_seconds()), args.device)
try:
    print("INFO: METEOR reservation active", flush=True)
    recovery_path = recovery.register(args, metadata)
    print("INFO: stopping RF scheduler", flush=True)
    scheduler_stop()
    time.sleep(3)
    recovery.release_v4(args.device)

    metadata["iq_preflight"] = iq_preflight(args)

    if not metadata["iq_preflight"]["success"]:
        metadata["status"] = "failed_iq_preflight"
        meta_path.write_text(json.dumps(metadata, indent=2) + "\n")
        visible, output = device_visible(args.device)
        if visible:
            reboot_pending = recovery.request_reboot(recovery_path)
            if reboot_pending:
                metadata['status'] = 'reboot_recovery_pending'
                meta_path.write_text(json.dumps(metadata, indent=2) + "\n")
                raise SystemExit(75)
        print("ERROR: METEOR capture failed after recovery; bounded IQ preflight exhausted", flush=True)
        raise SystemExit(1)

    if datetime.now().astimezone() >= record_stop:
        metadata["status"] = "failed_capture_window_ended"
        meta_path.write_text(json.dumps(metadata, indent=2) + "\n")
        raise SystemExit("ERROR: capture window ended during IQ preflight")

    if datetime.now().astimezone() < record_start:
        wait_until(record_start, "Waiting for recording start")

    duration = max(
        1,
        int((record_stop - datetime.now().astimezone()).total_seconds())
    )

    cmd = [
        RTL_SDR,
        "-d", args.device,
        "-f", str(args.frequency),
        "-s", str(args.sample_rate),
        "-g", str(args.gain),
        str(iq_path),
    ]

    print()
    print("Starting IQ recording...")
    print(" ".join(cmd))
    print(f"Recording for approximately {duration} seconds")

    actual_start = datetime.now().astimezone()
    metadata["actual_start"] = actual_start.isoformat()
    metadata["status"] = "recording"

    proc = None
    scheduled_stop = False

    try:
        proc = subprocess.Popen(cmd)

        try:
            proc.wait(timeout=duration)

        except subprocess.TimeoutExpired:
            scheduled_stop = True
            print("Scheduled capture complete; stopping rtl_sdr...")
            proc.send_signal(signal.SIGINT)

            try:
                proc.wait(timeout=8)
            except subprocess.TimeoutExpired:
                proc.terminate()
                try:
                    proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    proc.wait(timeout=3)

    finally:
        if proc and proc.poll() is None:
            proc.kill()
            proc.wait(timeout=3)
        actual_stop = datetime.now().astimezone()

finally:
    iq_bytes = iq_path.stat().st_size if iq_path.exists() else 0
    capture_proc = locals().get("proc")
    rf_health.finish(health_id, bool(capture_proc and locals().get('scheduled_stop',False)
                     and capture_proc.returncode in (0, -2)
                     and iq_bytes >= max(1,locals().get('duration', 1))*args.sample_rate
                     and iq_bytes % 2 == 0),
                     iq_bytes, "IQ bytes", capture_proc.returncode if capture_proc else None, "METEOR preflight/capture failed")
    health_control.close()
    if not reboot_pending:
        print("Restarting RF Watchkeeper V4 scheduler...", flush=True)
        scheduler_start()
    else:
        print("INFO: METEOR reservation retained for reboot recovery", flush=True)

metadata["actual_stop"] = actual_stop.isoformat()
metadata["rtl_sdr_returncode"] = proc.returncode if proc else None

if iq_path.exists():
    metadata["iq_bytes"] = iq_path.stat().st_size
else:
    metadata["iq_bytes"] = 0

if metadata["iq_bytes"] > 0 and proc is not None and proc.returncode in (0, -2) and scheduled_stop:
    metadata["status"] = "completed"
else:
    metadata["status"] = "failed_no_iq"

meta_path.write_text(json.dumps(metadata, indent=2) + "\n")

print()
print("=" * 72)
print("INFO: METEOR capture successful" if metadata["status"] == "completed" else "ERROR: METEOR capture failed after recovery", flush=True)
print(f"Status:   {metadata['status']}")
print(f"IQ:       {iq_path}")
print(f"Metadata: {meta_path}")
print(f"Size:     {metadata['iq_bytes'] / 1024 / 1024:.1f} MiB")
print("=" * 72)

if metadata["status"] != "completed":
    raise SystemExit(1)
