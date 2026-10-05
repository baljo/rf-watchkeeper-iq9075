# Store and query the latest AIS targets in the shared RF Watchkeeper SQLite database; 2026-09-24 21:35 EEST, Thomas Vikström.
"""AIS persistence helpers for RF Watchkeeper."""

from datetime import datetime, timezone
from pathlib import Path
import sqlite3
import json
import math
import logging

ROOT = Path(__file__).resolve().parent
DEFAULT_DB = ROOT / "data" / "watchkeeper.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS ais_targets (
    mmsi            INTEGER PRIMARY KEY,
    first_seen      TEXT NOT NULL,
    last_seen       TEXT NOT NULL,
    message_count   INTEGER NOT NULL DEFAULT 1,
    message_type    INTEGER,
    channel         TEXT,
    latitude        REAL,
    longitude       REAL,
    distance_km     REAL,
    signalpower     REAL,
    ppm             REAL,
    speed_knots     REAL,
    course_deg      REAL,
    heading_deg     REAL,
    vessel_name     TEXT,
    callsign        TEXT,
    ship_type       INTEGER,
    source          TEXT NOT NULL DEFAULT 'live',
    decoder         TEXT NOT NULL DEFAULT 'AIS-catcher'
);

CREATE INDEX IF NOT EXISTS idx_ais_last_seen
    ON ais_targets(last_seen);
"""

UPSERT = """
INSERT INTO ais_targets (
    mmsi, first_seen, last_seen, message_count,
    message_type, channel, latitude, longitude, distance_km,
    signalpower, ppm, speed_knots, course_deg, heading_deg,
    vessel_name, callsign, ship_type, source, decoder
)
VALUES (?, ?, ?, 1, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'live', 'AIS-catcher')
ON CONFLICT(mmsi) DO UPDATE SET
    last_seen = excluded.last_seen,
    message_count = ais_targets.message_count + 1,
    message_type = excluded.message_type,
    channel = COALESCE(excluded.channel, ais_targets.channel),
    latitude = COALESCE(excluded.latitude, ais_targets.latitude),
    longitude = COALESCE(excluded.longitude, ais_targets.longitude),
    distance_km = COALESCE(excluded.distance_km, ais_targets.distance_km),
    signalpower = COALESCE(excluded.signalpower, ais_targets.signalpower),
    ppm = COALESCE(excluded.ppm, ais_targets.ppm),
    speed_knots = COALESCE(excluded.speed_knots, ais_targets.speed_knots),
    course_deg = COALESCE(excluded.course_deg, ais_targets.course_deg),
    heading_deg = COALESCE(excluded.heading_deg, ais_targets.heading_deg),
    vessel_name = COALESCE(excluded.vessel_name, ais_targets.vessel_name),
    callsign = COALESCE(excluded.callsign, ais_targets.callsign),
    ship_type = COALESCE(excluded.ship_type, ais_targets.ship_type)
"""


def connect(db_path=DEFAULT_DB):
    db_path = Path(db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(str(db_path), timeout=5.0)
    connection.execute("PRAGMA busy_timeout = 5000")
    connection.execute("PRAGMA journal_mode = WAL")
    connection.executescript(SCHEMA)
    columns = {row[1] for row in connection.execute('PRAGMA table_info(ais_targets)')}
    for name, kind in [('position_seen', 'TEXT'), ('motion_seen', 'TEXT'), ('is_base_station', 'INTEGER NOT NULL DEFAULT 0')]:
        if name not in columns:
            connection.execute('ALTER TABLE ais_targets ADD COLUMN ' + name + ' ' + kind)
            if name == 'position_seen':
                connection.execute('UPDATE ais_targets SET position_seen=last_seen WHERE latitude IS NOT NULL AND longitude IS NOT NULL')
            if name == 'motion_seen':
                connection.execute('UPDATE ais_targets SET motion_seen=position_seen WHERE speed_knots IS NOT NULL')
    connection.execute('UPDATE ais_targets SET is_base_station=1 WHERE message_type IN (4,11)')
    connection.commit()
    return connection


def observer_position():
    config = json.loads((ROOT / 'ais-config.json').read_text())
    return config['observer_lat'], config['observer_lon']


def position_distance(lat, lon, observer=None):
    if not all(isinstance(x, (int, float)) and not isinstance(x, bool) and math.isfinite(x) for x in (lat, lon)):
        return None
    if not (-90 <= lat <= 90 and -180 <= lon <= 180):
        return None
    a, b = observer or observer_position()
    a, b, c, d = map(math.radians, (a, b, lat, lon))
    h = math.sin((c-a)/2)**2 + math.cos(a)*math.cos(c)*math.sin((d-b)/2)**2
    return 6371.0088 * 2 * math.asin(math.sqrt(min(1, max(0, h))))


def seconds_since(timestamp, now):
    try:
        return max(0, (now - datetime.fromisoformat(timestamp.replace('Z', '+00:00')).astimezone(timezone.utc)).total_seconds())
    except (ValueError, TypeError, AttributeError):
        return float('inf')


def target_timeout(row, now):
    if row.get('is_base_station') or row.get('message_type') in (4, 11):
        return 86400
    if not row.get('position_seen') and row.get('latitude') is None:
        return 7200
    speed = row.get('speed_knots')
    if isinstance(speed, (int, float)) and 0 <= speed < 102.3 and row.get('motion_seen') == row.get('position_seen'):
        return 1800 if speed > 0.5 else 3600
    return 3600


def live_target(row, now):
    row = dict(row)
    timeout = target_timeout(row, now)
    if seconds_since(row['last_seen'], now) > timeout:
        return None
    distance = position_distance(row['latitude'], row['longitude'])
    if distance is None or distance > 250 or seconds_since(row.get('position_seen'), now) > timeout:
        row.update(latitude=None, longitude=None, distance_km=None)
    else:
        row['distance_km'] = distance
    return row


def normalize_received_at(message):
    """Return an ISO-8601 UTC receive/message time for AIS storage."""
    timestamp = message.get("timestamp")
    if isinstance(timestamp, str) and timestamp:
        return timestamp

    rxtime = message.get("rxtime")
    if isinstance(rxtime, str) and len(rxtime) == 14 and rxtime.isdigit():
        try:
            value = datetime.strptime(rxtime, "%Y%m%d%H%M%S")
            return value.replace(tzinfo=timezone.utc).isoformat().replace("+00:00", "Z")
        except ValueError:
            pass

    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def store_target(message, distance_km=None, db_path=DEFAULT_DB):
    message = dict(message)
    mmsi = message.get("mmsi")
    received_at = normalize_received_at(message)

    if not isinstance(mmsi, int):
        return False

    has_position = message.get('lat') is not None or message.get('lon') is not None
    if has_position:
        distance_km = position_distance(message.get('lat'), message.get('lon'))
        if distance_km is None or distance_km > 250:
            logging.warning('Rejected AIS position MMSI=%s lat=%s lon=%s distance_km=%s', mmsi, message.get('lat'), message.get('lon'), distance_km)
            return False

    values = (
        mmsi,
        received_at,
        received_at,
        message.get("type"),
        message.get("channel"),
        message.get("lat"),
        message.get("lon"),
        distance_km,
        message.get("signalpower"),
        message.get("ppm"),
        message.get("speed"),
        message.get("course"),
        message.get("heading"),
        message.get("shipname") or message.get("name"),
        message.get("callsign"),
        message.get("shiptype"),
    )

    connection = connect(db_path)
    try:
        if has_position:
            previous = connection.execute('SELECT latitude,longitude,position_seen FROM ais_targets WHERE mmsi=?', (mmsi,)).fetchone()
            previous_distance = position_distance(previous[0], previous[1]) if previous else None
            if previous_distance is not None and previous_distance <= 250:
                elapsed = seconds_since(previous[2], datetime.fromisoformat(received_at.replace('Z', '+00:00')))
                jump = position_distance(message['lat'], message['lon'], previous[:2])
                if elapsed < 3600 and jump > 2 + elapsed * 150 * 1.852 / 3600:
                    logging.warning('Rejected AIS jump MMSI=%s lat=%s lon=%s distance_km=%s jump_km=%s elapsed_s=%s', mmsi, message['lat'], message['lon'], distance_km, jump, elapsed)
                    return False
        connection.execute(UPSERT, values)
        connection.execute('UPDATE ais_targets SET position_seen=CASE WHEN ? THEN ? ELSE position_seen END, motion_seen=CASE WHEN ? THEN ? ELSE motion_seen END, is_base_station=MAX(is_base_station, ?) WHERE mmsi=?',
                           (has_position, received_at, has_position and message.get('speed') is not None, received_at, int(message.get('type') in (4, 11)), mmsi))
        connection.commit()
        return True
    finally:
        connection.close()


def recent_targets(limit=50, db_path=DEFAULT_DB, now=None):
    limit = max(1, min(int(limit), 500))
    connection = connect(db_path)

    try:
        connection.row_factory = sqlite3.Row
        rows = connection.execute(
            """
            SELECT *
            FROM ais_targets
            ORDER BY last_seen DESC
            """,
        ).fetchall()
        now = now or datetime.now(timezone.utc)
        return [target for row in rows if (target := live_target(row, now)) is not None][:limit]
    finally:
        connection.close()

MET_HYDRO_SCHEMA = """
CREATE TABLE IF NOT EXISTS ais_met_hydro (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    received_at     TEXT NOT NULL,
    mmsi            INTEGER NOT NULL,
    latitude        REAL,
    longitude       REAL,
    distance_km     REAL,
    bearing_deg     REAL,
    bearing_text    TEXT,
    wind_speed      REAL,
    wind_gust       REAL,
    wind_dir_deg    REAL,
    air_temp_c      REAL,
    humidity_pct    REAL,
    pressure_hpa    REAL,
    water_level_m   REAL,
    channel         TEXT,
    signalpower     REAL
);

CREATE INDEX IF NOT EXISTS idx_ais_met_hydro_time
    ON ais_met_hydro(received_at);
"""

INSERT_MET_HYDRO = """
INSERT INTO ais_met_hydro (
    received_at, mmsi, latitude, longitude,
    distance_km, bearing_deg, bearing_text,
    wind_speed, wind_gust, wind_dir_deg,
    air_temp_c, humidity_pct, pressure_hpa,
    water_level_m, channel, signalpower
)
VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
"""


def ensure_met_hydro_schema(connection):
    connection.executescript(MET_HYDRO_SCHEMA)


def store_met_hydro(message, distance_km=None, bearing_deg=None, bearing_text=None, db_path=DEFAULT_DB):
    if not (
        isinstance(message, dict)
        and message.get("type") == 8
        and message.get("dac") == 1
        and message.get("fid") == 31
        and isinstance(message.get("mmsi"), int)
    ):
        return False

    received_at = normalize_received_at(message)

    connection = connect(db_path)
    try:
        ensure_met_hydro_schema(connection)
        connection.execute(
            INSERT_MET_HYDRO,
            (
                received_at,
                message["mmsi"],
                message.get("lat"),
                message.get("lon"),
                distance_km,
                bearing_deg,
                bearing_text,
                message.get("wspeed"),
                message.get("wgust"),
                message.get("wdir"),
                message.get("airtemp"),
                message.get("humidity"),
                message.get("pressure"),
                message.get("waterlevel"),
                message.get("channel"),
                message.get("signalpower"),
            ),
        )
        connection.commit()
        return True
    finally:
        connection.close()


def recent_met_hydro(limit=50, db_path=DEFAULT_DB):
    limit = max(1, min(int(limit), 500))
    connection = connect(db_path)
    try:
        ensure_met_hydro_schema(connection)
        connection.row_factory = sqlite3.Row
        rows = connection.execute(
            """
            SELECT *
            FROM ais_met_hydro
            ORDER BY received_at DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
        return [dict(row) for row in rows]
    finally:
        connection.close()
