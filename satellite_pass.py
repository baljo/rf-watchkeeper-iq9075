# Build and score RF Watchkeeper satellite pass records without touching the SDR or raw IQ; 2026-09-28 21:49 EEST, Thomas Vikström.
import argparse
import json
from datetime import datetime
from pathlib import Path

WEIGHTS = {
    "carrier": 20.0,
    "sync": 25.0,
    "image_lines": 35.0,
    "continuity": 15.0,
    "output_valid": 5.0,
}

DEFAULT_SHIFTS_HZ = [0, 20000, 30000, 45000]


def clamp01(value):
    return max(0.0, min(1.0, float(value)))


def calculate_score(metrics):
    components = {
        "carrier": clamp01(metrics.get("carrier", 0.0)),
        "sync": clamp01(metrics.get("sync", 0.0)),
        "image_lines": clamp01(metrics.get("image_lines", 0.0)),
        "continuity": clamp01(metrics.get("continuity", 0.0)),
        "output_valid": clamp01(metrics.get("output_valid", 0.0)),
    }

    weighted = {
        key: round(components[key] * WEIGHTS[key], 2)
        for key in WEIGHTS
    }

    total = round(sum(weighted.values()), 2)
    return total, components, weighted


def load_json(path):
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def save_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".json.tmp")
    with tmp.open("w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
        f.write("\n")
    tmp.replace(path)


def command_init(args):
    iq = Path(args.iq).resolve()

    if not iq.exists():
        raise SystemExit(f"IQ file does not exist: {iq}")

    stem = iq.stem
    output_dir = Path(args.output_root).resolve() / stem
    output_dir.mkdir(parents=True, exist_ok=True)

    pass_json = output_dir / "pass.json"

    if pass_json.exists() and not args.force:
        raise SystemExit(
            f"{pass_json} already exists. Use --force only if you intentionally want to recreate it."
        )

    stat = iq.stat()

    record = {
        "schema_version": 1,
        "created_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "satellite": args.satellite,
        "pass": {
            "aos": args.aos,
            "max_elevation_deg": args.max_elevation,
            "los": args.los,
            "aos_azimuth_deg": args.aos_azimuth,
            "max_azimuth_deg": args.max_azimuth,
            "los_azimuth_deg": args.los_azimuth,
        },
        "capture": {
            "iq_file": str(iq),
            "size_bytes": stat.st_size,
            "mtime": datetime.fromtimestamp(
                stat.st_mtime
            ).astimezone().isoformat(timespec="seconds"),
            "frequency_hz": args.frequency,
            "sample_rate_sps": args.sample_rate,
            "gain_db": args.gain,
            "raw_iq_preserved": True,
        },
        "setup": {
            "antenna": args.antenna,
            "location": args.location,
            "notes": args.notes,
        },
        "decoder": {
            "candidate_frequency_shifts_hz": DEFAULT_SHIFTS_HZ,
            "trials": [],
            "best_trial_shift_hz": None,
        },
        "score": {
            "technical_score_0_100": None,
            "weights": WEIGHTS,
            "note": "Convenience score only; raw metrics remain authoritative.",
        },
    }

    save_json(pass_json, record)

    print(f"Created: {pass_json}")
    print(f"Raw IQ unchanged: {iq}")
    print(f"Size: {stat.st_size:,} bytes")


def command_trial(args):
    pass_json = Path(args.pass_json).resolve()

    if not pass_json.exists():
        raise SystemExit(f"Pass record does not exist: {pass_json}")

    record = load_json(pass_json)

    metrics = {
        "carrier": args.carrier,
        "sync": args.sync,
        "image_lines": args.image_lines,
        "continuity": args.continuity,
        "output_valid": args.output_valid,
    }

    score, normalized, weighted = calculate_score(metrics)

    trial = {
        "recorded_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "frequency_shift_hz": args.shift,
        "raw_metrics": {
            "carrier": args.carrier,
            "sync": args.sync,
            "image_lines": args.image_lines,
            "continuity": args.continuity,
            "output_valid": args.output_valid,
            "decoded_lines": args.decoded_lines,
            "expected_lines": args.expected_lines,
            "sync_events": args.sync_events,
            "dropout_fraction": args.dropout_fraction,
        },
        "normalized_metrics": normalized,
        "weighted_components": weighted,
        "technical_score_0_100": score,
        "decode_log": args.decode_log,
        "output_files": args.output_file or [],
        "notes": args.notes,
    }

    trials = record["decoder"]["trials"]

    # Replace an existing result for the same frequency shift.
    trials[:] = [
        t for t in trials
        if int(t.get("frequency_shift_hz", -999999)) != args.shift
    ]
    trials.append(trial)
    trials.sort(key=lambda t: int(t["frequency_shift_hz"]))

    best = max(
        trials,
        key=lambda t: float(t.get("technical_score_0_100", 0.0))
    )

    record["decoder"]["best_trial_shift_hz"] = best["frequency_shift_hz"]
    record["score"]["technical_score_0_100"] = best["technical_score_0_100"]
    record["score"]["best_trial_components"] = best["weighted_components"]

    save_json(pass_json, record)

    print(f"Recorded shift: {args.shift:+d} Hz")
    print(f"Technical score: {score:.2f}/100")
    print(
        f"Best recorded shift: "
        f"{record['decoder']['best_trial_shift_hz']:+d} Hz"
    )


def command_show(args):
    record = load_json(Path(args.pass_json).resolve())

    print(f"Satellite: {record['satellite']}")
    print(f"IQ:        {record['capture']['iq_file']}")
    print(
        f"Score:     "
        f"{record['score']['technical_score_0_100']}"
    )

    trials = record["decoder"]["trials"]

    if not trials:
        print("Trials:    none yet")
        return

    print("\nShift       Score")
    print("-----------------")
    for trial in trials:
        print(
            f"{trial['frequency_shift_hz']:+7d} Hz   "
            f"{trial['technical_score_0_100']:6.2f}"
        )


def build_parser():
    parser = argparse.ArgumentParser(
        description="RF Watchkeeper satellite pass metadata and scoring."
    )

    sub = parser.add_subparsers(dest="command", required=True)

    p_init = sub.add_parser("init")
    p_init.add_argument("--iq", required=True)
    p_init.add_argument("--satellite", required=True)
    p_init.add_argument(
        "--output-root",
        default="/root/rf-watchkeeper/processed/satellite",
    )
    p_init.add_argument("--aos")
    p_init.add_argument("--max-elevation", type=float)
    p_init.add_argument("--los")
    p_init.add_argument("--aos-azimuth", type=float)
    p_init.add_argument("--max-azimuth", type=float)
    p_init.add_argument("--los-azimuth", type=float)
    p_init.add_argument("--frequency", type=int, required=True)
    p_init.add_argument("--sample-rate", type=int, required=True)
    p_init.add_argument("--gain", type=float, required=True)
    p_init.add_argument("--antenna")
    p_init.add_argument("--location")
    p_init.add_argument("--notes")
    p_init.add_argument("--force", action="store_true")
    p_init.set_defaults(func=command_init)

    p_trial = sub.add_parser("trial")
    p_trial.add_argument("--pass-json", required=True)
    p_trial.add_argument("--shift", required=True, type=int)

    p_trial.add_argument("--carrier", type=float, required=True)
    p_trial.add_argument("--sync", type=float, required=True)
    p_trial.add_argument("--image-lines", type=float, required=True)
    p_trial.add_argument("--continuity", type=float, required=True)
    p_trial.add_argument("--output-valid", type=float, required=True)

    p_trial.add_argument("--decoded-lines", type=int)
    p_trial.add_argument("--expected-lines", type=int)
    p_trial.add_argument("--sync-events", type=int)
    p_trial.add_argument("--dropout-fraction", type=float)
    p_trial.add_argument("--decode-log")
    p_trial.add_argument("--output-file", action="append")
    p_trial.add_argument("--notes")
    p_trial.set_defaults(func=command_trial)

    p_show = sub.add_parser("show")
    p_show.add_argument("--pass-json", required=True)
    p_show.set_defaults(func=command_show)

    return parser


def main():
    parser = build_parser()
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
