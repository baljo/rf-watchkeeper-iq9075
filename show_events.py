# Print concise human-readable RF Watchkeeper events from the JSONL audit log. 2026-09-17 23:17 EEST — Thomas Vikström.
"""Show recent Watchkeeper events without exposing the full nested JSON."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def describe(event: dict) -> str:
    kind = event.get("event_type", "event")
    when = event.get("received_at", "?")
    if kind == "transcription":
        lang = event.get("language") or event.get("language_requested") or "?"
        return f"{when}  ASR [{lang}] {event.get('text', '').strip()}"
    if kind == "interpretation":
        backend = event.get("backend", "?")
        return f"{when}  Genie [{backend}] {event.get('summary', '').strip()}"
    if kind == "sensor_reading":
        return (f"{when}  {event.get('model', 'sensor')} "
                f"{event.get('temperature_c', '?')} °C, "
                f"{event.get('humidity_pct', '?')} %RH")
    return f"{when}  {kind}"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("log", help="JSONL event log")
    parser.add_argument("--last", type=int, default=12, help="number of matching events")
    args = parser.parse_args()
    events = []
    for line in Path(args.log).read_text(encoding="utf-8").splitlines():
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if event.get("event_type") in {"transcription", "interpretation", "sensor_reading"}:
            events.append(event)
    for event in events[-max(0, args.last):]:
        print(describe(event))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
