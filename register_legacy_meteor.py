# Register completed legacy satellite_capture.py METEOR recordings with meteor-auto; 2026-10-04 10:05 EEST, Thomas Vikström.
import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path("/root/rf-watchkeeper")
RECORDINGS = ROOT / "recordings/satellite"
STATE = ROOT / "data/meteor-auto"
PASSES = STATE / "passes"
MARKER = STATE / "legacy-bridge-start"


def load_json(path):
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def canonical_id(metadata):
    satellite = metadata.get("satellite")
    if satellite == "M2-3":
        prefix = "m23"
    elif satellite == "M2-4":
        prefix = "m24"
    else:
        raise ValueError(f"unsupported satellite {satellite!r}")

    aos = metadata.get("pass_start_10deg")
    if not aos:
        raise ValueError("missing pass_start_10deg")

    t = datetime.fromisoformat(aos).astimezone(timezone.utc)
    return f"{prefix}-{t.strftime('%Y%m%dT%H%M%SZ')}"


def register(raw_json):
    try:
        m = load_json(raw_json)
    except Exception as exc:
        print(f"SKIP {raw_json.name}: invalid JSON: {exc}")
        return False

    if m.get("status") != "completed":
        print(f"SKIP {raw_json.name}: status={m.get('status')!r}")
        return False

    if m.get("satellite") not in ("M2-3", "M2-4"):
        print(f"SKIP {raw_json.name}: not M2-3/M2-4")
        return False

    iq_value = m.get("iq_file")
    raw_iq = Path(iq_value) if iq_value else raw_json.with_suffix(".cu8")

    if not raw_iq.is_file():
        print(f"SKIP {raw_json.name}: IQ missing: {raw_iq}")
        return False

    iq_bytes = raw_iq.stat().st_size
    if iq_bytes <= 0 or iq_bytes % 2:
        print(f"SKIP {raw_json.name}: invalid IQ size {iq_bytes}")
        return False

    required = (
        "pass_start_10deg",
        "pass_stop_10deg",
        "record_start",
        "record_stop",
        "frequency_hz",
        "sample_rate_sps",
        "gain_db",
        "device_serial",
        "pre_margin_seconds",
        "post_margin_seconds",
    )
    missing = [k for k in required if k not in m]
    if missing:
        print(f"SKIP {raw_json.name}: missing metadata {missing}")
        return False

    pid = canonical_id(m)
    directory = PASSES / pid
    pass_json = directory / "pass.json"

    if pass_json.exists():
        existing = load_json(pass_json)
        existing_iq = existing.get("iq")
        if existing_iq and Path(existing_iq).resolve() != raw_iq.resolve():
            print(
                f"WARNING {pid}: managed record already exists with different IQ: "
                f"{existing_iq}"
            )
        else:
            print(f"SKIP {pid}: already managed")
        return False

    p = {
        "id": pid,
        "satellite": m["satellite"],
        "start": m["pass_start_10deg"],
        "stop": m["pass_stop_10deg"],
        "peak": None,
        "peak_deg": None,
        "peak_azimuth": None,
        "south_seconds": None,
        "tle_epoch": None,
        "tle_source": "legacy scheduled capture bridge",
        "record_start": m["record_start"],
        "record_stop": m["record_stop"],
        "trigger": m["record_start"],
        "frequency": m["frequency_hz"],
        "sample_rate": m["sample_rate_sps"],
        "gain": m["gain_db"],
        "device": m["device_serial"],
        "pre_margin": m["pre_margin_seconds"],
        "post_margin": m["post_margin_seconds"],
        "preflight_seconds": 0,
        "status": "attempted",
    }

    record = {
        "schema_version": 1,
        "owner": "meteor-auto-v1",
        "pass": p,
        "state": "pending_decode",
        "iq": str(raw_iq.resolve()),
        "capture_metadata": str(raw_json.resolve()),
        "started_at": m.get("actual_start"),
        "capture_finished_at": m.get("actual_stop"),
        "capture_returncode": m.get("rtl_sdr_returncode"),
        "capture": m,
        "captured_iq_bytes": iq_bytes,
        "scheduler_restored": True,
        "score": None,
        "analysis": None,
        "notification": None,
        "backfilled_from_legacy_capture": True,
    }

    directory.mkdir(parents=True, exist_ok=False)

    tmp = directory / "pass.json.tmp"
    with tmp.open("x", encoding="utf-8") as f:
        json.dump(record, f, indent=2)
        f.write("\n")
        f.flush()
        os.fsync(f.fileno())

    tmp.replace(pass_json)

    print(
        f"REGISTERED {pid}: {m['satellite']} "
        f"{m['record_start']} IQ={iq_bytes} bytes"
    )
    return True


def scan():
    if not MARKER.exists():
        raise RuntimeError(f"installation marker missing: {MARKER}")

    threshold = MARKER.stat().st_mtime - 5

    candidates = []
    for path in RECORDINGS.glob("M2-*.json"):
        try:
            if path.stat().st_mtime >= threshold:
                candidates.append(path)
        except FileNotFoundError:
            continue

    for path in sorted(candidates):
        register(path)


def main():
    parser = argparse.ArgumentParser(
        description="Register completed legacy METEOR captures with meteor-auto"
    )
    parser.add_argument("--json", type=Path)
    args = parser.parse_args()

    PASSES.mkdir(parents=True, exist_ok=True)

    if args.json:
        register(args.json.resolve())
    else:
        scan()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
