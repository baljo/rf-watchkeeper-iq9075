"""Five-minute health watchdog; safe direct probes and bounded escalating recovery."""
import argparse
from datetime import datetime
import fcntl
import json
import logging
import os
from pathlib import Path
import signal
import subprocess
import time
import rf_health as h
import meteor_recovery
import watchkeeper

SCHEDULER = 'rf-watchkeeper-scheduler.service'
PAUSE=h.ROOT/'data/rf-health-scheduler-pause.json'

def systemctl(*argv):
    return subprocess.run(['systemctl']+list(argv), timeout=30, check=True, capture_output=True,text=True)

def restore_scheduler():
    if not PAUSE.exists():
        return
    state=json.loads(PAUSE.read_text())
    if state.get('restore') and state.get('boot_id')==h.boot_id():
        if h.satellite_guard():
            return
        systemctl('start',SCHEDULER)
        h.event('service_restore','success','Scheduler restored after interrupted health check')
    PAUSE.unlink()

def approaching():
    plan = h.ROOT/'data/meteor-auto/plan.json'
    rows = json.loads(plan.read_text())['passes']
    future = [(h.timestamp(p['record_start'])-time.time(), p['id']) for p in rows if p['status'] in ('planned','claimed') and h.timestamp(p['record_stop'])>time.time()]
    # Manual timers preserve their own trigger and capture arguments.
    units = systemctl('list-units','--all','--type=timer','--plain','--no-legend').stdout
    for line in units.splitlines():
        unit = line.split()[0]
        if not unit.startswith(('meteor-','satellite-')):
            continue
        value = systemctl('show',unit,'-p','NextElapseUSecRealtime','--value').stdout.strip()
        if value and value != 'n/a':
            due = datetime.strptime(value,'%a %Y-%m-%d %H:%M:%S %Z').replace(tzinfo=__import__('datetime').timezone.utc).timestamp()
            future.append((due-time.time(),unit))
    return min(future) if future else (float('inf'),None)

def age(proc):
    fields = (Path('/proc')/str(proc)/'stat').read_text().rsplit(')',1)[1].split()
    start_ticks = int(fields[19])
    uptime = float(Path('/proc/uptime').read_text().split()[0])
    return uptime-start_ticks/os.sysconf('SC_CLK_TCK'), start_ticks

def stale_limit(argv):
    # Unknown/custom owners are protected. Never guess their maximum runtime.
    names = {Path(v).name for v in argv[:3]}
    if 'ais_collector.py' in names:
        try:
            seconds = float(argv[argv.index('--seconds')+1])
            return seconds+30 if seconds > 0 else None
        except (ValueError,IndexError):
            return None
    if 'AIS-catcher' in names and '-T' in argv:
        try:
            return float(argv[argv.index('-T')+1])+30
        except (ValueError,IndexError):
            return None
    return None

def clean_stale(serial):
    for pid, argv in meteor_recovery.v4_owners(serial):
        limit = stale_limit(argv)
        try:
            elapsed, token = age(pid)
            if limit is None or elapsed <= limit:
                continue
            if h.satellite_guard():
                return False
            h.event('stale_process','identified', 'PID %s elapsed %.1fs limit %.1fs'%(pid,elapsed,limit),serial)
            if age(pid)[1] != token:
                continue
            os.kill(pid,signal.SIGTERM)
            deadline = time.monotonic()+3
            while time.monotonic()<deadline:
                try:
                    if age(pid)[1] != token:
                        break
                except FileNotFoundError:
                    break
                time.sleep(.1)
            else:
                if not h.satellite_guard() and age(pid)[1] == token:
                    os.kill(pid,signal.SIGKILL)
            h.event('stale_process','terminated','PID '+str(pid),serial)
        except ProcessLookupError:
            pass
    return True

def run(force=False, simulate=False, no_reboot=False):
    cfg = h.config()
    if no_reboot:
        cfg['allow_reboot']=False
    with h.control_lock():
        if not simulate:
            restore_scheduler()
        if not cfg['receivers']['V4MAIN01']['enabled']:
            return 0
        serial='V4MAIN01'
        guard=h.satellite_guard()
        if guard:
            h.set_state('BUSY',guard)
            return 0
        lead,pass_id=approaching()
        prepass=0<lead<=cfg['prepass_seconds']
        with h.connect() as db:
            last=db.execute('SELECT completion_time FROM rf_health_jobs WHERE receiver_serial=? AND capture_ok=1 AND boot_id=? ORDER BY completion_time DESC,id DESC LIMIT 1',(serial,h.boot_id())).fetchone()
            pending=db.execute('SELECT * FROM rf_health_jobs WHERE receiver_serial=? AND completion_time IS NULL ORDER BY id DESC LIMIT 1',(serial,)).fetchone()
            checked=db.execute("SELECT timestamp FROM rf_health_events WHERE action='prepass' AND result='success' AND detail=? ORDER BY id DESC LIMIT 1",(pass_id,)).fetchone() if pass_id else None
        elapsed=time.time()-h.timestamp(last[0]) if last else float('inf')
        if checked and time.time()-h.timestamp(checked[0])<cfg['prepass_seconds']:
            prepass=False
        overdue=pending and time.time()>pending['deadline']
        if overdue and not simulate:
            h.finish(pending['id'],False,reason='RF job exceeded configured dwell plus 30-second hard deadline')
        if not force and not prepass and not overdue and elapsed<cfg['green_seconds']:
            h.set_state('GREEN','Recent successful sample acquisition')
            return 0
        if pending and not overdue and not force and not prepass:
            try:
                os.kill(pending['pid'],0)
                h.set_state('BUSY','Known RF job within its configured dwell: '+pending['job_type'])
                return 0
            except ProcessLookupError:
                if not simulate:
                    h.finish(pending['id'],False,reason='RF job owner exited without completion report')
        if prepass:
            h.event('prepass','started',pass_id)
        elif elapsed>=cfg['green_seconds']:
            h.event('heartbeat_stale','warning','age='+str(int(elapsed)) if last else 'No receiver heartbeat yet')
        if simulate:
            h.event('simulation','no_actions','Would inspect/probe/recover; no processes or services changed')
            return 0
        was_active=subprocess.run(['systemctl','is-active','--quiet',SCHEDULER],timeout=5).returncode==0
        # Stop an ordinary job only for prepass, a requested test, overdue work,
        # or lack of any sample heartbeat for a full scheduler cycle threshold.
        if was_active and not (force or prepass or overdue or elapsed>=cfg['green_seconds']):
            h.set_state('BUSY','Ordinary RF job within dwell')
            return 0
        reboot=False
        try:
            if h.satellite_guard():
                return 0
            if was_active:
                meteor_recovery.save(PAUSE,dict(restore=True,boot_id=h.boot_id(),paused_at=h.stamp()))
                systemctl('stop',SCHEDULER)
            if h.satellite_guard():
                return 0
            clean_stale(serial)
            owners=meteor_recovery.v4_owners(serial)
            if owners:
                h.set_state('BUSY','Protected owner: '+str(owners))
                return 0
            with watchkeeper.device_lock(serial):
                if h.satellite_guard():
                    return 0
                if h.probe(serial,'meteor-prepass' if prepass else 'direct-probe'):
                    h.set_state('GREEN','METEOR readiness verified' if prepass else 'Direct sample probe successful')
                    h.event('recovery','success','Direct probe; receiver usable',serial)
                    if prepass:
                        h.event('prepass','success',pass_id,serial)
                    return 0
                h.event('recovery','stage2','Inspect demonstrably stale V4 owners',serial)
                if h.satellite_guard():
                    return 0
                clean_stale(serial)
                if h.probe(serial):
                    h.event('recovery','success','After stale-owner inspection',serial)
                    h.set_state('GREEN','Recovered after owner cleanup')
                    return 0
                # No safe targeted reset facility exists on this EVK. Do not reset hubs.
                recovery=cfg.get('usb_recovery_command')
                if recovery:
                    if h.satellite_guard():
                        return 0
                    h.event('usb_recovery','attempt',str(recovery),serial)
                    subprocess.run(recovery,check=True,timeout=15)
                else:
                    h.event('usb_recovery','unavailable','No verified V4-only reset mechanism; stage skipped',serial)
                if h.probe(serial):
                    h.set_state('GREEN','Recovered at USB recovery stage')
                    h.event('recovery','success','USB recovery stage',serial)
                    return 0
            if h.satellite_guard():
                return 0
            # Keep scheduler stopped during the verification; start only after release.
            systemctl('reset-failed',SCHEDULER)
            systemctl('start',SCHEDULER)
            systemctl('stop',SCHEDULER)
            h.event('service_restart','completed',SCHEDULER,serial)
            if h.satellite_guard():
                return 0
            if meteor_recovery.v4_owners(serial):
                h.set_state('BUSY','Owner appeared during service restart')
                return 0
            with watchkeeper.device_lock(serial):
                if h.satellite_guard():
                    return 0
                if h.probe(serial):
                    h.set_state('GREEN','Recovered after service restart')
                    h.event('recovery','success','Service restart',serial)
                    return 0
            h.set_state('RED','Sample probes failed after staged recovery')
            lead,_=approaching()
            if not cfg['allow_reboot'] or lead<cfg['minimum_reboot_lead_seconds'] or h.satellite_guard():
                h.event('reboot','suppressed','Disabled, satellite protected, or insufficient prepass lead time',serial)
                return 0
            if not h.reboot_allowed('V4 watchdog sample probes exhausted'):
                h.event('reboot','rate_limited','Automatic reboot within last hour',serial)
                return 0
            h.event('reboot','requested','Persistent hourly guard consumed; failed acquisition across recovery stages',serial)
            os.sync()
            systemctl('reboot')
            reboot=True
            return 0
        finally:
            if was_active and not reboot and not h.satellite_guard():
                systemctl('start',SCHEDULER)
                if PAUSE.exists():
                    PAUSE.unlink()

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--force-probe',action='store_true')
    parser.add_argument('--simulate',action='store_true')
    parser.add_argument('--no-reboot',action='store_true',help='Live sample/recovery check with reboot suppressed')
    parser.add_argument('--restore-only',action='store_true',help='Restore scheduler after a health-service interruption')
    args=parser.parse_args()
    logging.basicConfig(level=logging.INFO,format='%(asctime)s %(levelname)s %(message)s')
    try:
        if args.restore_only:
            with h.control_lock():
                restore_scheduler()
            return 0
        return run(args.force_probe,args.simulate,args.no_reboot)
    except BlockingIOError:
        if h.satellite_guard():
            h.set_state('BUSY','Active satellite reservation; recovery suppressed')
        return 0
    except Exception as exc:
        h.event('monitor','failed',str(exc))
        h.set_state('UNKNOWN','Health monitor failed safely: '+str(exc))
        return 1

if __name__=='__main__':
    raise SystemExit(main())
