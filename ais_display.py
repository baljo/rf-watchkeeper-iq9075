"""Read-only display enrichment from the original AIS observations."""
import json
from pathlib import Path


def enrich_met_hydro(rows, path):
    result = [dict(row, visibility=None, visgreater=None) for row in rows]
    wanted = {}
    for row in result:
        key = (row['received_at'], row['mmsi'], row['latitude'], row['longitude'])
        wanted.setdefault(key, []).append(row)
    if not wanted:
        return result
    try:
        # The state API only returns the latest 50 records. Read a bounded tail;
        # missing/rotated raw observations remain unavailable, never inferred.
        with Path(path).open('rb') as stream:
            stream.seek(0, 2)
            start = max(0, stream.tell() - 2 * 1024 * 1024)
            stream.seek(start)
            if start:
                stream.readline()
            lines = stream.read().splitlines()
    except OSError:
        return result
    for line in reversed(lines):
        try:
            message = json.loads(line)
            if not isinstance(message, dict) or (message.get('type'), message.get('dac'), message.get('fid')) != (8, 1, 31):
                continue
            timestamp = message.get('timestamp')
            if not isinstance(timestamp, str) or not timestamp:
                raw = message.get('rxtime', '')
                if not isinstance(raw, str) or len(raw) != 14 or not raw.isdigit():
                    continue
                timestamp = '{}-{}-{}T{}:{}:{}Z'.format(raw[:4], raw[4:6], raw[6:8], raw[8:10], raw[10:12], raw[12:14])
            key = (timestamp, message.get('mmsi'), message.get('lat'), message.get('lon'))
            for row in wanted.pop(key, []):
                row['visibility'] = message.get('visibility')
                row['visgreater'] = message.get('visgreater')
            if not wanted:
                break
        except (ValueError, TypeError):
            continue
    return result
