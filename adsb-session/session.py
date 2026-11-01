#!/usr/bin/env python3
"""Temporary private ADS-B lease; independent systemd watchdog restores RF state."""
import argparse
import datetime as dt
import fcntl
import hashlib
import json
import os
from pathlib import Path
import shutil
import socket
import sqlite3
import subprocess as sp
import time

ROOT = Path(__file__).resolve().parent
STATE = ROOT / 'private'
LEASE = STATE / 'lease.json'
UNIT = Path('/etc/systemd/system')
NAME = 'rf-watchkeeper-adsb'
IMAGE = 'rf-watchkeeper-adsb:20261101'
CAP = 1024**3

def utc():
    return dt.datetime.now(dt.timezone.utc).isoformat()

def run(*args, check=True):
    return sp.run(args, check=check, text=True, capture_output=True, timeout=90).stdout.strip()

def ctl(*args, **kw):
    return run('systemctl', *args, **kw)

def atomic(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix('.tmp')
    tmp.write_text(json.dumps(value, indent=2)+'\n')
    tmp.replace(path)

def event(kind, **kw):
    with (STATE/'changes.ndjson').open('a') as out:
        out.write(json.dumps(dict(utc=utc(), event=kind, **kw))+'\n')

def props(unit):
    return dict(x.split('=', 1) for x in ctl('show', unit, '-p', 'ActiveState', '-p', 'SubState', '-p', 'UnitFileState').splitlines())

def conflicts():
    lines = ctl('list-unit-files', '--no-legend', '--no-pager').splitlines()
    lines += ctl('list-units', '--all', '--plain', '--no-legend', '--no-pager').splitlines()
    names = {x.split()[0] for x in lines if x.split()}
    direct = {'rf-watchkeeper-scheduler.service', 'rf-watchkeeper.service',
              'rf-watchkeeper-ais.service', 'rf-watchkeeper-sensors.service',
              'rf-watchkeeper-health.service', 'rf-watchkeeper-health.timer',
              'rf-watchkeeper-meteor-dispatch.service', 'rf-watchkeeper-meteor-dispatch.timer',
              'rf-watchkeeper-meteor-recover.service'}
    return sorted(u for u in names if u in direct or u.startswith(('meteor-', 'satellite-')))

def usb_owners():
    owners = []
    for dev in Path('/sys/bus/usb/devices').glob('*'):
        try:
            if (dev/'serial').read_text().strip() != 'V4MAIN01':
                continue
            bus, num = int((dev/'busnum').read_text()), int((dev/'devnum').read_text())
            node = '/dev/bus/usb/%03d/%03d' % (bus, num)
            for proc in Path('/proc').glob('[0-9]*'):
                try:
                    if any(os.readlink(fd) == node for fd in (proc/'fd').iterdir()):
                        owners.append(dict(pid=int(proc.name), cmd=(proc/'cmdline').read_bytes().replace(b'\0', b' ').decode(errors='replace')))
                except (OSError, PermissionError):
                    pass
            return node, owners
        except OSError:
            pass
    raise RuntimeError('V4MAIN01 not found in USB sysfs')

def install():
    STATE.mkdir(mode=0o700, exist_ok=True)
    script = str(Path(__file__).resolve())
    units = {
        NAME+'.service': '[Unit]\nDescription=Bounded private ADS-B session\nAfter=docker.service network.target\nRequires=docker.service\n[Service]\nType=simple\nExecStart=/usr/bin/python3 '+script+' capture\nExecStopPost=-/usr/bin/docker rm -f '+NAME+'\nRestart=on-failure\nRestartSec=10\nTimeoutStopSec=20\nKillMode=control-group\nUMask=0077\n[Install]\nWantedBy=multi-user.target\n',
        NAME+'-watchdog.service': '[Unit]\nDescription=Independent ADS-B expiry and restoration\nAfter=docker.service\n[Service]\nType=oneshot\nExecStart=/usr/bin/python3 '+script+' tick\nTimeoutStartSec=180\nUMask=0077\n',
        NAME+'-watchdog.timer': '[Unit]\nDescription=Persistent ADS-B deadline enforcement\n[Timer]\nOnCalendar=*-*-* *:*:00,30 UTC\nOnBootSec=10s\nPersistent=true\nAccuracySec=1s\n[Install]\nWantedBy=timers.target\n'}
    for name, value in units.items():
        (UNIT/name).write_text(value)
    run('systemd-analyze', 'verify', *[str(UNIT/u) for u in units])
    ctl('daemon-reload')
    ctl('enable', '--now', NAME+'-watchdog.timer')

def start(seconds):
    if LEASE.exists():
        raise RuntimeError('Existing lease; restore it first')
    if (ROOT.parent/'data/acquisition-suspended.json').exists():
        raise RuntimeError('Existing broad acquisition suspension; preserve operator state')
    node, owners = usb_owners()
    units = conflicts()
    saved = {u: props(u) for u in units}
    if any(s['ActiveState'] in ('activating','deactivating','failed') for s in saved.values()):
        raise RuntimeError('Conflicting unit transitional/failed; retry after inspection')
    # Refuse an owner outside a known systemd RF capture cgroup.
    for owner in owners:
        cg = (Path('/proc')/str(owner['pid'])/'cgroup').read_text()
        if not any('/'+u in cg for u in units if u.endswith('.service')):
            raise RuntimeError('Unknown SDR owner: '+repr(owner))
    now = time.time()
    lease = dict(session=dt.datetime.now(dt.timezone.utc).strftime('%Y%m%dT%H%M%SZ'),
                 start=now, expiry=now+seconds, before=saved, usb_node=node,
                 owners_before=owners, attempts=0, phase='preparing')
    atomic(LEASE, lease)
    event('lease_saved', lease=lease)
    # The watchdog is installed before any RF state is changed. Guards persist over reboot.
    for u in units:
        drop = UNIT/(u+'.d')/'91-adsb-lease.conf'
        if drop.exists():
            raise RuntimeError('Unexpected pre-existing lease guard '+str(drop))
        drop.parent.mkdir(exist_ok=True)
        drop.write_text('[Unit]\nConditionPathExists=!'+str(LEASE)+'\n')
    ctl('daemon-reload')
    for suffix in ('.timer', '.service'):
        selected = [u for u in units if u.endswith(suffix)]
        if selected:
            ctl('stop', *selected)
    node, owners = usb_owners()
    if owners:
        raise RuntimeError('SDR still owned; watchdog will restore: '+repr(owners))
    lease['phase'] = 'capturing'
    atomic(LEASE, lease)
    ctl('enable', NAME+'.service')
    ctl('start', NAME+'.service')
    event('capture_started', session=lease['session'], expiry=lease['expiry'])
    print(json.dumps(lease, indent=2))

def restore():
    if not LEASE.exists():
        return
    lease = json.loads(LEASE.read_text())
    ctl('stop', NAME+'.service')
    run('docker', 'rm', '-f', NAME, check=False)
    # Do not release the RF guard until Docker has positively relinquished this container.
    if run('docker','ps','-aq','--filter','name=^/'+NAME+'$'):
        raise RuntimeError('Decoder container remains; guards retained')
    if lease['phase'] != 'restoring' and usb_owners()[1]:
        raise RuntimeError('USB remains owned; guards retained for inspection')
    ctl('disable', NAME+'.service')
    lease['phase'] = 'restoring'
    atomic(LEASE, lease)
    # Removing our own guards restores original unit definitions/enablement.
    for u in lease['before']:
        (UNIT/(u+'.d')/'91-adsb-lease.conf').unlink(missing_ok=True)
    ctl('daemon-reload')
    # Original inactive one-shots and disabled receivers are never started.
    for suffix in ('.service', '.timer'):
        selected = [u for u,s in lease['before'].items() if u.endswith(suffix) and s['ActiveState']=='active']
        if selected:
            ctl('start', *selected)
    after = {u: props(u) for u in lease['before']}
    mismatches = {u: dict(before=s, after=after[u]) for u,s in lease['before'].items()
                  if s['UnitFileState'] != after[u]['UnitFileState'] or
                  (s['ActiveState']=='active') != (after[u]['ActiveState']=='active')}
    if mismatches:
        event('restore_mismatch', units=mismatches)
        raise RuntimeError('State restoration mismatch; retained lease for retry')
    lease.update(phase='restored', restored_at=utc(), after=after)
    atomic(STATE/(lease['session']+'-restored.json'), lease)
    LEASE.unlink()
    event('restored', session=lease['session'], after=after)
    summarize(lease)
    print(json.dumps(lease, indent=2))

def summarize(lease):
    summary = dict(session=lease['session'], start=lease['start'], expiry=lease['expiry'],
                   observed_at=utc(), phase=lease['phase'], abort=lease.get('abort'),
                   attempts=lease['attempts'] if 'attempts' in lease else 0)
    path = STATE/'aircraft.sqlite'
    if path.exists():
        with sqlite3.connect(path) as db:
            summary['frames'], summary['first_frame_utc'], summary['last_frame_utc'] = db.execute(
                'SELECT count(*),min(utc),max(utc) FROM frames WHERE session=?',(lease['session'],)).fetchone()
            summary['aircraft_all_sessions'] = db.execute('SELECT count(*) FROM aircraft').fetchone()[0]
            summary['decoded_snapshots'] = db.execute('SELECT count(*) FROM snapshots WHERE session=? AND kind=?',(lease['session'],'aircraft')).fetchone()[0]
            summary['database_integrity'] = db.execute('PRAGMA quick_check').fetchone()[0]
    atomic(STATE/(lease['session']+'-summary.json'), summary)

def tick():
    if not LEASE.exists():
        return
    lease = json.loads(LEASE.read_text())
    if time.time() >= lease['expiry'] or lease.get('abort') or lease['phase'] in ('restoring','preparing'):
        restore()

def frames(buffer):
    """Extract Beast escaped binary frames, retaining 12 MHz ticks and RSSI byte."""
    sizes = {0x31:9, 0x32:14, 0x33:21}
    result = []
    pos = 0
    while pos+2 <= len(buffer):
        if buffer[pos] != 0x1a or buffer[pos+1] not in sizes:
            pos += 1
            continue
        kind = buffer[pos+1]
        i, data = pos+2, bytearray()
        while len(data) < sizes[kind] and i < len(buffer):
            value = buffer[i]
            if value == 0x1a:
                if i+1 >= len(buffer):
                    break
                if buffer[i+1] != 0x1a:
                    break
                i += 1
            data.append(value)
            i += 1
        if len(data) < sizes[kind]:
            if i >= len(buffer) or (i+1 >= len(buffer) and buffer[i]==0x1a):
                break
            pos = i
            continue
        result.append((kind, bytes(data)))
        pos = i
    return result, buffer[pos:]

def capture():
    if not LEASE.exists():
        return
    lease = json.loads(LEASE.read_text())
    if time.time() < lease['start']:
        lease['abort'] = 'clock precedes session start; refusing restart'
        atomic(LEASE, lease)
        return
    if time.time() >= lease['expiry'] or lease.get('abort') or lease['phase']!='capturing':
        return
    lease['attempts'] += 1
    if lease['attempts'] > 6:
        lease['abort'] = 'six decoder attempts exhausted'
        atomic(LEASE, lease)
        return
    atomic(LEASE, lease)
    token = hashlib.sha256(b'V4MAIN01').hexdigest()[:16]
    with open('/tmp/dragonwing-sdr-'+token+'.lock','a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        node, owners = usb_owners()
        if owners:
            raise RuntimeError('Unexpected receiver owner; no force termination')
        lease['usb_node'] = node
        atomic(LEASE, lease)
        collect(lease)

def collect(lease):
    directory = STATE/lease['session']
    directory.mkdir(mode=0o700, exist_ok=True)
    output = directory/('json-attempt-%02d' % lease['attempts'])
    output.mkdir(exist_ok=True)
    db = sqlite3.connect(STATE/'aircraft.sqlite')
    db.executescript('''PRAGMA journal_mode=WAL;
      CREATE TABLE IF NOT EXISTS frames(session TEXT,utc TEXT,kind INTEGER,ticks INTEGER,signal INTEGER,payload TEXT,icao TEXT);
      CREATE TABLE IF NOT EXISTS snapshots(session TEXT,utc TEXT,kind TEXT,json TEXT);
      CREATE TABLE IF NOT EXISTS aircraft(icao TEXT PRIMARY KEY,first_seen TEXT,last_seen TEXT,sessions INTEGER,last_session TEXT,json TEXT);
      CREATE TABLE IF NOT EXISTS sessions(id TEXT PRIMARY KEY,start REAL,expiry REAL,provenance TEXT);
    ''')
    provenance = run('docker','run','--rm','--entrypoint','sh',IMAGE,'-c','cat /rtl-source.txt /decoder-source.txt; sha256sum /usr/local/bin/dump1090 /usr/local/lib/librtlsdr.so.0; /usr/local/bin/dump1090 --help',check=False)
    atomic(directory/'provenance.json', dict(utc=utc(), image=run('docker','image','inspect',IMAGE,'--format','{{.Id}}'),build=provenance,frequency_hz=1090000000,gain_db=38.6,bias_tee=False,receiver='V4MAIN01'))
    db.execute('INSERT OR IGNORE INTO sessions VALUES(?,?,?,?)',(lease['session'],lease['start'],lease['expiry'],provenance))
    db.commit()
    args = ['docker','run','--rm','--name',NAME,'--device',lease['usb_node'],
            '-p','127.0.0.1:30005:30005','-v',str(output)+':/output',IMAGE,
            '--device','V4MAIN01','--gain','38.6','--no-fix','--net-verbatim','--net','--net-heartbeat','0','--net-bo-port','30005',
            '--net-ro-port','0','--net-sbs-port','0','--net-bi-port','0','--net-ri-port','0',
            '--write-json','/output','--write-json-every','1','--json-stats-every','10',
            '--json-location-accuracy','0','--quiet']
    atomic(directory/'command.json', args)
    log = (directory/'decoder.log').open('ab',buffering=0)
    process = sp.Popen(args,stdout=log,stderr=log)
    sock, buf, last, total, last_frame = None, b'', 0, 0, None
    stream_activity = time.monotonic()
    sample_progress, samples, stats_summary = time.monotonic(), -1, {}
    json_mtimes = {}
    deadline = time.monotonic()+max(0,lease['expiry']-time.time())
    try:
        while time.time()<lease['expiry'] and time.monotonic()<deadline:
            if process.poll() is not None:
                raise RuntimeError('Decoder exited '+str(process.returncode))
            if time.monotonic()-sample_progress > 120:
                raise RuntimeError('Decoder sample counters stalled for 120 seconds')
            size = sum(p.stat().st_size for p in STATE.glob('aircraft.sqlite*'))
            if size > CAP or shutil.disk_usage(STATE).free < 2*1024**3 or log.tell()>16*1024**2:
                lease['abort']='storage safety bound reached'
                atomic(LEASE,lease)
                return
            if sock is None:
                try:
                    sock=socket.create_connection(('127.0.0.1',30005),timeout=1)
                    sock.settimeout(.5)
                except OSError:
                    time.sleep(.5)
                    if time.monotonic()-stream_activity > 90:
                        raise RuntimeError('Beast listener unavailable for 90 seconds')
                    continue
            try:
                chunk=sock.recv(65536)
                if not chunk:
                    sock.close()
                    sock = None
                    time.sleep(.5)
                    if time.monotonic()-stream_activity > 90:
                        raise RuntimeError('Beast stream closed for 90 seconds')
                    continue
                stream_activity = time.monotonic()
                rows,buf=frames(buf+chunk)
                stamp=utc()
                for kind,data in rows:
                    payload=data[7:]
                    # DF18 can use non-ICAO address namespaces; let the decoder
                    # annotate those in snapshots rather than guessing here.
                    icao=payload[1:4].hex() if payload and payload[0]>>3 == 17 else None
                    db.execute('INSERT INTO frames VALUES(?,?,?,?,?,?,?)',(lease['session'],stamp,kind,int.from_bytes(data[:6],'big'),data[6],payload.hex(),icao))
                total+=len(rows)
                if rows:
                    last_frame=stamp
            except socket.timeout:
                pass
            if time.monotonic()-last >= 1:
                for kind in ('aircraft','stats'):
                    try:
                        source=output/(kind+'.json')
                        mtime=source.stat().st_mtime_ns
                        if json_mtimes.get(kind)==mtime:
                            continue
                        raw=source.read_text()
                        parsed=json.loads(raw)
                        json_mtimes[kind]=mtime
                    except (OSError,ValueError):
                        continue
                    db.execute('INSERT INTO snapshots VALUES(?,?,?,?)',(lease['session'],utc(),kind,raw))
                    if kind=='aircraft':
                        for ac in parsed.get('aircraft',[]):
                            # Ignore stale retained records; decoder message age is explicit in original JSON.
                            if ac.get('seen',999)>2:
                                continue
                            hexid=ac['hex']
                            db.execute('''INSERT INTO aircraft VALUES(?,?,?,?,?,?) ON CONFLICT(icao) DO UPDATE SET
                              last_seen=excluded.last_seen,sessions=aircraft.sessions+(aircraft.last_session!=excluded.last_session),
                              last_session=excluded.last_session,json=excluded.json''',(hexid,utc(),utc(),1,lease['session'],json.dumps(ac)))
                    else:
                        stats_summary=parsed.get('total',{}).get('local',{})
                        progress=stats_summary.get('samples_processed',0)
                        if progress>samples:
                            samples=progress
                            sample_progress=time.monotonic()
                db.commit()
                atomic(directory/'health.json',dict(utc=utc(),session=lease['session'],expiry=lease['expiry'],frames_this_attempt=total,last_frame_utc=last_frame,database_bytes=size,aircraft_all_sessions=db.execute('SELECT count(*) FROM aircraft').fetchone()[0],attempt=lease['attempts'],decoder_stats=stats_summary))
                last=time.monotonic()
        event('deadline_reached', session=lease['session'])
    finally:
        db.commit()
        db.close()
        run('docker','stop','-t','5',NAME,check=False)
        if sock:
            sock.close()
        process.wait(timeout=15)
        log.close()

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action',choices=('install','start','capture','tick','restore'))
    parser.add_argument('--seconds',type=int,default=43200)
    args=parser.parse_args()
    STATE.mkdir(mode=0o700,exist_ok=True)
    os.umask(0o077)
    # Serializes lease changes with the independent watchdog; capture uses separate receiver lock.
    if args.action=='capture':
        try:
            capture()
        except Exception as error:
            event('capture_error', error=repr(error))
            raise
    else:
        with (STATE/'control.lock').open('a') as lock:
            fcntl.flock(lock,fcntl.LOCK_EX)
            start(args.seconds) if args.action=='start' else globals()[args.action]()
