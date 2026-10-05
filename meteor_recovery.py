# Preserve METEOR reservations and resume real IQ capture after one guarded EVK reboot; 2026-10-04 22:11 EEST, Thomas Vikström.
import argparse
from datetime import datetime, timezone, timedelta
import fcntl
import hashlib
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time
import rf_health

ROOT = Path(__file__).resolve().parent
STATE = ROOT / 'data/meteor-recovery'
UNITS = Path('/etc/systemd/system')
MIN_REMAINING = 60
HEADER = '# Resume a persisted METEOR reservation after guarded reboot; 2026-10-04 22:11 EEST, Thomas Vikström.\n'


def now():
    return datetime.now(timezone.utc)


def dt(value):
    return datetime.fromisoformat(value).astimezone(timezone.utc)


def log(message):
    print('INFO: ' + message, flush=True)


def boot_id():
    return Path('/proc/sys/kernel/random/boot_id').read_text().strip()


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix('.tmp')
    with temporary.open('w') as stream:
        json.dump(value, stream, indent=2)
        stream.write('\n')
        stream.flush()
        os.fsync(stream.fileno())
    temporary.replace(path)
    descriptor = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def state_path(satellite, start):
    identity = satellite + '-' + dt(start).isoformat()
    return STATE / (hashlib.sha256(identity.encode()).hexdigest()[:24] + '.json')


def pending(path):
    if not path.exists():
        return False
    return json.loads(path.read_text()).get('state') in ('reboot_requested', 'resuming')


def register(args, metadata):
    path = state_path(args.satellite, args.start)
    if not path.exists():
        save(path, dict(state='reserved', boot_id=boot_id(), reboot_count=0,
                        record_stop=metadata['record_stop'], metadata=str(Path(metadata['iq_file']).with_suffix('.json')),
                        iq=metadata['iq_file'], managed_record=args.recovery_record,
                        argv=[sys.executable, '-u', str(ROOT / 'satellite_capture.py')] + sys.argv[1:]))
    return path


def install_timer(path):
    name = 'meteor-recovery-' + path.stem
    service = HEADER + f'''[Unit]
Description=METEOR persisted reboot recovery {path.stem}
After=local-fs.target time-sync.target rf-watchkeeper-scheduler.service

[Service]
Type=simple
WorkingDirectory={ROOT}
ExecStart={sys.executable} -u {ROOT / 'meteor_recovery.py'} resume {path}
TimeoutStopSec=20
RuntimeMaxSec=40min
KillMode=control-group
UMask=0077
'''
    timer = HEADER + f'''[Unit]
Description=METEOR persistent recovery reservation {path.stem}

[Timer]
OnBootSec=20s
OnActiveSec=15s
OnUnitInactiveSec=15s
AccuracySec=1s
Unit={name}.service

[Install]
WantedBy=timers.target
'''
    # Files on /etc and enabled timers.target link survive transient job loss.
    for suffix, text in (('.service', service), ('.timer', timer)):
        target = UNITS / (name + suffix)
        target.write_text(text)
    subprocess.run(['systemd-analyze', 'verify', str(UNITS / (name + '.service')),
                    str(UNITS / (name + '.timer'))], check=True, timeout=30)
    subprocess.run(['systemctl', 'daemon-reload'], check=True, timeout=30)
    return name


def request_reboot(path):
    with path.with_suffix('.reboot.lock').open('a') as stream:
        try:
            fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            log('reboot recovery already attempted or in progress; refusing reboot loop')
            return False
        return request_reboot_locked(path)


def request_reboot_locked(path):
    r = json.loads(path.read_text())
    if r['reboot_count']:
        log('reboot recovery already attempted; refusing reboot loop')
        return False
    if (dt(r['record_stop']) - now()).total_seconds() < MIN_REMAINING + 90:
        log('pass window already expired or too short for reboot recovery')
        return False
    # Do not consume the guard or reboot unless persistent units are validated.
    name = install_timer(path)
    if not rf_health.reboot_allowed("METEOR preflight recovery"):
        rf_health.event("reboot", "rate_limited", "METEOR automatic reboot within last hour")
        return False
    rf_health.event("reboot", "requested", "METEOR persisted recovery")
    r.update(state='reboot_requested', reboot_count=1, boot_id=boot_id(), requested_at=now().isoformat())
    save(path, r)
    try:
        subprocess.run(['systemctl', 'enable', '--now', name + '.timer'], check=True, timeout=30)
        subprocess.run(['systemctl', 'is-enabled', name + '.timer'], check=True, timeout=10)
    except subprocess.SubprocessError:
        r.update(state='failed', reason='persistent recovery timer could not be enabled')
        save(path, r)
        disable_timer(path)
        raise
    log('initiating last-resort reboot recovery; persistent reservation installed')
    try:
        result = subprocess.run(['/bin/sh', str(ROOT / 'satellite_v4_preflight.sh'),
                                 '--reboot-only', str(path)], timeout=30)
        failed = result.returncode != 0
    except subprocess.SubprocessError:
        failed = True
    if failed:
        r.update(state='failed', reason='last-resort reboot command failed')
        save(path, r)
        disable_timer(path)
        return False
    return True


def disable_timer(path):
    subprocess.run(['systemctl', 'disable', '--now', 'meteor-recovery-' + path.stem + '.timer'],
                   check=False, timeout=30)


def finish_managed(r, success, reason):
    record = r.get('managed_record')
    if not record:
        return
    import meteor_pipeline as pipeline
    path = Path(record)
    value = pipeline.read(path)
    metadata = Path(r['metadata'])
    capture = pipeline.read(metadata) if metadata.exists() else {}
    iq = Path(r['iq'])
    value.update(state='pending_decode' if success else 'capture_failed', capture=capture,
                 capture_finished_at=now().isoformat(), needs_scheduler_recovery=False,
                 captured_iq_bytes=iq.stat().st_size if iq.exists() else 0,
                 scheduler_restored=pipeline.active(pipeline.SCHEDULER), recovery_reason=reason)
    if iq.exists():
        value['iq_fingerprint'] = pipeline.fingerprint(iq)
    pipeline.save(path, value)
    pipeline.update_pass(value['pass']['id'], status='attempted', recovery_reason=reason)


def other_satellite(path):
    own_unit = 'meteor-recovery-' + path.stem + '.service'
    output = subprocess.check_output(['systemctl', 'list-units', '--type=service',
                                      '--state=active,activating,deactivating', '--plain', '--no-legend'], text=True)
    for line in output.splitlines():
        name = line.split()[0]
        if name.startswith(('meteor-', 'satellite-')) and name != own_unit:
            return name
    for proc in Path('/proc').glob('[0-9]*/cmdline'):
        try:
            argv = proc.read_bytes().split(b'\0')
            if any(value.endswith(b'/satellite_capture.py') or value == b'satellite_capture.py' for value in argv):
                return 'recorder PID ' + proc.parent.name
        except OSError:
            pass
    return None


def resume(path):
    with path.with_suffix('.lock').open('a') as stream:
        fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        r = json.loads(path.read_text())
        if r['state'] not in ('reboot_requested', 'resuming'):
            disable_timer(path)
            return
        if r['boot_id'] == boot_id():
            if now() - dt(r['requested_at']) < timedelta(seconds=120):
                return  # Timer may run before shutdown; never duplicate the recorder.
            reason = 'reboot did not occur within bounded recovery interval'
        elif (dt(r['record_stop']) - now()).total_seconds() < MIN_REMAINING:
            reason = 'pass window already expired or insufficient useful recording window'
            log('pass window already expired')
        elif r['state'] == 'resuming':
            reason = 'post-reboot recovery was interrupted; attempts exhausted'
        elif other_satellite(path):
            reason = 'another satellite owner is active; refusing conflicting recovery'
        else:
            synchronized = subprocess.check_output(['timedatectl', 'show', '-p', 'NTPSynchronized', '--value'], text=True).strip()
            if synchronized != 'yes':
                return  # Retry on timer until synchronized or window expires.
            r.update(state='resuming', resumed_at=now().isoformat())
            save(path, r)
            log('post-reboot capture resumed')
            m = {}
            try:
                rc = subprocess.run(r['argv'], timeout=max(1, (dt(r['record_stop']) - now()).total_seconds()) + 60).returncode
                m = json.loads(Path(r['metadata']).read_text()) if Path(r['metadata']).exists() else {}
                iq = Path(r['iq'])
                seconds = (dt(m['actual_stop']) - dt(m['actual_start'])).total_seconds() if m.get('actual_start') and m.get('actual_stop') else 0
                success = (rc == 0 and m.get('status') == 'completed' and seconds > 0 and iq.exists()
                           and iq.stat().st_size >= seconds * m['sample_rate_sps'] and iq.stat().st_size % 2 == 0)
            except (OSError, ValueError, subprocess.SubprocessError) as exc:
                log('post-reboot capture error: ' + str(exc))
                success = False
            # A killed/timed-out recorder cannot execute its scheduler-restoration finally.
            if subprocess.run(['systemctl', 'is-active', '--quiet', 'rf-watchkeeper-scheduler.service'],
                              timeout=10).returncode != 0 and not other_satellite(path):
                release_v4('V4MAIN01')
                subprocess.run(['systemctl', 'start', 'rf-watchkeeper-scheduler.service'], check=True, timeout=30)
            reason = 'METEOR capture successful' if success else 'METEOR capture failed after recovery'
            if not success and Path(r['metadata']).exists():
                m.update(status='failed_after_recovery', recovery_reason=reason)
                save(Path(r['metadata']), m)
            r.update(state='completed' if success else 'failed', reason=reason)
            save(path, r)
            try:
                finish_managed(r, success, reason)
            finally:
                disable_timer(path)
                log(reason)
            return
        log('METEOR capture failed after recovery: ' + reason)
        metadata = Path(r['metadata'])
        if metadata.exists():
            value = json.loads(metadata.read_text())
            value.update(status='failed_after_recovery', recovery_reason=reason)
            save(metadata, value)
        if not other_satellite(path):
            subprocess.run(['systemctl', 'start', 'rf-watchkeeper-scheduler.service'], check=True, timeout=30)
        r.update(state='failed', reason=reason)
        save(path, r)
        try:
            finish_managed(r, False, reason)
        finally:
            disable_timer(path)


def v4_owners(serial):
    # Explicit serial selection or actual V4 USB FD ownership; never global pkill.
    usb_nodes = set()
    for device in Path('/sys/bus/usb/devices').glob('*'):
        try:
            if (device / 'serial').read_text().strip() == serial:
                usb_nodes.add('/dev/bus/usb/{:03d}/{:03d}'.format(int((device / 'busnum').read_text()), int((device / 'devnum').read_text())))
        except (OSError, ValueError):
            pass
    owners = []
    for proc in Path('/proc').glob('[0-9]*'):
        try:
            argv = [v.decode(errors='replace') for v in (proc / 'cmdline').read_bytes().split(b'\0') if v]
            names = {Path(v).name for v in argv[:3]}
            if not names.intersection({'AIS-catcher', 'ais_collector.py', 'rtl_sdr', 'rtl_fm', 'rtl_power', 'rtl_433'}):
                continue
            owns_usb = False
            for fd in (proc / 'fd').iterdir():
                try:
                    owns_usb = owns_usb or os.readlink(fd) in usb_nodes
                except OSError:
                    pass
            if serial in argv or owns_usb:
                owners.append((int(proc.name), argv))
        except (OSError, ProcessLookupError):
            pass
    # An orphan AIS collector can launch another receiver; include its known V4 child's parent.
    for pid, _ in list(owners):
        try:
            status = Path(f'/proc/{pid}/status').read_text()
            parent = next(line.split()[1] for line in status.splitlines() if line.startswith('PPid:'))
            argv = [v.decode(errors='replace') for v in Path(f'/proc/{parent}/cmdline').read_bytes().split(b'\0') if v]
            if any(Path(v).name == 'ais_collector.py' for v in argv[:3]) and int(parent) not in {p for p, _ in owners}:
                owners.append((int(parent), argv))
        except (OSError, StopIteration):
            pass
    return owners


def release_v4(serial):
    for sig in (signal.SIGTERM, signal.SIGKILL):
        owners = v4_owners(serial)
        if not owners:
            return
        for pid, argv in owners:
            log(f'remaining V4 owner detected: PID {pid} {argv}; sending {sig.name}')
            try:
                os.kill(pid, sig)
            except ProcessLookupError:
                pass
        time.sleep(2)
    if v4_owners(serial):
        raise RuntimeError('remaining V4 owner detected after bounded cleanup')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('command', choices=['resume'])
    parser.add_argument('path', type=Path)
    arguments = parser.parse_args()
    resume(arguments.path)
