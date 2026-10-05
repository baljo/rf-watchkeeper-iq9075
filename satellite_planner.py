# Predict and filter METEOR-M N2-3/N2-4 passes using separate recording-horizon and peak-elevation thresholds; 2026-09-28 20:25 EEST, Thomas Vikström.
import argparse
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import requests
from skyfield.api import EarthSatellite, load, wgs84


SATELLITES = {
    "M2-3": {
        "name": "METEOR-M N2-3",
        "norad": 57166,
    },
    "M2-4": {
        "name": "METEOR-M N2-4",
        "norad": 59051,
    },
}

TLE_URL = "https://celestrak.org/NORAD/elements/gp.php?CATNR={norad}&FORMAT=TLE"
CACHE_FILE = Path(__file__).resolve().parent / "data" / "meteor_tles.json"
LOCAL_TZ = ZoneInfo("Europe/Helsinki")


def fetch_tle(name, norad):
    response = requests.get(
        TLE_URL.format(norad=norad),
        timeout=15,
        headers={"User-Agent": "RF-Watchkeeper/1.0"},
    )
    response.raise_for_status()

    lines = [line.strip() for line in response.text.splitlines() if line.strip()]

    if len(lines) < 3:
        raise RuntimeError(f"Unexpected TLE response for {name}: {response.text!r}")

    if not lines[1].startswith("1 ") or not lines[2].startswith("2 "):
        raise RuntimeError(f"Invalid TLE received for {name}")

    return {
        "name": lines[0],
        "norad": norad,
        "line1": lines[1],
        "line2": lines[2],
        "fetched_utc": datetime.now(timezone.utc).isoformat(),
    }


def load_satellites():
    CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)

    cache = {}
    if CACHE_FILE.exists():
        try:
            cache = json.loads(CACHE_FILE.read_text())
        except Exception:
            cache = {}

    updated_cache = dict(cache)
    results = []

    for short_name, info in SATELLITES.items():
        try:
            tle = fetch_tle(info["name"], info["norad"])
            updated_cache[short_name] = tle
            source = "CelesTrak"

        except Exception as exc:
            if short_name not in cache:
                raise RuntimeError(
                    f"Could not fetch TLE for {info['name']} and no cached TLE exists: {exc}"
                ) from exc

            tle = cache[short_name]
            source = "CACHE"
            print(f"WARNING: {info['name']}: using cached TLE ({exc})")

        results.append((short_name, tle, source))

    CACHE_FILE.write_text(json.dumps(updated_cache, indent=2) + "\n")
    return results


def direction(azimuth):
    directions = [
        "N", "NNE", "NE", "ENE",
        "E", "ESE", "SE", "SSE",
        "S", "SSW", "SW", "WSW",
        "W", "WNW", "NW", "NNW",
    ]
    return directions[int((azimuth + 11.25) // 22.5) % 16]


def local_string(dt):
    return dt.astimezone(LOCAL_TZ).strftime("%Y-%m-%d %H:%M:%S %Z")


def angle_at(satellite, observer, t):
    topocentric = (satellite - observer).at(t)
    altitude, azimuth, _ = topocentric.altaz()
    return altitude.degrees, azimuth.degrees


def predict_passes(
    satellite,
    observer,
    ts,
    start_dt,
    hours,
    horizon_elevation,
    min_peak_elevation,
):
    end_dt = start_dt + timedelta(hours=hours)

    times, events = satellite.find_events(
        observer,
        ts.from_datetime(start_dt),
        ts.from_datetime(end_dt),
        altitude_degrees=horizon_elevation,
    )

    passes = []
    current = None

    for t, event in zip(times, events):
        dt = t.utc_datetime().replace(tzinfo=timezone.utc)
        altitude, azimuth = angle_at(satellite, observer, t)

        if event == 0:
            current = {
                "aos": dt,
                "aos_az": azimuth,
            }

        elif event == 1 and current is not None:
            current["tca"] = dt
            current["max_elevation"] = altitude
            current["tca_az"] = azimuth

        elif event == 2 and current is not None:
            current["los"] = dt
            current["los_az"] = azimuth

            if (
                "tca" in current
                and current["max_elevation"] >= min_peak_elevation
            ):
                passes.append(current)

            current = None

    return passes


def main():
    parser = argparse.ArgumentParser(
        description="Predict upcoming RF Watchkeeper METEOR satellite passes."
    )

    parser.add_argument("--latitude", type=float, required=True)
    parser.add_argument("--longitude", type=float, required=True)

    parser.add_argument(
        "--elevation",
        type=float,
        default=10.0,
        help="Observer elevation above sea level in metres",
    )

    parser.add_argument("--hours", type=float, default=24.0)

    parser.add_argument(
        "--horizon-elevation",
        type=float,
        default=10.0,
        help="Elevation where recording would start/stop",
    )

    parser.add_argument(
        "--min-peak-elevation",
        type=float,
        default=20.0,
        help="Minimum maximum elevation required to keep a pass",
    )

    args = parser.parse_args()

    ts = load.timescale()

    observer = wgs84.latlon(
        latitude_degrees=args.latitude,
        longitude_degrees=args.longitude,
        elevation_m=args.elevation,
    )

    start_dt = datetime.now(timezone.utc)

    print()
    print("RF Watchkeeper - METEOR pass planner")
    print("=" * 72)
    print(
        f"Observer: {args.latitude:.6f}, {args.longitude:.6f}  "
        f"elevation {args.elevation:.0f} m"
    )
    print(
        f"Window:   {local_string(start_dt)} -> "
        f"{local_string(start_dt + timedelta(hours=args.hours))}"
    )
    print(f"Recording horizon:    {args.horizon_elevation:.1f} deg")
    print(f"Minimum peak elevation: {args.min_peak_elevation:.1f} deg")
    print()

    all_passes = []

    for short_name, tle, source in load_satellites():
        satellite = EarthSatellite(
            tle["line1"],
            tle["line2"],
            tle["name"],
            ts,
        )

        passes = predict_passes(
            satellite=satellite,
            observer=observer,
            ts=ts,
            start_dt=start_dt,
            hours=args.hours,
            horizon_elevation=args.horizon_elevation,
            min_peak_elevation=args.min_peak_elevation,
        )

        print(
            f"{short_name}: {tle['name']} "
            f"(NORAD {tle['norad']}, TLE source: {source})"
        )

        if not passes:
            print("  No qualifying passes.")
            print()
            continue

        for p in passes:
            duration = (p["los"] - p["aos"]).total_seconds() / 60.0

            print(
                f"  START {local_string(p['aos'])}   "
                f"{p['aos_az']:6.1f} deg {direction(p['aos_az'])}"
            )
            print(
                f"  PEAK  {local_string(p['tca'])}   "
                f"{p['max_elevation']:5.1f} deg elevation   "
                f"{p['tca_az']:6.1f} deg {direction(p['tca_az'])}"
            )
            print(
                f"  STOP  {local_string(p['los'])}   "
                f"{p['los_az']:6.1f} deg {direction(p['los_az'])}"
            )
            print(f"  Recording window: {duration:.1f} min")
            print()

            all_passes.append(
                (
                    p["aos"],
                    short_name,
                    p["max_elevation"],
                    p["los"],
                )
            )

    if all_passes:
        print("Chronological recording schedule")
        print("-" * 72)

        for aos, short_name, max_elevation, los in sorted(all_passes):
            duration = (los - aos).total_seconds() / 60.0

            print(
                f"{local_string(aos)}  "
                f"{short_name:4s}  "
                f"max {max_elevation:5.1f} deg  "
                f"{duration:4.1f} min"
            )

    print()


if __name__ == "__main__":
    main()
