"""Shared sample-based receiver health, additive SQLite history and reboot guard."""
import contextlib
from datetime import datetime, timezone
import fcntl
import json
import logging
import os
from pathlib import Path
import signal
import sqlite3
import subprocess
import tempfile
import time

ROOT = Path(__file__).resolve().parent
DB = ROOT / 'data/watchkeeper.db'
CONFIG = ROOT / 'rf-health-config.json'
LOG = logging.getLogger('rf_health')

class ClosingConnection(sqlite3.Connection):
    def __exit__(self, *args):
        try:
            return super().__exit__(*args)
        finally:
            self.close()

def stamp():
    return datetime.now(timezone.utc).isoformat()

def timestamp(value):
    return datetime.fromisoformat(value.replace('Z', '+00:00')).timestamp()

def config():
    return json.loads(CONFIG.read_text())

def connect(path=None):
    db = sqlite3.connect(str(path or DB), timeout=10, factory=ClosingConnection)
    db.row_factory = sqlite3.Row
    db.executescript('''
    CREATE TABLE IF NOT EXISTS rf_health_jobs (
      id INTEGER PRIMARY KEY, receiver_serial TEXT NOT NULL, job_type TEXT NOT NULL,
      start_time TEXT NOT NULL, completion_time TEXT, deadline REAL, pid INTEGER,
      capture_ok INTEGER, evidence_value REAL DEFAULT 0, evidence_kind TEXT,
      exit_code INTEGER, failure_reason TEXT, application_status TEXT, boot_id TEXT);
    CREATE INDEX IF NOT EXISTS rf_health_jobs_receiver_time
      ON rf_health_jobs(receiver_serial, completion_time);
    CREATE TABLE IF NOT EXISTS rf_health_events (
      id INTEGER PRIMARY KEY, timestamp TEXT NOT NULL, receiver_serial TEXT NOT NULL,
      action TEXT NOT NULL, result TEXT NOT NULL, detail TEXT, boot_id TEXT);
    CREATE TABLE IF NOT EXISTS rf_health_state (
      receiver_serial TEXT PRIMARY KEY, checked_at TEXT, status TEXT, detail TEXT);
    CREATE TABLE IF NOT EXISTS rf_health_reboot_guard (
      singleton INTEGER PRIMARY KEY CHECK(singleton=1), requested_at REAL NOT NULL,
      boot_id TEXT NOT NULL, reason TEXT NOT NULL);
    ''')
    if 'boot_id' not in {row[1] for row in db.execute('PRAGMA table_info(rf_health_jobs)')}:
        db.execute('ALTER TABLE rf_health_jobs ADD COLUMN boot_id TEXT')
        db.commit()
    return db

def begin(job, seconds, serial='V4MAIN01', path=None):
    with connect(path) as db:
        return db.execute('INSERT INTO rf_health_jobs(receiver_serial,job_type,start_time,deadline,pid,boot_id) VALUES(?,?,?,?,?,?)',
                          (serial, job, stamp(), time.time()+seconds+30, os.getpid(),boot_id())).lastrowid

def finish(identity, ok, evidence=0, kind='sample_bytes', code=None, reason=None, application=None, path=None):
    # An application's result must never manufacture a receiver heartbeat.
    ok = bool(ok and evidence > 0)
    with connect(path) as db:
        changed = db.execute('UPDATE rf_health_jobs SET completion_time=?,capture_ok=?,evidence_value=?,evidence_kind=?,exit_code=?,failure_reason=?,application_status=? WHERE id=? AND completion_time IS NULL',
                   (stamp(), int(ok), evidence, kind, code, None if ok else reason or 'No sample evidence / abnormal completion',
                    json.dumps(application) if application is not None else None, identity)).rowcount
    if changed and not ok:
        LOG.warning('Receiver capture failed: job_id=%s reason=%s', identity, reason)

def cancel(identity, reason='Intentional early job cancellation'):
    with connect() as db:
        db.execute('UPDATE rf_health_jobs SET completion_time=?,failure_reason=? WHERE id=? AND completion_time IS NULL',
                   (stamp(),reason,identity))

def event(action, result, detail='', serial='V4MAIN01', path=None):
    with connect(path) as db:
        db.execute('INSERT INTO rf_health_events(timestamp,receiver_serial,action,result,detail,boot_id) VALUES(?,?,?,?,?,?)',
                   (stamp(), serial, action, result, detail, boot_id()))
    LOG.warning('%s: %s %s', action, result, detail)

def boot_id():
    return Path('/proc/sys/kernel/random/boot_id').read_text().strip()

def set_state(status, detail, serial='V4MAIN01', path=None):
    with connect(path) as db:
        db.execute('INSERT OR REPLACE INTO rf_health_state VALUES(?,?,?,?)', (serial, stamp(), status, detail))

def snapshot(path=None):
    rows = []
    with connect(path) as db:
        for serial, receiver in config()['receivers'].items():
            if not receiver['enabled']:
                rows.append(dict(serial=serial, status='DISABLED', detail='Intentionally disconnected'))
                continue
            last = db.execute('SELECT * FROM rf_health_jobs WHERE receiver_serial=? AND capture_ok=1 ORDER BY completion_time DESC,id DESC LIMIT 1', (serial,)).fetchone()
            state = db.execute('SELECT * FROM rf_health_state WHERE receiver_serial=?', (serial,)).fetchone()
            failures = db.execute('SELECT count(*) FROM rf_health_jobs WHERE receiver_serial=? AND capture_ok=0 AND completion_time>?',
                                  (serial, datetime.fromtimestamp(time.time()-86400, timezone.utc).isoformat())).fetchone()[0]
            recovery = db.execute("SELECT * FROM rf_health_events WHERE receiver_serial=? AND action NOT IN ('probe','heartbeat_stale','prepass') ORDER BY id DESC LIMIT 1", (serial,)).fetchone()
            app = db.execute("SELECT * FROM rf_health_jobs WHERE receiver_serial=? AND application_status IS NOT NULL AND application_status != 'null' ORDER BY id DESC LIMIT 1", (serial,)).fetchone()
            age = time.time()-timestamp(last['completion_time']) if last else None
            status = 'GREEN' if age is not None and age < config()['green_seconds'] else 'YELLOW' if age is not None and age <= config()['red_seconds'] else 'RED'
            if state and state['status'] in ('BUSY', 'UNKNOWN', 'RED') and timestamp(state['checked_at']) > (timestamp(last['completion_time']) if last else 0):
                status = state['status']
            detail=state['detail'] if state else 'Awaiting monitor'
            if last and (not state or timestamp(last['completion_time'])>timestamp(state['checked_at'])):
                detail='Successful receiver sample acquisition'
            rows.append(dict(serial=serial, status=status, detail=detail,
                             last_capture=dict(last) if last else None, heartbeat_age_seconds=age,
                             recent_failures=failures, last_recovery=dict(recovery) if recovery else None,
                             last_application_result=dict(app) if app else None,
                             checked_at=state['checked_at'] if state else None))
    return rows

@contextlib.contextmanager
def control_lock():
    with (ROOT/'data/rf-health-control.lock').open('a') as handle:
        fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        yield

def satellite_guard():
    """Fail closed on uncertain ownership; includes manually started recorders."""
    try:
        result = subprocess.run(['systemctl','list-units','--type=service',
            '--state=active,activating,deactivating','--plain','--no-legend'], capture_output=True,text=True,check=True,timeout=5)
        for line in result.stdout.splitlines():
            unit = line.split()[0]
            if unit == 'meteor-auto-capture.service' or unit.startswith(('meteor-', 'satellite-')) and unit != 'satellite-v4-preflight.service':
                return unit
        for proc in Path('/proc').glob('[0-9]*/cmdline'):
            try:
                argv = proc.read_bytes().split(b'\0')
                if any(Path(a.decode(errors='replace')).name == 'satellite_capture.py' for a in argv[:4]):
                    return 'satellite recorder PID '+proc.parent.name
            except FileNotFoundError:
                continue
        for p in (ROOT/'data/meteor-auto/passes').glob('*/pass.json'):
            r = json.loads(p.read_text())
            if r.get('state') == 'capturing':
                return 'persisted capture reservation '+str(p)
        for p in (ROOT/'data/meteor-recovery').glob('*.json'):
            r = json.loads(p.read_text())
            if r.get('state') in ('reboot_requested','resuming'):
                return 'persistent reboot reservation '+str(p)
    except (OSError, ValueError, subprocess.SubprocessError) as exc:
        return 'Cannot verify satellite ownership: '+str(exc)
    return None

def stop_process(proc):
    if proc.poll() is None:
        proc.terminate()
    try:
        proc.wait(timeout=3)
        return False
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait(timeout=3)
        return True

def probe(serial='V4MAIN01', job='direct-probe'):
    """Caller must own receiver lock and verify no satellite reservation."""
    identity = begin(job, 8, serial)
    code, count, reason = None, 0, None
    event('probe', 'started', job, serial)
    try:
        with tempfile.TemporaryDirectory(prefix='rf-health-') as folder:
            path = Path(folder)/'probe.cu8'
            with subprocess.Popen(['/usr/local/bin/rtl_sdr','-d',serial,'-f','137900000',
                    '-s','256000','-g','49.6','-n','256000',str(path)], stdout=subprocess.DEVNULL,
                    stderr=subprocess.PIPE) as proc:
                try:
                    _, err = proc.communicate(timeout=8)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    _, err = proc.communicate(timeout=3)
                    reason = 'Direct sample probe exceeded hard timeout'
                code = proc.returncode
            count = path.stat().st_size if path.exists() else 0
            ok = code == 0 and reason is None and count == 512000 and len(set(path.read_bytes()[:65536])) > 1
            if not ok and not reason:
                reason = 'Invalid IQ sample acquisition: '+err.decode(errors='replace')[-1200:]
    except (OSError, subprocess.SubprocessError) as exc:
        ok, reason = False, str(exc)
    finish(identity, ok, count, code=code, reason=reason)
    event('probe', 'success' if ok else 'failed', str(count)+' bytes; '+(reason or 'valid IQ'), serial)
    return ok

def reboot_allowed(reason, path=None, now=None):
    """Atomic durable guard shared with legacy and managed METEOR recovery."""
    now = time.time() if now is None else now
    with connect(path) as db:
        db.execute('BEGIN IMMEDIATE')
        previous = db.execute('SELECT requested_at FROM rf_health_reboot_guard WHERE singleton=1').fetchone()
        if previous and now-previous[0] < config()['reboot_interval_seconds']:
            return False
        db.execute('INSERT OR REPLACE INTO rf_health_reboot_guard VALUES(1,?,?,?)',(now,boot_id(),reason))
    return True
