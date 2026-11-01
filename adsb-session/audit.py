"""Read-only, privacy-safe evidence: no aircraft coordinates or observer config."""
import hashlib
import json
from pathlib import Path
import sqlite3
import subprocess
import session as s

lease=json.loads(s.LEASE.read_text())
directory=s.STATE/lease['session']
with sqlite3.connect(s.STATE/'aircraft.sqlite') as db:
    counts=dict(frames=db.execute('SELECT count(*) FROM frames WHERE session=?',(lease['session'],)).fetchone()[0],
                aircraft_all_sessions=db.execute('SELECT count(*) FROM aircraft').fetchone()[0],
                snapshots=db.execute('SELECT count(*) FROM snapshots WHERE session=?',(lease['session'],)).fetchone()[0],
                integrity=db.execute('PRAGMA quick_check').fetchone()[0])
unrelated=['rf-watchkeeper-dashboard.service','rf-watchkeeper-atis-process.service',
           'rf-watchkeeper-atis-shadow.service','rf-watchkeeper-interpreter.service',
           'rf-watchkeeper-meteor-plan.timer','rf-watchkeeper-meteor-process.timer',
           'rf-watchkeeper-audio-retention.timer','rf-watchkeeper-meteor-cleanup.timer']
restored=[]
for path in sorted(s.STATE.glob('*-restored.json')):
    row=json.loads(path.read_text())
    restored.append(dict(session=row['session'],restored_at=row['restored_at'],attempts=row['attempts'],
                         states=row['after'],before=row['before']))
test=subprocess.run(['/usr/bin/python3','-m','unittest','-v','test_session'],text=True,capture_output=True,timeout=30)
result=dict(observed_utc=s.utc(),session=lease['session'],start=lease['start'],expiry=lease['expiry'],
            phase=lease['phase'],attempts=lease['attempts'],counts=counts,
            health=json.loads((directory/'health.json').read_text()),
            conflicting_units={u:dict(before=old,now=s.props(u),guard=(s.UNIT/(u+'.d')/'91-adsb-lease.conf').read_text()) for u,old in lease['before'].items()},
            unrelated_units={u:s.props(u) for u in unrelated},
            expiry_timer=s.props(s.NAME+'-watchdog.timer'),
            decoder_service=s.props(s.NAME+'.service'),
            decoder_restarts=s.ctl('show',s.NAME+'.service','-p','NRestarts','--value'),
            clock=s.run('timedatectl','show','-p','NTPSynchronized','-p','NTP'),
            sources=json.loads((directory/'provenance.json').read_text()),
            bindings=s.run('docker','port',s.NAME),
            usb_node=s.usb_owners()[0],owners=s.usb_owners()[1],
            hashes={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in s.ROOT.iterdir() if p.suffix=='.py' or p.name=='Dockerfile'},
            trials=restored,
            tests=dict(exit_code=test.returncode,stdout=test.stdout,stderr=test.stderr))
print(json.dumps(result,indent=2))
