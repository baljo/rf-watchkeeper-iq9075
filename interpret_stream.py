# Interpret new normalized ASR events while leaving dashboard-owned runs to their coordinator. 2026-09-20 20:13 EEST — Thomas Vikström.
"""Small JSONL bridge from transcription events to RF Watchkeeper summaries."""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

from interpret import genie_summary, make_event, fallback_summary


def interpret_one(event: dict, config: Path) -> dict:
    try:
        summary = genie_summary(event, config)
        return make_event(event, summary, "genie-qnn")
    except Exception as exc:  # preserve the event stream even if the model is unavailable
        return make_event(event, fallback_summary(event), "deterministic-fallback", str(exc))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--genie-config", type=Path, required=True)
    parser.add_argument("--poll-seconds", type=float, default=0.5)
    parser.add_argument("--from-start", action="store_true")
    args = parser.parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    position = 0
    with args.input.open("a+", encoding="utf-8") as stream:
        if not args.from_start:
            stream.seek(0, 2)
        while True:
            line = stream.readline()
            if not line:
                time.sleep(args.poll_seconds)
                continue
            position = stream.tell()
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not isinstance(event, dict) or event.get("event_type") != "transcription" or event.get("interpretation_owner") == "audio_workflow":
                continue
            output = interpret_one(event, args.genie_config)
            with args.output.open("a", encoding="utf-8") as target:
                target.write(json.dumps(output, ensure_ascii=False) + "\n")
                target.flush()
            print(json.dumps(output, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    raise SystemExit(main())
