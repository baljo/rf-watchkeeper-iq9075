#!/bin/sh
# Run fixed-duration AIS gain benchmarks without blocking on sparse reception; 2026-09-25 11:18 EEST, Thomas Vikström.

cd /root/rf-watchkeeper || exit 1

python3 - <<'PY'
# Benchmark AIS gain settings for exactly five minutes each and summarize received AIS traffic; 2026-09-25 11:18 EEST, Thomas Vikström.

import json
import subprocess
import time
import re
import signal
import rf_health
import atis_pipeline
import watchkeeper
from pathlib import Path

AIS = "/root/AIS-catcher"
DEVICE = "V4MAIN01"
SECONDS = 300
OUTDIR = Path("logs/ais-gain-test")
OUTDIR.mkdir(parents=True, exist_ok=True)

tests = [
    ("AUTO", "auto"),
    ("20dB", "20"),
    ("30dB", "30"),
    ("40dB", "40"),
    ("49.6dB", "49.6"),
]

summary = []

# Never release another satellite owner or occupy its planned recording window.
health_control = rf_health.control_lock()
health_control.__enter__()
reason = rf_health.satellite_guard() or atis_pipeline.satellite_reason(len(tests)*SECONDS, margin=300)
if reason:
    raise SystemExit('Diagnostic refused: '+reason)
subprocess.run(['systemctl','stop','rf-watchkeeper-scheduler.service'],check=True,timeout=30)
receiver_lock = watchkeeper.device_lock(DEVICE)
try:
    receiver_lock.__enter__()
except BaseException:
    if not rf_health.satellite_guard():
        subprocess.run(['systemctl','start','rf-watchkeeper-scheduler.service'],check=False,timeout=30)
    health_control.__exit__(None,None,None)
    raise

try:
    for label, gain in tests:
        print(f"\n=== {label} ===", flush=True)
        outfile = OUTDIR / f"{label}.jsonl"

        cmd = [
            AIS, "-d", DEVICE, "-o", "5",
            "-gr", "tuner", gain, "rtlagc", "on",
            "-a", "192K",
            "-b", "-T", str(SECONDS+2),
        ]

        print(" ".join(cmd), flush=True)
        print(f"Running for {SECONDS} seconds...", flush=True)

        started = time.monotonic()
        health_id = rf_health.begin('AIS gain diagnostic '+label, SECONDS)
        intentional = False

        with outfile.open("w", encoding="utf-8") as out:
            proc = subprocess.Popen(
                cmd,
                stdout=out,
                stderr=subprocess.STDOUT,
                text=True,
            )

            try:
                proc.wait(timeout=SECONDS)
            except subprocess.TimeoutExpired:
                intentional = True
                proc.send_signal(signal.SIGINT)
                try:
                    proc.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    proc.wait(timeout=3)

        elapsed = time.monotonic() - started

        messages = 0
        mmsis = set()
        signal_values = []

        with outfile.open("r", encoding="utf-8") as inp:
            for line in inp:
                try:
                    item = json.loads(line)
                except json.JSONDecodeError:
                    continue

                if item.get("class") != "AIS":
                    continue

                messages += 1

                if isinstance(item.get("mmsi"), int):
                    mmsis.add(item["mmsi"])

                if isinstance(item.get("signalpower"), (int, float)):
                    signal_values.append(float(item["signalpower"]))

        minutes = elapsed / 60.0
        processing_ms = sum(float(value) for value in re.findall(
            r'\[[^\n]+\]\s+([0-9]+(?:\.[0-9]+)?)\s+ms', outfile.read_text(errors='replace')))
        rf_health.finish(health_id, intentional and proc.returncode in (0,254,-2),
                         processing_ms, 'AIS sample DSP milliseconds', proc.returncode,
                         'Diagnostic sample evidence missing / early exit / forced cleanup',
                         {'messages':messages,'unique_mmsi':len(mmsis),'status':'decoded' if messages else 'quiet'})

        result = {
            "gain": label,
            "elapsed_seconds": round(elapsed, 1),
            "messages": messages,
            "messages_per_minute": round(messages / minutes, 2) if minutes > 0 else 0,
            "unique_mmsi": len(mmsis),
            "mmsis": sorted(mmsis),
            "mean_signalpower": round(sum(signal_values) / len(signal_values), 2) if signal_values else None,
            "weakest_signalpower": round(min(signal_values), 2) if signal_values else None,
        }

        summary.append(result)
        print(json.dumps(result, indent=2), flush=True)

    (OUTDIR / "summary.json").write_text(
        json.dumps(summary, indent=2),
        encoding="utf-8",
    )

finally:
    if 'proc' in locals() and proc.poll() is None:
        rf_health.stop_process(proc)
        rf_health.cancel(health_id, 'AIS diagnostic interrupted; receiver released')
    receiver_lock.__exit__(None,None,None)
    systemctl = subprocess.run
    try:
        if not rf_health.satellite_guard():
            systemctl(["systemctl", "start", "rf-watchkeeper-scheduler.service"],check=False,timeout=30)
    finally:
        health_control.__exit__(None,None,None)
PY
