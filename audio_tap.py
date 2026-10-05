# Copy live PCM audio to the speaker while saving a bounded WAV recording and metadata; 2026-09-24 12:41 EEST, Thomas Vikström.
import argparse
from datetime import datetime, timezone
from pathlib import Path
import sqlite3
import sys
import wave


def prune_fm(db, keep=20):
    rows = db.execute(
        """
        SELECT id, file_path
        FROM audio_recordings
        WHERE source = 'fm'
        ORDER BY recorded_at DESC, id DESC
        LIMIT -1 OFFSET ?
        """,
        (keep,),
    ).fetchall()

    for row_id, file_path in rows:
        try:
            Path(file_path).unlink(missing_ok=True)
        except OSError:
            pass
        db.execute("DELETE FROM audio_recordings WHERE id = ?", (row_id,))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--db", type=Path, required=True)
    parser.add_argument("--frequency-hz", type=int, required=True)
    parser.add_argument("--rate", type=int, default=16000)
    parser.add_argument("--seconds", type=float, default=30.0)
    args = parser.parse_args()

    args.output.parent.mkdir(parents=True, exist_ok=True)

    max_bytes = int(args.rate * 2 * args.seconds)
    saved = 0

    with wave.open(str(args.output), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(args.rate)

        while True:
            block = sys.stdin.buffer.read(8192)
            if not block:
                break

            # Always keep live listening going.
            try:
                sys.stdout.buffer.write(block)
                sys.stdout.buffer.flush()
            except BrokenPipeError:
                break

            if saved < max_bytes:
                wanted = min(len(block), max_bytes - saved)
                wanted -= wanted % 2
                if wanted:
                    wav.writeframesraw(block[:wanted])
                    saved += wanted

    duration = saved / (args.rate * 2)

    # Don't retain an empty/broken capture.
    if duration <= 0:
        args.output.unlink(missing_ok=True)
        return 1

    recorded_at = datetime.now(timezone.utc).isoformat()

    with sqlite3.connect(args.db) as db:
        db.execute(
            """
            INSERT INTO audio_recordings (
                recorded_at,
                source,
                frequency_hz,
                modulation,
                duration_s,
                sample_rate_hz,
                channels,
                file_path,
                source_sdr,
                notes
            )
            VALUES (?, 'fm', ?, 'wbfm', ?, ?, 1, ?, ?, ?)
            """,
            (
                recorded_at,
                args.frequency_hz,
                round(duration, 3),
                args.rate,
                str(args.output),
                "RTL-SDR device 0",
                "Automatic RF Watchkeeper FM scheduler capture",
            ),
        )

        prune_fm(db, 20)
        db.commit()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
