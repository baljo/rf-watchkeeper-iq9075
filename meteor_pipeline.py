# Dispatch persisted METEOR passes and preserve claims through bounded reboot recovery; 2026-10-04 22:15 EEST, Thomas Vikström.
import argparse
import contextlib
from datetime import datetime, timedelta, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import re
import shutil
import signal
import subprocess
import sys
import time
import threading
import uuid
import meteor_store
import meteor_retention
import meteor_frequency
import meteor_recovery as recovery
from zoneinfo import ZoneInfo

ROOT = Path('/root/rf-watchkeeper')
STATE = ROOT / 'data/meteor-auto'
CAPTURE_SERVICE = 'meteor-auto-capture.service'
SCHEDULER = 'rf-watchkeeper-scheduler.service'
UTC = timezone.utc
HELSINKI = ZoneInfo('Europe/Helsinki')


def now():
    return datetime.now(UTC)


def dt(value):
    value = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if value.tzinfo is None:
        raise ValueError('Timezone required')
    return value.astimezone(UTC)


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def fingerprint(path):
    stat = Path(path).stat()
    return dict(device=stat.st_dev, inode=stat.st_ino, bytes=stat.st_size, modified_ns=stat.st_mtime_ns)


def save(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + '.tmp')
    with temporary.open('w', encoding='utf-8') as stream:
        json.dump(data, stream, indent=2, ensure_ascii=False)
        stream.write('\n')
        stream.flush()
        os.fsync(stream.fileno())
    temporary.replace(path)


def event(kind, **fields):
    row = dict(at=now().isoformat(), event=kind, **fields)
    print(json.dumps(row), flush=True, file=sys.stderr)
    STATE.mkdir(parents=True, exist_ok=True)
    with (STATE / 'events.jsonl').open('a', encoding='utf-8') as stream:
        stream.write(json.dumps(row) + '\n')


@contextlib.contextmanager
def lock(name):
    import fcntl
    STATE.mkdir(parents=True, exist_ok=True)
    with (STATE / (name + '.lock')).open('a') as stream:
        fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        yield


def command(argv):
    return subprocess.check_output(argv, text=True, timeout=30, env=dict(os.environ, LC_ALL='C', TZ='UTC')).strip()


def active(unit):
    return command(['systemctl', 'show', unit, '-p', 'ActiveState', '--value']) in ('active', 'activating', 'deactivating')


def synchronized():
    if command(['timedatectl', 'show', '-p', 'NTPSynchronized', '--value']) != 'yes':
        raise RuntimeError('Clock is not synchronized; refusing automatic capture')


def config(path):
    c = read(path)
    if c['device'] != 'V4MAIN01' or c['sample_rate'] not in (256000, 1024000):
        raise ValueError('METEOR requires V4MAIN01 and a supported sample rate')
    bounds = {'latitude': (-90, 90), 'longitude': (-180, 180), 'hours': (1, 48),
              'min_peak_deg': (10, 90), 'horizon_deg': (1, 20), 'min_free_gib': (1, 1000),
              'max_tle_age_days': (0.1, 7), 'raw_retention_days': (1, 3650),
              'pre_margin': (0, 300), 'post_margin': (0, 300), 'preflight_seconds': (30, 300),
              'dispatch_lead_seconds': (5, 60), 'max_lateness_seconds': (0, 60),
              'max_passes_per_day': (1, 8), 'decode_timeout_seconds': (1, 7200),
              'max_decode_attempts': (1, 10), 'decode_retry_seconds': (60, 86400)}
    for name, (low, high) in bounds.items():
        value = c[name]
        if type(value) not in (int, float) or not math.isfinite(value) or not low <= value <= high:
            raise ValueError('Invalid configuration: ' + name)
    for name in ('enabled', 'cleanup_enabled'):
        if type(c[name]) is not bool:
            raise ValueError(name + ' must be boolean')
    for name in ('satdump_command', 'satdump_prefix', 'satdump_extra'):
        if not isinstance(c[name], list) or any(not isinstance(s, str) for s in c[name]):
            raise ValueError(name + ' must be an argv list')
    if not c['satdump_command']:
        raise ValueError('Empty SatDump command')
    meteor_retention.settings(c)
    f = c.get('frequency_evaluation', {})
    for name, low, high in (('span_hz', 10000, 60000), ('windows', 8, 64), ('max_candidates', 1, 2), ('budget_seconds', 60, 1800)):
        value = f.get(name, dict(span_hz=60000, windows=24, max_candidates=2, budget_seconds=300)[name])
        if type(value) is not int or not low <= value <= high:
            raise ValueError('Invalid frequency evaluation setting: ' + name)
    return c


def reservations():
    """Inspect existing manual timers without touching their files or state."""
    lines = command(['systemctl', 'list-units', '--all', '--type=timer', '--plain', '--no-legend']).splitlines()
    result = []
    for line in lines:
        name = line.split()[0]
        if not name.startswith(('meteor-', 'satellite-')) or name.startswith('meteor-auto-'):
            continue
        micros = command(['systemctl', 'show', name, '-p', 'NextElapseUSecRealtime', '--value'])
        if not micros or micros == 'n/a':
            continue
        trigger = datetime.strptime(micros, '%a %Y-%m-%d %H:%M:%S %Z').replace(tzinfo=UTC)
        # Fallback blocks 45 minutes for unrecognized legacy/preflight units.
        start, end = trigger - timedelta(seconds=300), trigger + timedelta(minutes=45)
        text = command(['systemctl', 'cat', name.removesuffix('.timer') + '.service'])
        def argument(flag, default=None):
            match = re.search(r'"?' + re.escape(flag) + r'"?\s+"?([^"\s]+)', text)
            return match.group(1) if match else default
        if 'satellite_capture.py' in text and argument('--start') and argument('--stop'):
            start = min(start, dt(argument('--start')) - timedelta(seconds=int(argument('--pre-margin', '90')) + int(argument('--preflight-seconds', '120')) + 60))
            end = dt(argument('--stop')) + timedelta(seconds=int(argument('--post-margin', '90')) + 60)
        result.append(dict(unit=name, start=start.isoformat(), stop=end.isoformat()))
    return result


def satellite_busy():
    lines = command(['systemctl', 'list-units', '--type=service', '--state=active,activating,deactivating', '--plain', '--no-legend']).splitlines()
    for line in lines:
        name = line.split()[0]
        if name.startswith(('meteor-', 'satellite-')) and name != CAPTURE_SERVICE:
            return name
    # Covers a manually launched recorder outside systemd.
    for path in Path('/proc').glob('[0-9]*/cmdline'):
        try:
            args = path.read_bytes().split(b'\0')
            if any(a.endswith(b'/satellite_capture.py') or a == b'satellite_capture.py' for a in args):
                return 'recorder PID ' + path.parent.name
            if args and args[0].rsplit(b'/', 1)[-1] == b'rtl_sdr':
                return 'raw SDR process PID ' + path.parent.name
        except OSError:
            pass
    return None


def overlap(p, r):
    return dt(p['trigger']) < dt(r['stop']) and dt(p['record_stop']) + timedelta(seconds=60) > dt(r['start'])


def record_paths(p):
    stamp = dt(p['record_start']).strftime('%Y%m%d_%H%M%S')
    stem = '{}_{}_{}'.format(p['satellite'], stamp, p['frequency'])
    iq = ROOT / 'recordings/satellite' / (stem + '.cu8')
    return iq, iq.with_suffix('.json')


def predict(c):
    sys.path.insert(0, str(ROOT))
    import satellite_planner as planner
    ts = planner.load.timescale(builtin=True)
    observer = planner.wgs84.latlon(c['latitude'], c['longitude'], elevation_m=c['observer_elevation_m'])
    start = now()
    end = start + timedelta(hours=c['hours'])
    rows = []
    for short, tle, source in planner.load_satellites():
        sat = planner.EarthSatellite(tle['line1'], tle['line2'], tle['name'], ts)
        epoch = sat.epoch.utc_datetime()
        if max(abs((point - epoch).total_seconds()) for point in (start, end)) > c['max_tle_age_days'] * 86400:
            raise RuntimeError(short + ': stale TLE; no new plan committed')
        if sat.model.satnum != planner.SATELLITES[short]['norad']:
            raise RuntimeError(short + ': wrong NORAD ID in TLE')
        # Extend the search to include LOS for passes rising at the window edge.
        for row in planner.predict_passes(sat, observer, ts, start, c['hours'] + 1, c['horizon_deg'], c['min_peak_deg']):
            if not start <= row['aos'] < end:
                continue
            south = 0
            point = row['aos']
            while point <= row['los']:
                _, azimuth = planner.angle_at(sat, observer, ts.from_datetime(point))
                if c['south_azimuth_min'] <= azimuth <= c['south_azimuth_max']:
                    south += 10
                point += timedelta(seconds=10)
            record_start = row['aos'] - timedelta(seconds=c['pre_margin'])
            p = dict(id=short.replace('-', '').lower() + '-' + row['aos'].strftime('%Y%m%dT%H%M%SZ'),
                     satellite=short, start=row['aos'].isoformat(), stop=row['los'].isoformat(),
                     peak=row['tca'].isoformat(), peak_deg=row['max_elevation'], peak_azimuth=row['tca_az'],
                     south_seconds=south, tle_epoch=epoch.isoformat(), tle_source=source,
                     record_start=record_start.isoformat(),
                     record_stop=(row['los'] + timedelta(seconds=c['post_margin'])).isoformat(),
                     trigger=(record_start - timedelta(seconds=c['preflight_seconds'] + c['dispatch_lead_seconds'])).isoformat(),
                     **{k: c[k] for k in ('frequency', 'sample_rate', 'gain', 'device', 'pre_margin', 'post_margin', 'preflight_seconds')})
            rows.append(p)
    return rows


def select(rows, c, manual, existing):
    chosen, rejected, counts = [], [], {}
    for reservation in manual:
        if reservation.get('unit', '').startswith('meteor-'):
            date = dt(reservation['start']).astimezone(HELSINKI).date().isoformat()
            counts[date] = counts.get(date, 0) + 1
    protected = []
    for p in existing:
        if p['status'] not in ('planned', 'skipped'):
            date = dt(p['start']).astimezone(HELSINKI).date().isoformat()
            counts[date] = counts.get(date, 0) + 1
            # Capture-history records have recording bounds, but no dispatcher trigger.
            protected.append(dict(start=p.get('trigger', p['record_start']), stop=p['record_stop']))
    ids = {p['id'] for p in existing if p['status'] not in ('planned', 'skipped')}
    for p in sorted(rows, key=lambda p: (-p['south_seconds'], -p['peak_deg'], p['start'])):
        date = dt(p['start']).astimezone(HELSINKI).date().isoformat()
        reason = None
        if p['id'] in ids:
            reason = 'already attempted'
        elif dt(p['trigger']) <= now():
            reason = 'preflight window already started'
        elif p['south_seconds'] < c['min_south_seconds']:
            reason = 'insufficient south-window visibility'
        elif any(overlap(p, r) for r in manual + protected):
            reason = 'existing reservation overlaps'
        elif counts.get(date, 0) >= c['max_passes_per_day']:
            reason = 'daily limit'
        if reason:
            rejected.append(dict(id=p['id'], reason=reason))
        else:
            p = dict(p, status='planned')
            chosen.append(p)
            protected.append(dict(start=p['trigger'], stop=p['record_stop']))
            counts[date] = counts.get(date, 0) + 1
    return sorted(chosen, key=lambda p: p['trigger']), rejected


def plans():
    path = STATE / 'plan.json'
    return read(path) if path.exists() else dict(passes=[], generated_at=None)


def records():
    return sorted((STATE / 'passes').glob('*/pass.json'))


def plan(c, dry):
    with lock('schedule'):
        previous = plans()
        old = previous['passes']
        # Completed attempt records also enforce daily limits across replanning.
        attempted = {p['id']: p for p in old if p['status'] not in ('planned', 'skipped')}
        for path in records():
            p = read(path)['pass']
            if dt(p['start']) >= now() - timedelta(days=2):
                attempted[p['id']] = dict(p, status='attempted')
        manual = reservations()
        predictions = predict(c)
        prior = {p['id']: p for p in old if p['status'] == 'planned'}
        for p in predictions:
            if p['id'] in prior:
                for key in ('frequency', 'sample_rate', 'gain', 'device'):
                    p[key] = prior[p['id']][key]
        chosen, rejected = select(predictions, c, manual, list(attempted.values()))
        result = dict(generated_at=now().isoformat(), enabled=c['enabled'], passes=chosen,
                      rejected=rejected, manual_reservations=manual, dry_run=dry)
        if not dry:
            # In-flight claims remain visible to the capture service.
            result['passes'] += [p for p in old if p['status'] == 'claimed']
            save(STATE / 'plan.json', result)
            event('plan_saved', selected=len(chosen))
        print(json.dumps(result, indent=2))


def update_pass(pid, **fields):
    with lock('schedule'):
        data = plans()
        for p in data['passes']:
            if p['id'] == pid:
                p.update(fields)
        save(STATE / 'plan.json', data)


def run_capture(argv, stream, timeout):
    """Retain capture.log while also exposing receiver decisions in the journal."""
    with subprocess.Popen(argv, stdout=subprocess.PIPE, stderr=subprocess.STDOUT) as proc:
        def copy_output():
            for line in proc.stdout:
                stream.write(line)
                stream.flush()
                print(line.decode('utf-8', errors='replace').rstrip(), flush=True)
        reader = threading.Thread(target=copy_output, daemon=True)
        reader.start()
        try:
            return proc.wait(timeout=timeout)
        except BaseException:
            proc.terminate()
            try:
                proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait(timeout=5)
            raise
        finally:
            reader.join(timeout=5)


def dispatch(c):
    if not c['enabled']:
        return
    synchronized()
    with lock('schedule'):
        data = plans()
        if not data['generated_at'] or now() - dt(data['generated_at']) > timedelta(hours=8):
            raise RuntimeError('Plan missing or stale')
        if active(CAPTURE_SERVICE):
            return
        notice = STATE / 'dispatch-notice.json'
        future = [p for p in data['passes'] if p['status'] == 'planned' and now() < dt(p['trigger'])]
        next_pass = min(future, key=lambda p: p['trigger']) if future else None
        decision = dict(generated_at=data['generated_at'], next_id=next_pass['id'] if next_pass else None)
        if not notice.exists() or read(notice) != decision:
            event('dispatch_waiting' if next_pass else 'dispatch_no_upcoming_pass',
                  level='INFO', next_id=decision['next_id'], trigger=next_pass['trigger'] if next_pass else None)
            save(notice, decision)  # One notice per plan/next-pass change, not each thirty-second tick.
        for p in data['passes']:
            if p['status'] == 'claimed':
                if recovery.pending(recovery.state_path(p['satellite'], p['start'])):
                    continue  # Persistent recovery unit owns this reservation across reboot.
                p.update(status='interrupted', reason='capture service no longer active')
                event('capture_interrupted', id=p['id'], reason=p['reason'])
            if p['status'] != 'planned' or now() < dt(p['trigger']):
                continue
            reason = satellite_busy()
            if now() > dt(p['record_start']) + timedelta(seconds=c['max_lateness_seconds']):
                reason = 'missed capture window'
            if any(overlap(p, r) for r in reservations()):
                reason = 'manual satellite reservation'
            if reason:
                p.update(status='skipped', reason=reason)
                event('capture_skipped', id=p['id'], reason=reason)
                continue
            event('capture_claimed', id=p['id'], record_start=p['record_start'], record_stop=p['record_stop'])
            p['status'] = 'claimed'
            save(STATE / 'plan.json', data)
            try:
                command(['systemctl', 'start', CAPTURE_SERVICE])
                event('capture_service_started', id=p['id'], unit=CAPTURE_SERVICE)
            except Exception:
                p.update(status='interrupted', reason='service start failed')
                save(STATE / 'plan.json', data)
                raise
            return
        save(STATE / 'plan.json', data)


def capture(c):
    if not c['enabled']:
        return
    synchronized()
    if shutil.disk_usage(ROOT).free < meteor_retention.settings(c)['normal_free_gib'] * 1024**3:
        cleanup(c, c.get('cleanup_enabled', False) and meteor_retention.settings(c)['automatic_deletion_validated'])
    with lock('capture'):
        selected = [p for p in plans()['passes'] if p['status'] == 'claimed']
        if len(selected) != 1:
            raise RuntimeError('Exactly one claimed pass required')
        p = selected[0]
        directory = STATE / 'passes' / p['id']
        iq, metadata = record_paths(p)
        reason = satellite_busy()
        if any(overlap(p, r) for r in reservations()):
            reason = 'manual reservation'
        if not active(SCHEDULER):
            reason = 'V4 scheduler is not active; preserve intentional stopped state'
        if now() > dt(p['record_start']) + timedelta(seconds=c['max_lateness_seconds']):
            reason = 'capture window missed'
        seconds = (dt(p['record_stop']) - dt(p['record_start'])).total_seconds()
        if shutil.disk_usage(ROOT).free < seconds * p['sample_rate'] * 2 + c['min_free_gib'] * 1024**3:
            reason = 'insufficient disk headroom'
        if iq.exists() or metadata.exists() or directory.exists():
            reason = 'existing recording or attempt; never overwrite'
        if reason:
            update_pass(p['id'], status='skipped', reason=reason)
            event('capture_skipped', id=p['id'], reason=reason)
            return
        argv = [str(ROOT / '.satellite-venv/bin/python'), '-u', str(ROOT / 'satellite_capture.py'),
                '--satellite', p['satellite'], '--start', p['start'], '--stop', p['stop']]
        for flag, key in (('frequency', 'frequency'), ('sample-rate', 'sample_rate'), ('gain', 'gain'),
                          ('device', 'device'), ('pre-margin', 'pre_margin'), ('post-margin', 'post_margin'),
                          ('preflight-seconds', 'preflight_seconds')):
            argv += ['--' + flag, str(p[key])]
        argv += ['--recovery-record', str(directory / 'pass.json')]
        r = dict(schema_version=1, owner='meteor-auto-v1', pass_=p)
        r['pass'] = r.pop('pass_')
        r.update(state='capturing', iq=str(iq), capture_metadata=str(metadata),
                 started_at=now().isoformat(), capture_command=argv, score=None, analysis=None, notification=None)
        save(directory / 'pass.json', r)
        event('capture_started', id=p['id'])
        try:
            with (directory / 'capture.log').open('wb') as stream:
                rc = run_capture(argv, stream, max(1, (dt(p['record_stop']) - now()).total_seconds()) + 60)
            m = read(metadata) if metadata.exists() else {}
            if recovery.pending(recovery.state_path(p['satellite'], p['start'])):
                r.update(state='reboot_recovery_pending', capture=m)
                return
            valid = rc == 0 and m.get('status') == 'completed' and iq.exists() and iq.stat().st_size >= seconds * p['sample_rate'] and iq.stat().st_size % 2 == 0
            r.update(state='pending_decode' if valid else 'capture_failed', capture_returncode=rc,
                     capture=m, capture_finished_at=now().isoformat(), captured_iq_bytes=iq.stat().st_size if iq.exists() else 0)
            if iq.exists():
                r['iq_fingerprint'] = fingerprint(iq)
            r['scheduler_restored'] = active(SCHEDULER)
            if not r['scheduler_restored']:
                r['needs_scheduler_recovery'] = True
        except Exception as exc:
            r.update(state='capture_failed', error=str(exc), needs_scheduler_recovery=True)
            raise
        finally:
            save(directory / 'pass.json', r)
            if recovery.pending(recovery.state_path(p['satellite'], p['start'])):
                r['state'] = 'reboot_recovery_pending'
                save(directory / 'pass.json', r)
                event('capture_reboot_pending', id=p['id'], message='METEOR reservation retained across reboot')
            else:
                update_pass(p['id'], status='attempted')
            event('capture_finished', id=p['id'], state=r['state'])


def recover():
    """ExecStopPost and boot recovery restore only our interrupted capture ownership."""
    for path in records():
        r = read(path)
        if r.get('owner') != 'meteor-auto-v1':
            continue
        if recovery.pending(recovery.state_path(r['pass']['satellite'], r['pass']['start'])):
            continue  # Do not restart RF work or finalize a live reboot reservation.
        if r['state'] != 'capturing' and not r.get('needs_scheduler_recovery'):
            continue
        if satellite_busy():
            raise RuntimeError('Another satellite owner is active; recovery deferred')
        # The old recorder normally restores the scheduler itself; repair SIGTERM/reboot gaps.
        command(['systemctl', 'start', SCHEDULER])
        metadata = Path(r['capture_metadata'])
        m = read(metadata) if metadata.exists() else {}
        iq = Path(r['iq'])
        seconds = (dt(r['pass']['record_stop']) - dt(r['pass']['record_start'])).total_seconds()
        valid = m.get('status') == 'completed' and iq.exists() and iq.stat().st_size >= seconds * r['pass']['sample_rate'] and iq.stat().st_size % 2 == 0
        r.update(state='pending_decode' if valid else 'interrupted', recovered_at=now().isoformat(), capture=m,
                 needs_scheduler_recovery=False, capture_finished_at=now().isoformat(),
                 captured_iq_bytes=iq.stat().st_size if iq.exists() else 0)
        if iq.exists():
            r['iq_fingerprint'] = fingerprint(iq)
        save(path, r)
        event('capture_recovered', id=r['pass']['id'], state=r['state'])


def decode_argv(c, p, iq, output):
    if p['satellite'] not in ('M2-3', 'M2-4'):
        raise ValueError('Unsupported METEOR satellite')
    rate = p['sample_rate']
    if type(rate) is not int or not 1 <= rate <= 10000000:
        raise ValueError('Invalid recording sample rate')
    # Required options are explicit argv entries, never a JSON option blob.
    extra = [s.replace('{satellite_number}', p['satellite']) for s in c['satdump_extra']]
    if '--satellite_number' in extra:
        i = extra.index('--satellite_number')
        del extra[i:i+2]
    return c['satdump_command'] + c['satdump_prefix'] + [meteor_store.PIPELINE, 'baseband', str(iq), str(output),
           '--samplerate', str(rate), '--baseband_format', 'cu8', '--satellite_number', p['satellite']] + extra



def decoder_ready(c):
    if not shutil.which(c['satdump_command'][0]):
        return False
    if len(c['satdump_command']) > 1 and Path(c['satdump_command'][1]).name == 'satdump_evk.py':
        try:
            if not Path(c['satdump_command'][1]).is_file():
                return False
            manifest = read(ROOT / 'data/meteor-native-runtime.json')
            actual = command(['docker', 'image', 'inspect', manifest['image_tag'], '--format', '{{.Id}}'])
            return actual == manifest['image_id']
        except (OSError, ValueError, subprocess.SubprocessError):
            return False
    return True


def decode_once(c, path, iq_override=None, output_override=None, frequency_shift=None):
    r = read(path)
    if r.get('state') in ('capturing', 'external_decoding', 'reboot_recovery_pending'):
        raise RuntimeError('Active pass owner; decode deferred')
    r.pop('selected_decode_output', None)
    iq = Path(iq_override or r['iq'])
    attempt = len(r.get('decode_attempts', [])) + 1
    output = Path(output_override) if output_override else Path(path).parent / ('decode-' + str(attempt))
    if output.exists():
        raise RuntimeError('Decode output already exists; never overwrite')
    output.mkdir(parents=True)
    a = dict(command=[], output=str(output), started_at=now().isoformat())
    r.setdefault('decode_attempts', []).append(a)
    r['state'] = 'decoding'
    save(path, r)
    try:
        if not iq.is_file() or iq.stat().st_size <= 0 or iq.stat().st_size % 2:
            raise ValueError('Missing or invalid IQ; preserving record')
        if not decoder_ready(c):
            raise RuntimeError('Decoder unavailable or runtime image identity invalid')
        metadata = read(r['capture_metadata']) if r.get('capture_metadata') and Path(r['capture_metadata']).is_file() else r.get('capture', {})
        r['capture'] = metadata
        decode_pass = dict(r['pass'])
        if 'sample_rate_sps' not in metadata:
            raise ValueError('Recording JSON sample_rate_sps is required')
        decode_pass['sample_rate'] = metadata['sample_rate_sps']
        if metadata.get('satellite', decode_pass['satellite']) != decode_pass['satellite']:
            raise ValueError('Recording satellite mismatch')
        argv = decode_argv(c, decode_pass, iq, output)
        if frequency_shift is not None:
            if '--freq_shift' in argv:
                raise ValueError('Conflicting configured frequency shift')
            argv += ['--freq_shift', str(int(frequency_shift))]
        a['frequency_shift_hz'] = frequency_shift or 0
        a['command'] = argv
        save(path, r)
        with (output / 'satdump.log').open('wb') as stream:
            a['returncode'] = subprocess.run(argv, stdout=stream, stderr=subprocess.STDOUT,
                                             timeout=c['decode_timeout_seconds']).returncode
    except (OSError, ValueError, RuntimeError, subprocess.TimeoutExpired) as exc:
        r.update(state='decode_failed')
        a['error'] = str(exc)
    finally:
        a['finished_at'] = now().isoformat()
        a['metrics'] = meteor_store.inspect_output(output, a.get('returncode'), a.get('error'))
        a['products'] = [im['path'] for im in a['metrics']['images']]
        r['classification'] = a['metrics']['classification']
        r['state'] = {'SUCCESS':'decoded_products', 'PARTIAL_SUCCESS':'decoded_with_satdump_crash', 'SIGNAL/UNUSABLE':'decoded_no_products', 'EMPTY/FAILED':'decode_failed'}[r['classification']]
        save(path, r)
        meteor_store.persist(r, a, ROOT / 'data/watchkeeper-meteor.db')
        event('decode_finished', id=r['pass']['id'], state=r['state'])


def decode(c, path, iq_override=None, output_override=None):
    started = time.monotonic()
    decode_once(c, path, iq_override, output_override)
    # Explicit imported/override experiments must not certify the managed original.
    if iq_override or output_override:
        return
    try:
        evaluate_frequency(c, path, started)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        r = read(path)
        r['frequency_evaluation'] = dict(completed=False, error=str(exc), finished_at=now().isoformat(), verification=None)
        r['retention'] = meteor_retention.classify(r, c)
        save(path, r)
        meteor_retention.sync_db(ROOT, r)
        event('frequency_evaluation_unverified', id=r['pass']['id'], error=str(exc))


def evaluate_frequency(c, path, started=None):
    """Nominal first, then at most two spectrum-ranked shifts. Negative is unverified."""
    started = started or time.monotonic()
    r = read(path)
    if r.get('state') in ('capturing', 'external_decoding', 'reboot_recovery_pending'):
        raise RuntimeError('Pass is actively owned; cannot search')
    attempts = r.get('decode_attempts', [])
    if not attempts:
        raise ValueError('A normal decode is required before frequency evaluation')
    iq = Path(r['iq'])
    if not iq.is_file() or r.get('iq_fingerprint') != fingerprint(iq):
        raise ValueError('Raw recording changed or missing; cannot certify evaluation')
    f = dict(dict(span_hz=60000, windows=24, max_candidates=2, budget_seconds=300), **c.get('frequency_evaluation', {}))
    evaluation = dict(method='nominal_then_spectrum_ranked_v1', completed=False,
                      started_at=now().isoformat(), input_fingerprint=fingerprint(iq), span_hz=f['span_hz'],
                      negative_result_verified=False, verification=None, trials=[])
    # Do not repeat a useful decode that crashed: preserve diagnostics and indefinite retention.
    trial_outputs = [attempts[-1]['output']]
    best = attempts[-1]
    try:
        if best.get('returncode') != 0 or best.get('error') or best.get('metrics', {}).get('error'):
            raise ValueError('Nominal processing failed; preserve IQ and normal bounded retry behavior')
        if not meteor_frequency.useful(best['metrics']):
            r['state'] = 'frequency_searching'
            r['frequency_evaluation'] = evaluation
            save(path, r)
            rate = r.get('capture', {}).get('sample_rate_sps')
            if type(rate) is not int:
                raise ValueError('Recorded sample rate is required for offset survey')
            evaluation['survey'] = meteor_frequency.survey(iq, rate, f['span_hz'], f['windows'], f['max_candidates'])
            for carrier in evaluation['survey']['candidate_carrier_offsets_hz']:
                remaining = f['budget_seconds'] - (time.monotonic() - started)
                if remaining < 35:
                    evaluation['error'] = 'Bounded search budget exhausted; retained'
                    break
                cc = dict(c, decode_timeout_seconds=min(c['decode_timeout_seconds'], int(remaining)))
                decode_once(cc, path, frequency_shift=-carrier)
                r = read(path)
                trial = r['decode_attempts'][-1]
                trial_outputs.append(trial['output'])
                if meteor_frequency.rank(trial) > meteor_frequency.rank(best):
                    best = trial
                if meteor_frequency.useful(trial['metrics']):
                    break
                r['state'] = 'frequency_searching'
                save(path, r)
        r = read(path)
        if fingerprint(iq) != evaluation['input_fingerprint']:
            raise ValueError('IQ changed during evaluation')
        trials = [a for a in r['decode_attempts'] if a['output'] in trial_outputs]
        evaluation['trials'] = [dict(output=a['output'], shift_hz=a.get('frequency_shift_hz', 0),
                                    returncode=a.get('returncode'), error=a.get('error'),
                                    classification=a['metrics']['classification']) for a in trials]
        clean = all(meteor_frequency.trial_clean(a) for a in trials)
        evaluation['procedure_completed'] = bool(clean and not evaluation.get('error') and (meteor_frequency.useful(best['metrics']) or len(trials) == 1 + len(evaluation.get('survey', {}).get('candidate_carrier_offsets_hz', []))))
        evaluation['decoder_identity'] = meteor_frequency.decoder_identity(c)
        evaluation['configuration'] = meteor_frequency.procedure_config(c)
        evaluation.update(best_output=best['output'], best_shift_hz=best.get('frequency_shift_hz', 0),
                          best_carrier_offset_hz=-best.get('frequency_shift_hz', 0),
                          completed=bool(clean and meteor_frequency.useful(best['metrics'])),
                          verification='validated_channel_product' if clean and meteor_frequency.useful(best['metrics']) else None)
        # Keep real chronological attempt history. The selected result is separate.
        r['selected_decode_output'] = best['output']
        r['classification'] = best['metrics']['classification']
        r['state'] = {'SUCCESS':'decoded_products', 'PARTIAL_SUCCESS':'decoded_with_satdump_crash', 'SIGNAL/UNUSABLE':'decoded_no_products', 'EMPTY/FAILED':'decode_failed'}[r['classification']]
    except Exception as exc:
        evaluation['error'] = str(exc)
        r = read(path)
        r['state'] = 'decode_failed'
    finally:
        evaluation['finished_at'] = now().isoformat()
        if not evaluation['completed']:
            evaluation['limitation'] = 'Bounded supported search is not proof of absent signal; retention considers grace, procedure completion, errors and protection separately'
        r['frequency_evaluation'] = evaluation
        r['retention'] = meteor_retention.classify(r, c)
        save(path, r)
        meteor_store.persist(r, best, ROOT / 'data/watchkeeper-meteor.db')
        meteor_retention.sync_db(ROOT, r)
        event('frequency_evaluation_finished', id=r['pass']['id'], completed=evaluation['completed'], best_shift_hz=evaluation.get('best_shift_hz'))


def process(c):
    with lock('processing'):
        if satellite_busy() or active(CAPTURE_SERVICE):
            return
        for path in records():
            r = read(path)
            if r['state'] == 'decoding':
                r.update(state='decode_failed', error='worker interrupted; preserve attempt output')
                save(path, r)
            attempts = r.get('decode_attempts', [])
            if r['state'] not in ('pending_decode', 'decode_failed') or len(attempts) >= c['max_decode_attempts']:
                continue
            if attempts and now() - dt(attempts[-1]['finished_at'] if 'finished_at' in attempts[-1] else attempts[-1]['started_at']) < timedelta(seconds=c['decode_retry_seconds']):
                continue
            decode(c, path)
            return  # One bounded decode per timer invocation.


def cleanup(c, apply=False):
    print(json.dumps(meteor_retention.cleanup(ROOT, c, apply), indent=2))


def status(c):
    result = dict(enabled=c['enabled'], cleanup_enabled=c['cleanup_enabled'],
                  decoder_available=decoder_ready(c),
                  disk_free_gib=round(shutil.disk_usage(ROOT).free / 1024**3, 1), plan=plans(),
                  records=[dict(id=read(p)['pass']['id'], state=read(p)['state']) for p in records()])
    print(json.dumps(result, indent=2))


def worker_list(c, dry=False):
    with lock('processing'):
        eligible = []
        for path in records():
            r = read(path)
            if r.get('state') == 'external_decoding' and now() > dt(r['worker_lease']['expires_at']):
                r['state'] = 'pending_decode'
                if not dry:
                    save(path, r)
                    event('worker_lease_expired', id=r['pass']['id'])
            attempts = r.get('decode_attempts', [])
            if r.get('owner') == 'meteor-auto-v1' and r['state'] in ('pending_decode', 'decode_failed') and len(attempts) < c['max_decode_attempts']:
                if attempts and now() - dt(attempts[-1].get('finished_at', attempts[-1]['started_at'])) < timedelta(seconds=c['decode_retry_seconds']):
                    continue
                eligible.append(dict(id=r['pass']['id'], record=str(path), iq=r['iq'], bytes=r['captured_iq_bytes']))
        print(json.dumps(eligible))


def worker_claim(pid):
    if not re.fullmatch(r'm2[34]-\d{8}T\d{6}Z', pid):
        raise ValueError('Invalid pipeline pass ID')
    with lock('processing'):
        path = STATE / 'passes' / pid / 'pass.json'
        r = read(path)
        if r['state'] not in ('pending_decode', 'decode_failed') or r.get('owner') != 'meteor-auto-v1':
            raise RuntimeError('Pass already claimed or not eligible')
        token = uuid.uuid4().hex
        r.update(state='external_decoding', worker_lease=dict(token=token, expires_at=(now() + timedelta(hours=4)).isoformat()))
        save(path, r)
        print(json.dumps(r))


def worker_result(receipt):
    receipt = Path(receipt)
    if receipt.is_symlink() or receipt.resolve().parent != (STATE / 'incoming').resolve():
        raise ValueError('Receipt must be in pipeline incoming directory')
    result = read(receipt)
    pid = result['pass']['id']
    if not re.fullmatch(r'm2[34]-\d{8}T\d{6}Z', pid):
        raise ValueError('Invalid pass ID')
    with lock('processing'):
        path = STATE / 'passes' / pid / 'pass.json'
        r = read(path)
        token = r.get('worker_lease', {}).get('token')
        if r['state'] != 'external_decoding' or not token or result['worker_lease']['token'] != token or now() > dt(r['worker_lease']['expires_at']):
            raise RuntimeError('Worker lease mismatch or expired')
        if result['state'] not in ('decoded_products', 'decoded_with_satdump_crash', 'decoded_no_products', 'decode_failed'):
            raise RuntimeError('Invalid decoder result')
        if result['captured_iq_bytes'] != r['captured_iq_bytes'] or result['pass'] != r['pass']:
            raise RuntimeError('Capture identity changed')
        if len(result['decode_attempts']) != len(r.get('decode_attempts', [])) + 1:
            raise RuntimeError('Unexpected attempt history')
        last = result['decode_attempts'][-1]
        output = path.parent / ('dell-' + token)
        if not output.is_dir() or output.is_symlink():
            raise RuntimeError('Decoder artifacts have not been returned')
        last['output'] = str(output)
        last['products'] = [str(f) for f in output.rglob('*') if f.is_file() and f.suffix.lower() in ('.png', '.jpg', '.jpeg', '.tif', '.tiff') and f.stat().st_size > 0]
        last['finished_at'] = now().isoformat()
        last['metrics'] = meteor_store.inspect_output(output, last.get('returncode'), last.get('error'))
        last['products'] = [im['path'] for im in last['metrics']['images']]
        classification = last['metrics']['classification']
        state = {'SUCCESS':'decoded_products', 'PARTIAL_SUCCESS':'decoded_with_satdump_crash', 'SIGNAL/UNUSABLE':'decoded_no_products', 'EMPTY/FAILED':'decode_failed'}[classification]
        r.update(state=state, classification=classification, decode_attempts=result['decode_attempts'], worker_finished_at=now().isoformat())
        meteor_store.persist(r, last, ROOT / 'data/watchkeeper-meteor.db')
        save(path, r)
        event('worker_result_accepted', id=pid, state=r['state'])
    receipt.unlink()


def main():
    global ROOT, STATE
    parser = argparse.ArgumentParser(description='Conservative unattended METEOR milestone 1')
    parser.add_argument('--root', type=Path, default=ROOT)
    parser.add_argument('--config', type=Path)
    parser.add_argument('command', choices=['plan', 'dispatch', 'capture', 'recover', 'process', 'decode', 'frequency-search', 'pin', 'unpin', 'retention-refresh', 'cleanup', 'maintenance', 'status', 'worker-list', 'worker-claim', 'worker-result'])
    parser.add_argument('--dry-run', action='store_true')
    parser.add_argument('--apply', action='store_true')
    parser.add_argument('--record', type=Path)
    parser.add_argument('--iq', type=Path)
    parser.add_argument('--output', type=Path)
    parser.add_argument('--id')
    args = parser.parse_args()
    ROOT = args.root.resolve()
    STATE = ROOT / 'data/meteor-auto'
    try:
        c = config(args.config or ROOT / 'meteor-config.json')
        if args.dry_run and args.command not in ('plan', 'worker-list', 'cleanup'):
            raise ValueError('--dry-run is supported only for plan and worker-list; use status or cleanup for inspection')
        if args.apply and args.command != 'cleanup':
            raise ValueError('--apply is supported only for cleanup')
        if args.apply and args.dry_run:
            raise ValueError('--apply and --dry-run are mutually exclusive')
        if args.command == 'plan':
            plan(c, args.dry_run)
        elif args.command == 'cleanup':
            cleanup(c, args.apply)
        elif args.command == 'maintenance':
            meteor_retention.refresh(ROOT, c)
            cleanup(c, c['cleanup_enabled'] and meteor_retention.settings(c)['automatic_deletion_validated'])
        elif args.command in ('pin', 'unpin'):
            print(json.dumps(meteor_retention.pin(ROOT, c, args.id or '', args.command == 'pin')))
        elif args.command == 'retention-refresh':
            meteor_retention.refresh(ROOT, c)
        elif args.command == 'frequency-search':
            if not args.record:
                raise ValueError('--record is required')
            with lock('processing'):
                evaluate_frequency(c, args.record)
        elif args.command == 'worker-list':
            worker_list(c, args.dry_run)
        elif args.command == 'worker-claim':
            worker_claim(args.id or '')
        elif args.command == 'worker-result':
            if not args.record:
                raise ValueError('--record is required')
            worker_result(args.record)
        elif args.command == 'decode':
            if not args.record:
                raise ValueError('--record is required')
            with lock('processing'):
                decode(c, args.record, args.iq, args.output)
        else:
            globals()[args.command](c) if args.command != 'recover' else recover()
        return 0
    except BlockingIOError:
        print('Another pipeline operation owns the lock; deferred', file=sys.stderr)
        return 0
    except Exception as exc:
        print('METEOR pipeline: ' + str(exc), file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
