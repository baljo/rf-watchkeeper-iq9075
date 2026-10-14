"""Persistent RF acquisition suspend/status/resume; preserves retention and dashboard."""
import argparse
from contextlib import contextmanager
import fcntl
import json
from pathlib import Path
import subprocess
import time

ROOT=Path(__file__).resolve().parent
KEEP={'rf-watchkeeper-dashboard.service','rf-watchkeeper-meteor-cleanup.service',
      'rf-watchkeeper-meteor-cleanup.timer','rf-watchkeeper-audio-retention.service',
      'rf-watchkeeper-audio-retention.timer'}
MARKER=ROOT/'data/acquisition-suspended.json'

def run(*args,check=True):
    return subprocess.run(['systemctl',*args],check=check,text=True,
                          stdout=subprocess.PIPE,stderr=subprocess.PIPE).stdout.strip()

def discover():
    lines=run('list-unit-files','--no-legend','--no-pager').splitlines()
    lines+=run('list-units','--all','--plain','--no-legend','--no-pager').splitlines()
    return sorted({line.split()[0] for line in lines if line.split() and
                   line.split()[0].startswith(('rf-watchkeeper','meteor-','satellite-')) and
                   line.split()[0].endswith(('.service','.timer'))}-KEEP)

def properties(unit):
    return dict(line.split('=',1) for line in run('show',unit,'-p','ActiveState','-p','UnitFileState').splitlines() if '=' in line)

def atomic(path,value):
    path.parent.mkdir(parents=True,exist_ok=True)
    tmp=path.with_suffix('.tmp');tmp.write_text(json.dumps(value,indent=2)+'\n');tmp.replace(path)

@contextmanager
def mutex():
    (ROOT/'data').mkdir(exist_ok=True)
    with (ROOT/'data/acquisition-control.lock').open('a') as fd:
        fcntl.flock(fd,fcntl.LOCK_EX);yield

def status():
    units=discover()
    active={u:properties(u)['ActiveState'] for u in units}
    running=[u for u,s in active.items() if s in ('active','activating','deactivating')]
    return dict(suspended=MARKER.exists(),message='RF Watchkeeper suspended' if MARKER.exists() else 'RF Watchkeeper acquisition enabled',
                active_acquisition_units=running,
                retention={u:properties(u) for u in sorted(KEEP) if 'cleanup' in u or 'retention' in u},
                dashboard=properties('rf-watchkeeper-dashboard.service'))

def suspend():
    with mutex():
        units=discover()
        if MARKER.exists():
            saved=json.loads(MARKER.read_text())
        else:
            saved=dict(created_at=time.time(),units={u:properties(u) for u in units})
            atomic(MARKER,saved)
        # Marker exists before guard installation/stopping. Interrupted operations
        # can be completed by another suspend or resume invocation.
        for unit in units:
            if unit not in saved['units']:
                saved['units'][unit]=properties(unit);atomic(MARKER,saved)
            drop=Path('/etc/systemd/system')/(unit+'.d')/'90-acquisition-suspend.conf'
            drop.parent.mkdir(parents=True,exist_ok=True)
            drop.write_text('[Unit]\nConditionPathExists=!'+str(MARKER)+'\n')
        run('daemon-reload')
        timers=[u for u in units if u.endswith('.timer')]
        services=[u for u in units if u.endswith('.service')]
        # Disable starts after reboot; guards also reject manual/dependency starts.
        for u in units:
            if properties(u).get('UnitFileState') in ('enabled','enabled-runtime'):run('disable',u)
        if timers:run('stop',*timers)
        if services:run('stop',*services)
        result=status()
        if result['active_acquisition_units']:raise RuntimeError('Acquisition units did not stop: '+str(result['active_acquisition_units']))
        return result

def resume():
    with mutex():
        pending=ROOT/'data/acquisition-resume-pending.json'
        if not MARKER.exists() and not pending.exists():return status()
        saved=json.loads((MARKER if MARKER.exists() else pending).read_text())
        for unit,old in saved['units'].items():
            if old.get('UnitFileState') in ('enabled','enabled-runtime'):
                args=['enable']
                if old['UnitFileState']=='enabled-runtime':args.append('--runtime')
                run(*args,unit)
        atomic(pending,saved)
        MARKER.unlink(missing_ok=True)
        try:
            # Restore only intended running units, never replay idle one-shot jobs.
            services=[u for u,s in saved['units'].items() if u.endswith('.service') and s['ActiveState']=='active']
            timers=[u for u,s in saved['units'].items() if u.endswith('.timer') and s['ActiveState'] in ('active','activating')]
            if services:run('start',*services)
            if timers:run('start',*timers)
        except Exception:
            atomic(MARKER,saved)
            run('stop',*services,*timers,check=False)
            raise  # Caller can retry; guards remain installed permanently.
        atomic(ROOT/'data/acquisition-last-resume.json',saved)
        pending.unlink(missing_ok=True)
        return status()

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action',choices=('suspend','status','resume'))
    args=parser.parse_args()
    print(json.dumps(globals()[args.action](),indent=2))
