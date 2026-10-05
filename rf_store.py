# Store RF observations and query adaptive Nexus history without reducing stored readings; 2026-09-25 08:17 EEST — Thomas Vikström.
"""Small SQLite data layer for RF Watchkeeper structured observations."""

import argparse
from datetime import datetime, timedelta, timezone
import json
import math
from pathlib import Path
import sqlite3


ROOT = Path(__file__).resolve().parent
DEFAULT_DB = ROOT / "data" / "watchkeeper.db"


SCHEMA = """
CREATE TABLE IF NOT EXISTS nexus_measurements (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    received_at     TEXT NOT NULL,
    source          TEXT NOT NULL,
    decoder         TEXT,
    model           TEXT NOT NULL,
    device_key      TEXT NOT NULL,
    sensor_id       INTEGER NOT NULL,
    channel         INTEGER NOT NULL,
    frequency_hz    INTEGER,
    temperature_c   REAL NOT NULL,
    humidity_pct    REAL NOT NULL,
    battery_ok      INTEGER NOT NULL,

    UNIQUE(received_at, device_key, source)
);

CREATE INDEX IF NOT EXISTS idx_nexus_received_at
    ON nexus_measurements(received_at);

CREATE INDEX IF NOT EXISTS idx_nexus_device_time
    ON nexus_measurements(device_key, received_at);
"""


INSERT_NEXUS = """
INSERT OR IGNORE INTO nexus_measurements (
    received_at,
    source,
    decoder,
    model,
    device_key,
    sensor_id,
    channel,
    frequency_hz,
    temperature_c,
    humidity_pct,
    battery_ok
)
VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
"""


def connect(db_path=DEFAULT_DB):
    """Open the Watchkeeper database and ensure its schema exists."""
    db_path = Path(db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)

    connection = sqlite3.connect(str(db_path), timeout=5.0)
    connection.execute("PRAGMA busy_timeout = 5000")
    connection.execute("PRAGMA journal_mode = WAL")
    connection.executescript(SCHEMA)

    return connection


def is_live_nexus(event):
    """Return True only for normalized live Nexus sensor observations."""
    return (
        isinstance(event, dict)
        and event.get("schema_version") == 1
        and event.get("event_type") == "sensor_reading"
        and event.get("source") == "live"
        and event.get("model") == "Nexus-TH"
    )


def nexus_values(event):
    """Convert one normalized Nexus event into database column values."""
    return (
        event["received_at"],
        event["source"],
        event.get("decoder"),
        event["model"],
        event["device_key"],
        int(event["sensor_id"]),
        int(event["channel"]),
        event.get("frequency_hz"),
        float(event["temperature_c"]),
        float(event["humidity_pct"]),
        1 if event["battery_ok"] else 0,
    )


def store_nexus(event, db_path=DEFAULT_DB):
    """Persist one normalized Nexus observation; duplicate events are ignored."""
    if not is_live_nexus(event):
        return False

    connection = connect(db_path)

    try:
        cursor = connection.execute(INSERT_NEXUS, nexus_values(event))
        connection.commit()
        return cursor.rowcount == 1
    finally:
        connection.close()


def nexus_history(limit=1000, db_path=DEFAULT_DB):
    """Return recent Nexus observations in oldest-to-newest order."""
    limit = max(1, min(int(limit), 100000))

    connection = connect(db_path)

    try:
        connection.row_factory = sqlite3.Row

        rows = connection.execute(
            """
            SELECT
                received_at,
                source,
                decoder,
                model,
                device_key,
                sensor_id,
                channel,
                frequency_hz,
                temperature_c,
                humidity_pct,
                battery_ok
            FROM nexus_measurements
            ORDER BY received_at DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
    finally:
        connection.close()

    events = []

    for row in reversed(rows):
        events.append({
            "schema_version": 1,
            "event_type": "sensor_reading",
            "received_at": row["received_at"],
            "source": row["source"],
            "decoder": row["decoder"],
            "model": row["model"],
            "device_key": row["device_key"],
            "sensor_id": row["sensor_id"],
            "channel": row["channel"],
            "frequency_hz": row["frequency_hz"],
            "temperature_c": row["temperature_c"],
            "humidity_pct": row["humidity_pct"],
            "battery_ok": bool(row["battery_ok"]),
        })

    return events


def nexus_chart_history(period="24", device_key=None, db_path=DEFAULT_DB, now=None):
    """Read the complete selected range; aggregate only the response, never storage.

    Continuous runs are separate groups, even inside the same time bucket.
    Exceptionally fragmented history may exceed 1,000 points to retain every gap.
    """
    periods = {"1": 1, "6": 6, "24": 24, "168": 168, "720": 720, "all": None}
    if period not in periods:
        raise ValueError("Unknown Nexus history period")
    now = now or datetime.now(timezone.utc)
    until = now.isoformat(timespec="milliseconds").replace("+00:00", "Z")
    since = ((now - timedelta(hours=periods[period])).isoformat(timespec="milliseconds")
             .replace("+00:00", "Z") if periods[period] else "")
    # A display request must not create, migrate, or write the measurement database.
    connection = sqlite3.connect(Path(db_path).resolve().as_uri() + "?mode=ro", uri=True, timeout=5)
    connection.row_factory = sqlite3.Row
    try:
        connection.execute("BEGIN")
        sensors = [dict(row) for row in connection.execute("""
            SELECT device_key, COUNT(*) AS stored_count, MAX(received_at) AS latest_at
            FROM nexus_measurements WHERE source='live' AND model='Nexus-TH'
            GROUP BY device_key ORDER BY latest_at DESC, device_key
        """)]
        if not device_key and sensors:
            device_key = sensors[0]["device_key"]
        stored_count = next((s["stored_count"] for s in sensors if s["device_key"] == device_key), 0)
        where = "device_key=? AND source='live' AND model='Nexus-TH' AND received_at>=? AND received_at<=?"
        params = (device_key, since, until)
        stats = connection.execute("SELECT COUNT(*), MIN(received_at), MAX(received_at) "
                                   "FROM nexus_measurements WHERE " + where, params).fetchone()
        count, first, last = stats
        span = ((datetime.fromisoformat(last.replace("Z", "+00:00")) -
                 datetime.fromisoformat(first.replace("Z", "+00:00"))).total_seconds() if count else 0)
        widths = (60, 120, 180, 300, 600, 900, 1800, 3600, 7200, 10800, 21600, 43200, 86400)
        needed = span / 800
        width = (next((w for w in widths if w >= needed), math.ceil(needed / 86400) * 86400)
                 if count > 1000 else 0)
        # Round to milliseconds to avoid floating-point noise at the 180-second boundary.
        cte = """
            WITH timed AS (
                SELECT id, received_at, temperature_c, humidity_pct,
                       ROUND((julianday(received_at)-2440587.5)*86400, 3) AS stamp
                FROM nexus_measurements WHERE """ + where + """
            ), previous AS (
                SELECT *, LAG(stamp) OVER (ORDER BY received_at, id) AS previous_stamp FROM timed
            ), runs AS (
                SELECT *, SUM(CASE WHEN previous_stamp IS NULL OR stamp-previous_stamp>180
                                   THEN 1 ELSE 0 END)
                          OVER (ORDER BY received_at, id) AS segment FROM previous
            )
        """
        def query(bucket_seconds):
            if not bucket_seconds:
                return [dict(row) for row in connection.execute(cte + """
                    SELECT received_at, received_at AS first_at, received_at AS last_at,
                           temperature_c, humidity_pct, temperature_c AS temperature_min,
                           temperature_c AS temperature_max, 1 AS sample_count, segment
                    FROM runs ORDER BY received_at, id
                """, params)]
            return [dict(row) for row in connection.execute(cte + """
                SELECT MIN(received_at) AS received_at, MIN(received_at) AS first_at,
                       MAX(received_at) AS last_at, AVG(temperature_c) AS temperature_c,
                       AVG(humidity_pct) AS humidity_pct, MIN(temperature_c) AS temperature_min,
                       MAX(temperature_c) AS temperature_max, COUNT(*) AS sample_count, segment
                FROM runs GROUP BY segment, CAST(stamp / ? AS INTEGER)
                ORDER BY MIN(received_at)
            """, params + (bucket_seconds,))]
        points = query(width)
        # Coarsen if splitting buckets at gaps creates too many points. Never truncate runs.
        segments = len({point["segment"] for point in points})
        while width and len(points) > max(1000, segments) and width < max(span * 2, 60):
            width *= 2
            points = query(width)
        return {"points": points, "sensors": sensors, "device_key": device_key,
                "period": period, "stored_count": stored_count, "range_count": count,
                "displayed_count": len(points), "bucket_seconds": width,
                "first_at": first, "last_at": last,
                "gap_limited": len(points) > 1000}
    finally:
        connection.close()


def count_nexus(db_path=DEFAULT_DB):
    """Return the number of persisted Nexus observations."""
    connection = connect(db_path)

    try:
        return connection.execute(
            "SELECT COUNT(*) FROM nexus_measurements"
        ).fetchone()[0]
    finally:
        connection.close()


def backfill_jsonl(path, db_path=DEFAULT_DB):
    """Import existing normalized live Nexus observations from an event journal."""
    path = Path(path)

    read_count = 0
    nexus_count = 0
    inserted_count = 0
    invalid_count = 0

    connection = connect(db_path)

    try:
        with path.open("r", encoding="utf-8") as source:
            for line in source:
                read_count += 1

                try:
                    event = json.loads(line)
                except (json.JSONDecodeError, UnicodeError):
                    invalid_count += 1
                    continue

                if not is_live_nexus(event):
                    continue

                nexus_count += 1

                try:
                    cursor = connection.execute(
                        INSERT_NEXUS,
                        nexus_values(event),
                    )
                    inserted_count += cursor.rowcount
                except (KeyError, TypeError, ValueError, sqlite3.Error):
                    invalid_count += 1

        connection.commit()

    finally:
        connection.close()

    return read_count, nexus_count, inserted_count, invalid_count


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--backfill", type=Path)
    parser.add_argument("--count", action="store_true")
    args = parser.parse_args()

    connection = connect(args.db)
    connection.close()

    if args.backfill:
        total, nexus, inserted, invalid = backfill_jsonl(
            args.backfill,
            args.db,
        )

        print("JSONL records read:", total)
        print("Live Nexus records found:", nexus)
        print("New SQLite rows inserted:", inserted)
        print("Invalid records skipped:", invalid)

    if args.count or args.backfill:
        print("Nexus rows in database:", count_nexus(args.db))

    print("Database:", args.db)


if __name__ == "__main__":
    main()
