#!/usr/bin/env python3
"""Independent read-only ADS-B observer. Never controls RF services or USB."""
import datetime as dt
from contextlib import contextmanager
import json
import os
from pathlib import Path
import re
import sqlite3
import subprocess
import time

ROOT = Path(__file__).resolve().parent
PRIVATE = ROOT / 'private'

def read(path):
    try:
        if path.stat().st_size > 4*1024*1024:
            raise ValueError('state file too large')
        return json.loads(path.read_text())
    except FileNotFoundError:
        return {}

def atomic(path, data):
    tmp = path.with_suffix('.monitor-tmp')
    tmp.write_text(json.dumps(data, allow_nan=False, indent=2)+'\n')
    tmp.replace(path)

def stamp(value):
    return dt.datetime.fromisoformat(value.replace('Z', '+00:00')).timestamp()

def service(unit):
    result = subprocess.run(['systemctl', 'show', unit, '-p', 'ActiveState', '-p', 'SubState',
                             '-p', 'UnitFileState', '-p', 'MainPID'],
                            capture_output=True, text=True, timeout=3, check=True)
    return dict(line.split('=', 1) for line in result.stdout.splitlines() if '=' in line)

@contextmanager
def connect(path):
    db = sqlite3.connect(path.resolve().as_uri()+'?mode=ro', uri=True, timeout=.1)
    db.execute('PRAGMA query_only=ON')
    deadline = time.monotonic()+2
    db.set_progress_handler(lambda: int(time.monotonic()>deadline), 10000)
    try:
        yield db
    finally:
        db.close()

def collect(private, lease, state):
    """Consume bounded snapshot batches; cursor and aggregates survive observer restart."""
    sid = lease['session']
    state.setdefault('cursor', 0)
    state.setdefault('aircraft', {})
    state.setdefault('sample_segments', [])
    if not (private/'aircraft.sqlite').exists():
        state.update(caught_up=True, frames=0, first_frame_utc=None,
                     last_frame_utc=None, unique_aircraft=0)
        return state
    with connect(private/'aircraft.sqlite') as db:
        rows = db.execute('SELECT rowid,utc,kind,json FROM snapshots WHERE rowid>? AND session=? ORDER BY rowid LIMIT 500',
                          (state['cursor'], sid)).fetchall()
        for rowid, utc, kind, raw in rows:
            data = json.loads(raw)
            if kind == 'stats':
                local = data.get('total', {}).get('local', {})
                samples = local.get('samples_processed', 0)
                source_start = data.get('total', {}).get('start')
                segments = state['sample_segments']
                if (not segments or samples < segments[-1]['samples'] or
                    (source_start is not None and segments[-1].get('source_start') is not None and
                     source_start != segments[-1]['source_start'])):
                    segments.append(dict(first=utc, last=utc, samples=0, drops=0))
                segments[-1].update(last=utc, samples=samples, drops=local.get('samples_dropped', 0),
                                    source_start=source_start)
            elif kind == 'aircraft':
                now = data.get('now', stamp(utc))
                for ac in data.get('aircraft', []):
                    if ac.get('seen', 999) > 2:
                        continue
                    icao = ac.get('hex', '')
                    if not re.fullmatch(r'~?[0-9a-fA-F]{6}', icao):
                        continue
                    seen = now-ac.get('seen', 0)
                    old = state['aircraft'].get(icao, {})
                    item = dict(icao=icao, callsign=str(ac.get('flight', '')).strip()[:16],
                                altitude=ac.get('alt_baro', ac.get('altitude')),
                                speed=ac.get('gs', ac.get('speed')), last_seen=seen,
                                first_seen=old.get('first_seen', seen),
                                position_decoded=old.get('position_decoded', False) or
                                (isinstance(ac.get('lat'), (int, float)) and isinstance(ac.get('lon'), (int, float))))
                    state['aircraft'][icao] = item
            state['cursor'] = rowid
        state['caught_up'] = len(rows)<500
        frames, first, last = db.execute('SELECT count(*),min(utc),max(utc) FROM frames WHERE session=?', (sid,)).fetchone()
        direct = [r[0] for r in db.execute('SELECT DISTINCT icao FROM frames WHERE session=? AND icao IS NOT NULL LIMIT 20000', (sid,))]
        state.update(frames=frames, first_frame_utc=first, last_frame_utc=last,
                     unique_aircraft=len(set(direct)|set(state['aircraft'])))
    return state

def observe(private=PRIVATE, services=service):
    now = time.time()
    lease = read(private/'lease.json')
    restored = {}
    if not lease:
        # Session identifiers are UTC-sortable; ignore unrelated filenames.
        files = sorted(p for p in private.glob('*-restored.json') if re.fullmatch(r'\d{8}T\d{6}Z-restored.json', p.name))
        if not files:
            return dict(status='No ADS-B session', observed_at=now)
        restored = read(files[-1])
        lease = restored
    sid = lease['session']
    if not re.fullmatch(r'\d{8}T\d{6}Z', sid):
        raise ValueError('invalid session identifier')
    statepath = private/(sid+'-monitor-state.json')
    state = collect(private, lease, read(statepath))
    atomic(statepath, state)
    health = read(private/sid/'health.json')
    age = now-stamp(health['utc']) if health.get('utc') else None
    receiver = services('rf-watchkeeper-adsb.service')
    watchdog = services('rf-watchkeeper-adsb-watchdog.timer')
    scheduler = services('rf-watchkeeper-scheduler.service')
    after = {unit: services(unit) for unit in lease.get('before', {})}
    mismatches = [unit for unit, expected in lease.get('before', {}).items()
                  if after[unit].get('ActiveState') != expected.get('ActiveState') or
                  after[unit].get('UnitFileState') != expected.get('UnitFileState')]
    complete = lease.get('phase') == 'restored'
    errors = []
    if complete:
        status = 'Completed' if not mismatches else 'Completed — restoration alert'
    elif lease.get('abort') or receiver.get('ActiveState') != 'active':
        status = 'Decoder/supervisor failure or stopped — restoration pending'
    elif age is None or age > 35:
        status = 'Stale receiver health'
    elif now >= lease['expiry']:
        status = 'Expired — restoration pending'
    elif health.get('decoder_stats', {}).get('samples_processed', 0) <= 0:
        status = 'Waiting for decoder samples'
    elif state['frames'] == 0:
        status = 'Healthy receiver — no valid messages yet'
    else:
        status = 'Receiving valid aircraft messages'
    previous = read(private/'live-status.json')
    stats = health.get('decoder_stats', {})
    progress = None
    if previous.get('session') == sid and previous.get('attempt') == health.get('attempt'):
        progress = stats.get('samples_processed', 0)>previous.get('samples_processed', 0)
        if not complete and age is not None and age <= 35 and progress is False:
            status = 'Decoder samples stalled'
    if not complete and watchdog.get('ActiveState') != 'active':
        errors.append('Expiry watchdog is not active; operator action required')
    if complete and mismatches:
        errors.append('Restoration state differs from saved inventory; inspect private health report')
    aircraft = sorted(state['aircraft'].values(), key=lambda x:x['last_seen'], reverse=True)
    public = dict(session=sid, observed_at=now, status=status, alerts=errors,
                  start=lease['start'], expiry=lease['expiry'], remaining_seconds=max(0, lease['expiry']-now),
                  health_updated=health.get('utc'), health_age_seconds=age,
                  receiver=receiver, watchdog=watchdog, scheduler=scheduler,
                  rf_state=('Restored and verified' if not mismatches else 'Restoration alert') if complete else
                  ('Conflicting RF activity paused' if scheduler.get('ActiveState')=='inactive' else 'RF pause not confirmed — alert'),
                  attempt=health.get('attempt'), attempts=lease.get('attempts'),
                  samples_processed=stats.get('samples_processed'), samples_dropped=stats.get('samples_dropped'),
                  sample_progress=progress, valid_frames=state['frames'], unique_aircraft=state['unique_aircraft'],
                  first_valid_message=state['first_frame_utc'], last_valid_message=state['last_frame_utc'],
                  recent_aircraft=[{k:v for k,v in a.items() if k not in ('first_seen', 'position_decoded')} for a in aircraft[:20]],
                  aircraft_with_decoded_positions=sum(a['position_decoded'] for a in aircraft),
                  aggregation_caught_up=state['caught_up'], completed=complete,
                  stop_reason=lease.get('abort') or ('Scheduled expiry' if complete and now>=lease['expiry'] else 'Early restoration' if complete else None))
    if complete and state['caught_up']:
        reportpath = private/(sid+'-health-summary.json')
        report = read(reportpath)
        if not report:
            try:
                with connect(private/'aircraft.sqlite') as db:
                    integrity = db.execute('PRAGMA quick_check').fetchone()[0]
            except sqlite3.Error as error:
                integrity = 'Unavailable: '+type(error).__name__
            segments = state['sample_segments']
            report = dict(public, database_integrity=integrity, restoration_mismatches=mismatches,
                          saved_restoration=restored, sample_segments=segments,
                          samples_all_observed_attempts=sum(s['samples'] for s in segments),
                          drops_all_observed_attempts=sum(s['drops'] for s in segments),
                          observed_receiver_uptime_seconds=sum(s['samples']/2400000 for s in segments),
                          uptime_basis='Decoder sample totals / 2.4 MS/s; excludes unobserved pre-snapshot samples',
                          final_health=health, notification_transport='None configured; local report and dashboard')
            atomic(reportpath, report)
        public['report'] = dict(ready=True, database_integrity=report['database_integrity'],
                              receiver_uptime_seconds=report['observed_receiver_uptime_seconds'],
                              samples=report['samples_all_observed_attempts'], drops=report['drops_all_observed_attempts'])
        if report['database_integrity'] != 'ok':
            public['alerts'].append('Database integrity check failed; inspect private health summary')
    elif now >= lease['expiry']+90 or lease.get('abort') or lease.get('phase') == 'restoring':
        # Persist an actionable report even when restoration never succeeds.
        try:
            with connect(private/'aircraft.sqlite') as db:
                integrity = db.execute('PRAGMA quick_check').fetchone()[0]
        except sqlite3.Error as error:
            integrity = 'Unavailable: '+type(error).__name__
        atomic(private/(sid+'-health-alert.json'), dict(public, restoration_mismatches=mismatches,
              database_integrity=integrity, final_health=health, sample_segments=state['sample_segments']))
    atomic(private/'live-status.json', public)
    return public

def main():
    os.umask(0o077)
    while True:
        try:
            observe()
        except Exception as error:
            # Do not keep presenting a cached success if observer processing fails.
            atomic(PRIVATE/'live-status.json', dict(status='Monitor error', observed_at=time.time(),
                                                   alerts=['Read-only monitor failed: '+type(error).__name__]))
        time.sleep(12)

if __name__ == '__main__':
    main()
