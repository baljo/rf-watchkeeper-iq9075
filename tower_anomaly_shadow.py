"""Opt-in, fail-closed post-capture shadow worker; no production pipeline edits.

Only completed Tower raw audio is read. Separate diagnostics never influence
retention, transcription, RF selection, shared accelerator leases or scheduling.
"""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import wave
from datetime import datetime, timezone


def review_metadata(result, processing):
    """Separate review evidence; never a production speech decision."""
    state = processing.get('status')
    eligible = state in ('no_activity', 'failed', 'uncertain', 'probably_non_voice', 'voice_candidate')
    return dict(anomaly_candidate=bool(eligible and result['summary']['p100'] > result['threshold']),
                production_status=state, review_state='unreviewed',
                severity_band=__import__('tower_anomaly_review').severity(result['summary']['p100'], result['threshold']),
                median_score=result['summary'].get('p50'),
                score=result['summary']['p100'], threshold=result['threshold'],
                shadow_only=True, affects_retention=False, affects_transcription=False,
                limitation='Score measures difference from learned background. Exceeding threshold does not imply voice.')


def process_is_busy(argv):
    # Match executable identities, never incidental daemon arguments such as --asr.
    names = ('rtl_sdr', 'rtl_fm', 'satdump', 'whisper', 'genie', 'asr', 'ais_rx', 'rtl_ais', 'VoiceAI', 'voice-ai-ref')
    parts = [p.decode(errors='replace') if isinstance(p, bytes) else p for p in argv if p]
    if not parts: return False
    executable = Path(parts[0]).name
    if executable.startswith('python') and len(parts) > 1:
        executable = Path(parts[1]).name
    return any(executable == name or executable.startswith(name+'-') for name in names)


def lock_is_held(path, table='/proc/locks'):
    """Read the kernel lock table; owner.json can outlive a released lease."""
    path = Path(path)
    if not path.exists(): return False
    stat = path.stat()
    expected = (os.major(stat.st_dev), os.minor(stat.st_dev), stat.st_ino)
    for line in Path(table).read_text().splitlines():
        for token in line.split():
            if token.count(':') != 2: continue
            try:
                major, minor, inode = token.split(':')
                identity = (int(major,16), int(minor,16), int(inode))
            except ValueError:
                continue
            if identity == expected: return True
    return False


def waiter_is_alive(owner):
    try:
        pid = int(owner['pid'])
        start = Path('/proc/%d/stat' % pid).read_text().rsplit(')',1)[1].split()[19]
        boot = Path('/proc/sys/kernel/random/boot_id').read_text().strip()
        return start == owner.get('start') and boot == owner.get('boot')
    except (OSError, ValueError, KeyError, TypeError):
        return False


def busy_reason():
    try:
        import atis_pipeline
        reason = atis_pipeline.satellite_reason(15, margin=300)
        if reason:
            return reason
        resource = Path(atis_pipeline.ROOT)/'data/inference'
        if lock_is_held(resource/'htp.lock'):
            return 'Shared inference kernel lease active'
        for marker in resource.glob('wait-*.json'):
            if marker.exists() and waiter_is_alive(json.loads(marker.read_text())):
                return 'Production inference waiter active'
        # Read-only process guard supplements satellite reservations. No RF probes.
        for proc in Path('/proc').glob('[0-9]*/cmdline'):
            if proc.parent.name == str(os.getpid()):
                continue
            try:
                argv = proc.read_bytes().split(b'\0')
            except FileNotFoundError:
                continue
            if process_is_busy(argv):
                return 'RF/inference process busy'
    except Exception as error:
        return 'Unable to verify idle resources: ' + type(error).__name__
    return None


def state_path(output, folder):
    return Path(output)/'failures'/(folder.name+'.json')


def read_state(output, folder):
    path = state_path(output, folder)
    if not path.exists(): return {}
    # Unreadable state must fail closed, never reset the retry budget.
    try:
        state = json.loads(path.read_text())
        if not isinstance(state, dict): raise ValueError('Invalid state object')
        return state
    except (OSError, ValueError):
        return dict(status='failed_terminal', reason='unreadable_failure_state')


def save_state(output, folder, status, reason, attempts=0, next_retry=0, detail=None):
    path = state_path(output, folder)
    path.parent.mkdir(parents=True, exist_ok=True)
    record = dict(id=folder.name, status=status, reason=reason, attempts=attempts,
                  next_retry_at=next_retry, updated_at=datetime.now(timezone.utc).isoformat(),
                  original_audio=str(folder/'raw.wav'), originals_preserved=True,
                  affects_retention=False, affects_transcription=False, detail=detail)
    tmp = path.with_suffix('.tmp')
    tmp.write_text(json.dumps(record, indent=2)+'\n')
    tmp.replace(path)
    return record


def pending(root, output):
    base = Path(root)/'recordings/tower'
    if base.is_symlink() or not base.exists(): return []
    selected = []
    # Oldest first: new arrivals cannot starve the backlog.
    for folder in sorted(base.iterdir()):
        if folder.is_symlink() or not folder.is_dir(): continue
        processing_path = folder/'processed.json'
        if not processing_path.is_file(): processing_path = folder/'tower-classification.json'
        if not processing_path.is_file(): continue
        try:
            if not json.loads(processing_path.read_text()).get('status'): continue
        except (OSError, ValueError): continue
        if (Path(output)/(folder.name+'.json')).exists(): continue
        if read_state(output, folder).get('status') in ('unscorable', 'failed_terminal'): continue
        selected.append(folder)
    return selected


def audio_reason(path):
    if path.is_symlink(): return 'unsafe_audio_symlink'
    try:
        size = path.stat().st_size
        if size == 0: return 'empty_audio'
        if size > 5_000_000: return 'audio_size_limit'
        with wave.open(str(path), 'rb') as audio:
            frames, channels, width, rate = (audio.getnframes(), audio.getnchannels(),
                                           audio.getsampwidth(), audio.getframerate())
            if frames == 0: return 'zero_frames'
            if width != 2 or rate not in (8000, 16000): return 'unsupported_audio_format'
            if len(audio.readframes(frames)) != frames*channels*width: return 'corrupt_audio'
            if frames < rate: return 'too_short_audio'
    except FileNotFoundError: return 'missing_audio'
    except (wave.Error, EOFError, ValueError): return 'corrupt_audio'
    return None


def reclassify(root, output):
    skipped = []
    for folder in pending(root, output):
        try: reason = audio_reason(folder/'raw.wav')
        except OSError: continue  # permission/I/O failures are transient
        if reason:
            save_state(output, folder, 'unscorable', reason)
            skipped.append(dict(id=folder.name, reason=reason))
    return skipped


def retry_failure(output, folder, reason, detail=None):
    if reason == 'resource_preempted':
        # Shared-resource contention is not evidence that audio is unscorable.
        state = read_state(output, folder)
        save_state(output, folder, 'retry_wait', reason, state.get('attempts', 0),
                   time.time()+60, detail)
        return dict(status='retry_scheduled', id=folder.name, reason=reason)
    attempts = read_state(output, folder).get('attempts', 0) + 1
    terminal = attempts >= 5
    save_state(output, folder, 'failed_terminal' if terminal else 'retry_wait',
               'retry_exhausted' if terminal else reason, attempts,
               0 if terminal else time.time()+min(3600, 60*2**(attempts-1)),
               detail=dict(last_reason=reason, error=detail))
    return dict(status='failed_terminal' if terminal else 'retry_scheduled',
                id=folder.name, reason=reason, attempts=attempts)


def run_once(root, model, output, guard=busy_reason, timeout=15):
    root, output = Path(root).resolve(), Path(output).resolve()
    if output == root or root/'recordings' == output or root/'recordings' in output.parents:
        raise ValueError('Shadow output must be separate from recordings')
    reason = guard()
    if reason: return {'status':'deferred_busy','reason':reason}
    candidates = pending(root,output)
    if not candidates: return {'status':'no_pending_audio'}
    candidates = [f for f in candidates if read_state(output, f).get('next_retry_at', 0) <= time.time()]
    if not candidates: return {'status':'retry_backoff'}
    folder = candidates[0]
    try: invalid = audio_reason(folder/'raw.wav')
    except OSError as error: return retry_failure(output, folder, 'audio_io_error', str(error))
    if invalid:
        save_state(output, folder, 'unscorable', invalid)
        return {'status':'unscorable', 'id':folder.name, 'reason':invalid}
    output.mkdir(parents=True,exist_ok=True)
    target = output/(folder.name+'.json')
    temporary = target.with_suffix('.pending')
    try:
        child = subprocess.Popen([sys.executable,str(Path(__file__).resolve()),'--score-child',
                              '--audio',str(folder/'raw.wav'),'--model',str(model),'--output',str(temporary)],
                             stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,
                             env=dict(os.environ,OPENBLAS_NUM_THREADS='1',OMP_NUM_THREADS='1'))
    except OSError as error:
        return retry_failure(output, folder, 'child_start_error', str(error))
    started = time.monotonic()
    try:
        while child.poll() is None:
            reason = guard()
            if time.monotonic()-started>timeout or reason:
                child.terminate()
                try: child.wait(timeout=2)
                except subprocess.TimeoutExpired: child.kill(); child.wait(timeout=2)
                return retry_failure(output, folder, 'resource_preempted' if reason else 'inference_timeout', reason)
            time.sleep(0.25)
        if child.returncode: return retry_failure(output, folder, 'inference_error', 'child exit %s' % child.returncode)
        result = json.loads(temporary.read_text())
        processing_path = folder/'processed.json'
        if not processing_path.is_file(): processing_path = folder/'tower-classification.json'
        result['review'] = review_metadata(result, json.loads(processing_path.read_text()))
        temporary.write_text(json.dumps(result, indent=2)+'\n')
        temporary.replace(target)
        state_path(output, folder).unlink(missing_ok=True)
        return {'status':'scored','id':folder.name}
    except (OSError, ValueError, KeyError, TypeError) as error:
        return retry_failure(output, folder, 'inference_error', str(error))
    finally:
        if child.poll() is None: child.kill(); child.wait(timeout=2)
        temporary.unlink(missing_ok=True)


def run_batch(root, model, output, guard=busy_reason, max_seconds=45, max_recordings=5,
              runner=run_once, clock=time.monotonic):
    """Bounded idle batch; each recording retains run_once's resource guards."""
    if runner is run_once:
        root, output = Path(root).resolve(), Path(output).resolve()
        if output == root or root/'recordings' == output or root/'recordings' in output.parents:
            raise ValueError('Shadow output must be separate from recordings')
    started = clock()
    scored = []
    failures = []
    reclassified = reclassify(root, output) if runner is run_once else []
    attempted = 0
    result = {'status': 'batch_limit'}
    while attempted < max_recordings:
        remaining = max_seconds - (clock() - started)
        if remaining <= 0:
            result = {'status': 'batch_time_limit'}
            break
        result = runner(root, model, output, guard=guard, timeout=min(15, remaining))
        if result.get('status') in ('unscorable', 'retry_scheduled', 'failed_terminal'):
            failures.append(result)
            attempted += 1
            continue
        if result.get('status') != 'scored':
            break
        attempted += 1
        scored.append(result['id'])
    return {'status': 'batch_complete', 'scored_count': len(scored),
            'ids': scored, 'reclassified_count': len(reclassified), 'reclassified': reclassified,
            'failures': failures, 'stop_reason': result['status'] if attempted < max_recordings else 'batch_limit',
            'elapsed_seconds': round(clock() - started, 3)}


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root')
    parser.add_argument('--audio')
    parser.add_argument('--model',required=True)
    parser.add_argument('--output',required=True)
    parser.add_argument('--score-child',action='store_true')
    parser.add_argument('--batch', action='store_true')
    args=parser.parse_args()
    if args.score_child:
        from tower_anomaly import score_file, read_json, save_json
        result=score_file(args.audio,read_json(args.model))
        result['model_sha256']=__import__('hashlib').sha256(Path(args.model).read_bytes()).hexdigest()
        save_json(args.output,result)
    else:
        if not args.root: parser.error('--root required')
        run = run_batch if args.batch else run_once
        import fcntl
        Path(args.output).mkdir(parents=True, exist_ok=True)
        with (Path(args.output)/'.worker.lock').open('a') as lock:
            try: fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                print(json.dumps(dict(status='deferred_busy', reason='Worker already running')))
            else:
                print(json.dumps(run(args.root,args.model,args.output)))
