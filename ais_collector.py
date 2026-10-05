# Run AIS-catcher, persist AIS targets, calculate distance/bearing, and publish meaningful RF Watchkeeper events; 2026-09-24 22:05 EEST, Thomas Vikström.
"""Scheduler-friendly AIS collector for RF Watchkeeper."""

import argparse
from datetime import datetime, timezone
import json
import math
from pathlib import Path
import subprocess
import time
import selectors
import os
import re
import signal
import rf_health

import ais_store

ROOT = Path(__file__).resolve().parent
CONFIG = ROOT / "ais-config.json"
STATUS = ROOT / "logs" / "ais-status.json"
EVENTS = ROOT / "logs" / "events.jsonl"

COMMAND = [
    "/root/AIS-catcher",
    "-d", "V4MAIN01",
    "-o", "5",
    "-gr", "tuner", "auto", "rtlagc", "on",
    "-a", "192K",
    "-b",
]


def utc_now():
    return datetime.now(timezone.utc).isoformat()


def load_observer():
    try:
        config = json.loads(CONFIG.read_text(encoding="utf-8"))
        lat = config.get("observer_lat")
        lon = config.get("observer_lon")

        if isinstance(lat, (int, float)) and isinstance(lon, (int, float)):
            if -90 <= lat <= 90 and -180 <= lon <= 180:
                return float(lat), float(lon)
    except (OSError, ValueError, TypeError):
        pass

    return None


def distance_km(observer, lat, lon):
    if observer is None:
        return None
    if not isinstance(lat, (int, float)) or not isinstance(lon, (int, float)):
        return None

    lat1, lon1 = map(math.radians, observer)
    lat2 = math.radians(float(lat))
    lon2 = math.radians(float(lon))

    dlat = lat2 - lat1
    dlon = lon2 - lon1

    a = (
        math.sin(dlat / 2) ** 2
        + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    )

    return 6371.0088 * 2 * math.asin(math.sqrt(a))


def bearing_deg(observer, lat, lon):
    if observer is None:
        return None
    if not isinstance(lat, (int, float)) or not isinstance(lon, (int, float)):
        return None

    lat1, lon1 = map(math.radians, observer)
    lat2 = math.radians(float(lat))
    lon2 = math.radians(float(lon))

    dlon = lon2 - lon1

    x = math.sin(dlon) * math.cos(lat2)
    y = (
        math.cos(lat1) * math.sin(lat2)
        - math.sin(lat1) * math.cos(lat2) * math.cos(dlon)
    )

    return (math.degrees(math.atan2(x, y)) + 360) % 360


def compass_direction(degrees):
    if degrees is None:
        return None

    points = (
        "N", "NNE", "NE", "ENE",
        "E", "ESE", "SE", "SSE",
        "S", "SSW", "SW", "WSW",
        "W", "WNW", "NW", "NNW",
    )

    return points[int((degrees + 11.25) // 22.5) % 16]


def write_status(state, messages=0, unique_mmsi=0, error=None):
    STATUS.parent.mkdir(parents=True, exist_ok=True)

    payload = {
        "updated_at": utc_now(),
        "state": state,
        "device": "V4MAIN01",
        "decoder": "AIS-catcher",
        "messages": messages,
        "unique_mmsi": unique_mmsi,
        "observer_configured": load_observer() is not None,
        "error": error,
    }

    temporary = STATUS.with_suffix(".tmp")
    temporary.write_text(json.dumps(payload), encoding="utf-8")
    temporary.replace(STATUS)


def publish_event(kind, message, distance=None, bearing=None):
    EVENTS.parent.mkdir(parents=True, exist_ok=True)

    event = {
        "schema_version": 1,
        "event_type": kind,
        "received_at": utc_now(),
        "source": "live",
        "decoder": "AIS-catcher",
        "mmsi": message.get("mmsi"),
        "message_type": message.get("type"),
        "channel": message.get("channel"),
        "latitude": message.get("lat"),
        "longitude": message.get("lon"),
        "distance_km": distance,
        "bearing_deg": bearing,
        "bearing_text": compass_direction(bearing),
        "vessel_name": message.get("shipname") or message.get("name"),
        "callsign": message.get("callsign"),
        "speed_knots": message.get("speed"),
        "course_deg": message.get("course"),
        "heading_deg": message.get("heading"),
    }

    with EVENTS.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(event, ensure_ascii=False, allow_nan=False) + "\n")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seconds", type=float, default=0,
                        help="0 means run continuously")
    parser.add_argument("--health-id", type=int)
    args = parser.parse_args()
    interrupted = [False]
    def request_stop(*unused):
        interrupted[0] = True
    signal.signal(signal.SIGTERM, request_stop)
    signal.signal(signal.SIGINT, request_stop)
    health_id = args.health_id or rf_health.begin("ais-diagnostic", args.seconds or 3600)
    started = time.monotonic()
    diagnostics = []
    intentional = False
    failure = None
    pending = ""

    if args.seconds < 0:
        raise ValueError("seconds must be nonnegative")

    observer = load_observer()

    seen = set()
    known_identity = {}
    last_position_event = {}

    count = 0
    deadline = time.monotonic() + args.seconds if args.seconds else None

    write_status("starting")

    process = subprocess.Popen(
        COMMAND + (["-T", str(math.ceil(args.seconds) + 2)] if args.seconds else []),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
    )

    write_status("running")

    selector = selectors.DefaultSelector()
    selector.register(process.stdout, selectors.EVENT_READ)

    try:
        while True:
            if interrupted[0]:
                failure = "Collector interrupted before configured dwell"
                break
            returncode = process.poll()
            if returncode is not None:
                raise RuntimeError(
                    f"AIS-catcher exited before the requested stop (exit code {returncode})"
                )

            if deadline is not None and time.monotonic() >= deadline:
                intentional = True
                break

            timeout = 0.25

            if deadline is not None:
                timeout = min(
                    timeout,
                    max(0.0, deadline - time.monotonic()),
                )

            if '\n' not in pending:
                events = selector.select(timeout)
                if not events:
                    continue
                block = os.read(process.stdout.fileno(), 65536)
                if not block:
                    continue
                pending += block.decode('utf-8', errors='replace')
                if len(pending) > 1048576:
                    raise RuntimeError('AIS output line exceeded safe bound')
                if '\n' not in pending:
                    continue
            line, pending = pending.split('\n', 1)
            diagnostics.append(line)

            if not line:
                continue

            line = line.strip()

            if not line.startswith("{"):
                print(line, flush=True)
                continue

            try:
                message = json.loads(line)
            except json.JSONDecodeError:
                continue

            if message.get("class") != "AIS":
                continue

            if message.get("type") == 8:
                debug_path = ROOT / "logs" / "ais-type8-raw.jsonl"
                with debug_path.open("a", encoding="utf-8") as debug:
                    debug.write(json.dumps(message, ensure_ascii=False, allow_nan=False) + "\n")

            mmsi = message.get("mmsi")
            if not isinstance(mmsi, int):
                continue

            if message.get('lat') is not None or message.get('lon') is not None:
                validated_distance = ais_store.position_distance(message.get('lat'), message.get('lon'), observer)
                if validated_distance is None or validated_distance > 250:
                    print(json.dumps({'rejected_position': True, 'mmsi': mmsi, 'lat': message.get('lat'), 'lon': message.get('lon'), 'distance_km': validated_distance}), flush=True)
                    continue

            distance = distance_km(
                observer,
                message.get("lat"),
                message.get("lon"),
            )

            bearing = bearing_deg(
                observer,
                message.get("lat"),
                message.get("lon"),
            )

            is_met_hydro = (
                message.get("type") == 8
                and message.get("dac") == 1
                and message.get("fid") == 31
            )

            was_new = mmsi not in seen
            seen.add(mmsi)

            identity = (
                message.get("shipname") or message.get("name"),
                message.get("callsign"),
            )

            identity_changed = (
                any(identity)
                and known_identity.get(mmsi) != identity
            )

            if any(identity):
                known_identity[mmsi] = identity

            if is_met_hydro:
                ais_store.store_met_hydro(
                    message,
                    distance_km=distance,
                    bearing_deg=bearing,
                    bearing_text=compass_direction(bearing),
                )
            else:
                if not ais_store.store_target(message, distance):
                    continue

            count += 1

            now = time.monotonic()

            if was_new and not is_met_hydro:
                publish_event("ais_target_discovered", message, distance, bearing)

            if identity_changed:
                publish_event("ais_identity", message, distance, bearing)

            if is_met_hydro:
                publish_event("ais_met_hydro", message, distance, bearing)
            elif (
                distance is not None
                and now - last_position_event.get(mmsi, -1e9) >= 60
            ):
                publish_event("ais_position", message, distance, bearing)
                last_position_event[mmsi] = now

            print(
                json.dumps({
                    "mmsi": mmsi,
                    "type": message.get("type"),
                    "channel": message.get("channel"),
                    "name": identity[0],
                    "callsign": identity[1],
                    "lat": message.get("lat"),
                    "lon": message.get("lon"),
                    "distance_km": distance,
                    "bearing_deg": bearing,
                    "bearing_text": compass_direction(bearing),
                    "signalpower": message.get("signalpower"),
                }, allow_nan=False),
                flush=True,
            )

            write_status("running", count, len(seen))

    except KeyboardInterrupt:
        failure = "Collector interrupted"
    except BaseException as exc:
        failure = str(exc)
        raise

    finally:
        selector.close()
        # AIS-catcher prints its sample-processing benchmark on graceful SIGINT.
        if process.poll() is None:
            process.send_signal(signal.SIGINT)
        forced = False
        try:
            tail, _ = process.communicate(timeout=5)
        except subprocess.TimeoutExpired:
            forced = True
            process.kill()
            tail, _ = process.communicate(timeout=3)
        diagnostics.append(pending + (tail or ""))
        diagnostic_text = "".join(diagnostics)
        timings = re.findall(r"\[[^\n]+\]\s+([0-9]+(?:\.[0-9]+)?)\s+ms", diagnostic_text)
        processing_ms = sum(float(value) for value in timings)
        ok = intentional and not forced and failure is None and process.returncode in (0, 254, -signal.SIGINT) and processing_ms > 0
        if interrupted[0]:
            rf_health.cancel(health_id, 'AIS intentionally released by scheduler stop')
        rf_health.finish(health_id, ok, processing_ms, "AIS sample DSP milliseconds", process.returncode,
                         failure or ("Forced cleanup" if forced else "No DSP sample evidence / abnormal exit"),
                         {"messages":count,"unique_mmsi":len(seen),"status":"decoded" if count else "quiet"})
        write_status("paused" if interrupted[0] else "stopped" if ok else "failed", count, len(seen),
                     None if ok or interrupted[0] else failure or "No sample evidence / abnormal completion")


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        write_status("failed", error=str(error))
        raise
