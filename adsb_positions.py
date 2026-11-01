"""Bounded read-only aircraft projection; no receiver metadata or RF controls."""
import json
import math
import re
import sqlite3
import subprocess
import sys
from pathlib import Path
import threading
import time

_lock = threading.Lock()
_cache = (0, None)

def finite(v, lo, hi):
    return isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v) and lo <= v <= hi

def collect_positions(private):
    global _cache
    with _lock:
        now = time.time()
        if now - _cache[0] < 10:
            return _cache[1]
        status = json.loads((private/'live-status.json').read_text())
        sid = status.get('session', '')
        if not re.fullmatch(r'\d{8}T\d{6}Z', sid):
            raise ValueError('No session')
        result = {}
        labels = {a.get('icao'): a.get('callsign','') for a in status.get('recent_aircraft',[])[:20] if isinstance(a,dict)}
        db = sqlite3.connect((private/'aircraft.sqlite').resolve().as_uri()+'?mode=ro', uri=True, timeout=.1)
        deadline = time.monotonic()+.5
        db.set_progress_handler(lambda: int(time.monotonic()>deadline), 1000)
        try:
            db.execute('PRAGMA query_only=ON')
            # Latest 5000 stored rows only, at most 2 MB of snapshot JSON.
            rows = db.execute('SELECT utc,kind,json FROM snapshots WHERE rowid>(SELECT coalesce(max(rowid),0)-5000 FROM snapshots) AND session=? ORDER BY rowid DESC LIMIT 5000', (sid,))
            size = 0
            for utc, kind, raw in rows:
                size += len(raw)
                if size > 2000000:
                    break
                if kind != 'aircraft':
                    continue
                data = json.loads(raw)
                report = data.get('now')
                if not finite(report, 0, now+5):
                    continue
                for ac in data.get('aircraft', [])[:500]:
                    address = ac.get('hex', '')
                    if not isinstance(address, str) or not re.fullmatch(r'~?[0-9a-fA-F]{6}', address) or address in result:
                        continue
                    if not finite(ac.get('lat'), -90, 90) or not finite(ac.get('lon'), -180, 180):
                        continue
                    age = ac.get('seen_pos')
                    # Unknown position age is never presented as a fresh position.
                    known = finite(age, 0, 86400)
                    positioned = report-age if known else None
                    fresh = bool(known and 0 <= now-positioned <= 60 and not status.get('completed') and now-status.get('observed_at',0)<=40 and status.get('receiver',{}).get('ActiveState')=='active' and finite(status.get('health_age_seconds'),0,35))
                    item = dict(icao=address, callsign=re.sub(r'[^A-Za-z0-9 _-]', '',str(ac.get('flight') or labels.get(address,'')))[:16].strip(),lat=ac['lat'],lon=ac['lon'],position_time=positioned,snapshot_time=report,fresh=fresh,provenance='dump1090 decoded position; no receiver reference supplied')
                    for key, value in [('altitude',ac.get('alt_baro',ac.get('altitude'))),('speed',ac.get('gs',ac.get('speed'))),('heading',ac.get('track'))]:
                        item[key] = value if finite(value,-2000 if key=='altitude' else 0,100000 if key=='altitude' else 2000 if key=='speed' else 360) else 'ground' if key=='altitude' and value=='ground' else None
                    seen=ac.get('seen')
                    item['last_seen']=report-seen if finite(seen,0,86400) else None
                    result[address]=item
                    if len(result)>=100:
                        break
                if len(result)>=100:
                    break
        finally:
            db.close()
        payload=dict(observed_at=now,session=sid,aircraft=list(result.values()),scan_limit=5000,position_fresh_seconds=60,history='Last decoded positions within the latest 5000 snapshots only; incomplete history')
        _cache=(now,payload)
        return payload


def positions(private):
    """Keep SQLite/JSON work outside the busy dashboard interpreter."""
    global _cache
    with _lock:
        if time.time() - _cache[0] < 10:
            return _cache[1]
        try:
            raw = subprocess.run([sys.executable, str(Path(__file__).resolve()), str(private)],
                                 capture_output=True, timeout=2, check=True).stdout
            if len(raw) > 65536:
                raise ValueError('Position response too large')
            payload = json.loads(raw)
        except (subprocess.SubprocessError, ValueError) as error:
            raise ValueError('Bounded position worker unavailable') from error
        _cache = (time.time(), payload)
        return payload


if __name__ == '__main__':
    print(json.dumps(collect_positions(Path(sys.argv[1])), allow_nan=False))
