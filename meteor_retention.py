"""Authoritative managed-pass retention. Raw IQ only; images are never removed."""
import contextlib
from datetime import datetime, timedelta, timezone
import fcntl
import json
import math
import os
from pathlib import Path
import re
import shutil
import sqlite3

UTC = timezone.utc
ACTIVE = {'capturing', 'decoding', 'external_decoding', 'frequency_searching', 'reboot_recovery_pending'}
CLASSES = {'processing_failed', 'unverified', 'no_signal', 'poor', 'useful', 'excellent', 'pinned'}

def instant(value):
    if not isinstance(value, str):
        raise ValueError('Timestamp is missing or invalid')
    t = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if t.tzinfo is None:
        raise ValueError('Timezone required')
    return t.astimezone(UTC)

def settings(c):
    v = c.get('retention', {})
    defaults = dict(no_signal_hours=24, poor_hours=48, useful_hours=168,
                    normal_free_gib=20, critical_free_gib=10, useful_min_lines=128,
                    excellent_min_lines=2000, automatic_deletion_validated=False)
    v = dict(defaults, **v)
    for name in ('no_signal_hours', 'poor_hours', 'useful_hours', 'normal_free_gib', 'critical_free_gib', 'useful_min_lines', 'excellent_min_lines'):
        if type(v[name]) not in (int, float) or not math.isfinite(v[name]) or v[name] <= 0:
            raise ValueError('Invalid retention setting: ' + name)
    if v['no_signal_hours'] < 24 or v['poor_hours'] < 48 or v['useful_hours'] < 168:
        raise ValueError('Retention grace periods cannot be shortened below conservative minimums')
    if v['normal_free_gib'] <= v['critical_free_gib'] or type(v['automatic_deletion_validated']) is not bool:
        raise ValueError('Invalid disk thresholds or deletion validation flag')
    return v

def fingerprint(path):
    s = path.stat()
    return dict(device=s.st_dev, inode=s.st_ino, bytes=s.st_size, modified_ns=s.st_mtime_ns)

def atomic(path, value):
    path = Path(path)
    temporary = path.with_name(path.name + '.retention-tmp')
    with temporary.open('w') as stream:
        json.dump(value, stream, indent=2)
        stream.write('\n')
        stream.flush()
        os.fsync(stream.fileno())
    temporary.replace(path)
    fd = os.open(str(path.parent), os.O_DIRECTORY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)

@contextlib.contextmanager
def locks(root):
    state = Path(root) / 'data/meteor-auto'
    state.mkdir(parents=True, exist_ok=True)
    with contextlib.ExitStack() as stack:
        # Same global locks used by capture, processing and external-worker claims.
        for name in ('capture', 'processing', 'retention'):
            stream = stack.enter_context((state / (name + '.lock')).open('a'))
            fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        yield

def classify(r, c, at=None):
    """Disposition is independent of deletion gates and decoder result labels."""
    at = at or datetime.now(UTC)
    v = settings(c)
    iq = Path(r['iq'])
    raw = iq.is_file() and not iq.is_symlink()
    size = iq.stat().st_size if raw else 0
    m = r.get('capture', {})
    attempts = r.get('decode_attempts', [])
    a = next((a for a in attempts if a.get('output') == r.get('selected_decode_output')), attempts[-1] if attempts else {})
    metrics = a.get('metrics', {})
    images = [im for t in attempts for im in t.get('metrics', {}).get('images', [])]
    useful = [im for im in images if re.fullmatch(r'MSU-MR-[1-6]', im.get('product', ''))
              and im.get('width', 0) >= 256 and im.get('height', 0) >= v['useful_min_lines']]
    useful_count = len({im.get('path', im.get('product')) for im in useful})
    lines = max(metrics.get('channel_lines', {}).values(), default=0)
    # SIGNAL/UNUSABLE can mean only positive noise SNR with NOSYNC. Actual
    # synchronization/partial products are ambiguous; the label alone is not.
    ambiguous_signal = any(re.search(r'(?:Viterbi|Deframer)\s*:\s*(?:SYNC|SYNCED|LOCKED)\b', status, re.I)
                           for t in attempts for status in t.get('metrics', {}).get('decoder_activity', []))
    try:
        expected = (instant(r['pass']['record_stop']) - instant(r['pass']['record_start'])).total_seconds() * m.get('sample_rate_sps', r['pass'].get('sample_rate', 0)) * 2
        captured_at = instant(m.get('actual_stop') or r['pass']['record_stop'])
    except (KeyError, TypeError, ValueError):
        expected, captured_at = 0, None
    valid = raw and size > 0 and size % 2 == 0 and size == r.get('captured_iq_bytes') and expected > 0 and size >= expected * .95
    unchanged = raw and r.get('iq_fingerprint') == fingerprint(iq)
    capture_ok = m.get('status') == 'completed' and r.get('capture_returncode', m.get('rtl_sdr_returncode', 0)) == 0
    evaluation = r.get('frequency_evaluation', {})
    recorded_frequency = m.get('frequency_hz', r['pass'].get('frequency'))
    from meteor_frequency import trial_clean, procedure_complete
    clean = trial_clean(a)
    verified = (evaluation.get('completed') is True and evaluation.get('input_fingerprint') == r.get('iq_fingerprint')
                and evaluation.get('best_output') == a.get('output') and not evaluation.get('error')
                and evaluation.get('verification') in ('validated_channel_product', 'exhaustive_verified_search'))
    searched = procedure_complete(r, c)
    retention_class = 'useful' if useful else 'poor' if lines or metrics.get('images') or ambiguous_signal else 'no_signal'
    deadline = (captured_at + timedelta(hours=v['poor_hours'] if retention_class == 'poor' else v['no_signal_hours'])).isoformat() if captured_at else None
    disposition, reason = 'REVIEW', 'Supported current frequency-offset procedure has not completed'
    explicit = bool(r.get('pinned') is True or r.get('explicit_protection') or r.get('reference') or r.get('regression')
                    or m.get('reference') is True or m.get('regression') is True or str(m.get('source', '')).startswith('imported'))
    if explicit or useful or r.get('historical_useful_images'):
        disposition = 'PROTECTED'
        retention_class = 'pinned' if explicit else 'excellent' if lines >= v['excellent_min_lines'] else 'useful'
        reason = r.get('explicit_protection') or ('Explicit reference/regression/Keep protection' if explicit else 'Useful channel products preserved, including historical/crash outputs')
        deadline = None
    elif r.get('state') in ACTIVE:
        disposition, reason = 'PROTECTED', 'Capture/decoder/search/worker currently owns this pass'
    elif deadline and at < instant(deadline):
        disposition, reason = 'GRACE', 'Finite capture-completion grace period has not expired'
    elif not raw:
        reason = 'Raw IQ missing or symlink; metadata retained'
    elif iq.parent.name != 'satellite' or iq.suffix != '.cu8' or r.get('owner') not in ('meteor-auto-v1', 'meteor-retention-legacy-v1'):
        reason = 'Raw location or ownership is outside the supported retention scope'
    elif not captured_at or not unchanged or (size and not valid):
        reason = 'Incomplete capture metadata, invalid size, or changed IQ fingerprint'
    elif r.get('review_reason'):
        reason = r['review_reason']
    elif c.get('frequency') is not None and type(recorded_frequency) not in (int, float):
        reason = 'Recorded center-frequency metadata is missing or invalid'
    elif c.get('frequency') is not None and abs(recorded_frequency - c['frequency']) > c.get('frequency_evaluation', {}).get('span_hz', 60000):
        reason = 'Recorded center frequency is outside the supported offset-search span; unusual frequency needs review'
    elif size == 0 and m.get('status') == 'failed_no_iq':
        disposition, reason = 'DELETABLE', 'Expired failed capture contains zero IQ samples; history retained'
        retention_class = 'processing_failed'
    elif size == 0:
        reason = 'Zero-byte IQ lacks explicit failed_no_iq capture evidence'
    elif not capture_ok:
        retention_class, reason = 'processing_failed', 'Capture error or incomplete capture needs review'
    elif not attempts:
        reason = 'No current decoding/frequency-offset evaluation evidence'
    elif not clean or evaluation.get('error') or any(t.get('returncode') != 0 or t.get('error') for t in evaluation.get('trials', [])):
        details = '; '.join(str(x) for x in (
            'selected returncode=' + str(a.get('returncode')) if a.get('returncode') != 0 else None,
            a.get('error'), metrics.get('error'), evaluation.get('error'),
            'Missing completion stages or unrecognized decoder error' if not clean and a.get('returncode') == 0 and not a.get('error') else None) if x)
        retention_class, reason = 'processing_failed', 'Decoder error or interrupted offset search needs review' + (': ' + details if details else '')
    elif not searched:
        reason = 'Supported current frequency-offset procedure has not completed'
    elif lines or metrics.get('images') or ambiguous_signal:
        reason = 'Partial channel/image or synchronized decoder evidence below useful threshold needs review'
    else:
        disposition, reason = 'DELETABLE', 'Capture grace expired; supported current nominal and offset procedure produced no useful images'
    deleted = r.get('retention', {}).get('deletion')
    if deleted:
        retention_class, reason = deleted['classification'], deleted['reason']
        disposition = 'PROTECTED'
        deadline = r['retention'].get('deadline')
    return dict(schema_version=2, retention_class=retention_class, disposition=disposition, reason=reason,
                deadline=deadline, grace_anchor='capture_completion', age_days=(at-captured_at).total_seconds()/86400 if captured_at else None,
                pinned=r.get('pinned') is True, explicitly_protected=explicit, raw_exists=raw,
                raw_valid=valid, raw_unchanged=unchanged, raw_bytes=size,
                capture_completed=capture_ok, capture_failed=not capture_ok,
                decode_completed_cleanly=clean, decode_failed=bool(a) and not clean,
                useful_image_count=useful_count, result_classification=metrics.get('classification'),
                frequency_evaluation_completed=verified, supported_procedure_completed=searched,
                frequency_evaluation=evaluation, raw_deleted=bool(deleted), deletion=deleted, checked_at=at.isoformat(),
                eligible=bool(not deleted and disposition == 'DELETABLE' and r.get('owner') in ('meteor-auto-v1', 'meteor-retention-legacy-v1')))

def inventory_records(root, c):
    """Include all raw captures; absence of management is not reference protection."""
    root = Path(root)
    records, seen = [], set()
    manifest = root / 'data/meteor-auto/retention-protected.json'
    protected = json.loads(manifest.read_text()) if manifest.exists() else {}
    history, useful_ids = [], set()
    db = root / 'data/watchkeeper-meteor.db'
    if db.exists():
        with contextlib.closing(sqlite3.connect(str(db))) as conn:
            history = [(pid, json.loads(meta)) for pid, meta in conn.execute('SELECT pass_id, metadata FROM meteor_passes')]
            useful_ids = {pid for pid, product, width, height in conn.execute('SELECT pass_id, product, width, height FROM meteor_images')
                          if re.fullmatch(r'MSU-MR-[1-6]', product or '') and (width or 0) >= 256 and (height or 0) >= settings(c)['useful_min_lines']}
    for path in sorted((root / 'data/meteor-auto/passes').glob('*/pass.json')):
        r = json.loads(path.read_text())
        reviewed = root / 'data/meteor-auto/retention-review' / Path(r['iq']).stem / 'pass.json'
        if reviewed.exists() and r.get('state') not in ACTIVE:
            evidence = json.loads(reviewed.read_text())
            evidence['decode_attempts'] = r.get('decode_attempts', []) + [a for a in evidence.get('decode_attempts', []) if a.get('output') not in {t.get('output') for t in r.get('decode_attempts', [])}]
            evidence['pinned'] = r.get('pinned', False)
            evidence['original_managed_record'] = str(path)
            r, path = evidence, reviewed
        records.append((path, r))
        seen.add(r['iq'])
    for iq in sorted((root / 'recordings/satellite').glob('*.cu8')):
        if str(iq) in seen:
            continue
        path = root / 'data/meteor-auto/retention-review' / iq.stem / 'pass.json'
        if path.exists():
            r = json.loads(path.read_text())
        else:
            sidecar = iq.with_suffix('.json')
            m = json.loads(sidecar.read_text()) if sidecar.exists() else {}
            r = dict(owner='meteor-retention-legacy-v1', state='historical', iq=str(iq), capture=m,
                     capture_metadata=str(sidecar), captured_iq_bytes=m.get('iq_bytes'), iq_fingerprint=fingerprint(iq),
                     decode_attempts=[], pass_=dict(id='legacy-' + iq.stem, satellite=m.get('satellite'),
                     record_start=m.get('record_start'), record_stop=m.get('record_stop'), sample_rate=m.get('sample_rate_sps'), frequency=m.get('frequency_hz')))
            r['pass'] = r.pop('pass_')
        records.append((path, r))
    included = {str(path) for path, _ in records}
    for path in sorted((root / 'data/meteor-auto/retention-review').glob('*/pass.json')):
        if str(path) in included:
            continue
        r = json.loads(path.read_text())
        if r.get('owner') == 'meteor-retention-legacy-v1' and not Path(r['iq']).exists():
            records.append((path, r))
    for path, r in records:
        name = Path(r['iq']).name
        if name in protected:
            r['explicit_protection'] = protected[name]
        matches = [meta for _, meta in history if r['iq'] in json.dumps(meta)]
        if any(meta.get('reference') is True or str(meta.get('source', '')).startswith('imported') for meta in matches):
            r.setdefault('explicit_protection', 'Imported/reference provenance in preserved database history')
        r['historical_useful_images'] = any(pid in useful_ids for pid, meta in history if r['iq'] in json.dumps(meta))
        r['historical_useful_images'] = bool(r.get('historical_useful_images')) or any(any(re.fullmatch(r'MSU-MR-[1-6]', im.get('product', '')) and im.get('width', 0) >= 256 and im.get('height', 0) >= settings(c)['useful_min_lines'] for im in meta.get('images', [])) for meta in matches)
    return records

def sync_db(root, r):
    """Merge retention into existing JSON metadata; preserve history and images."""
    db = Path(root) / 'data/watchkeeper-meteor.db'
    if not db.exists():
        return
    with sqlite3.connect(str(db), timeout=10) as conn:
        row = conn.execute('SELECT metadata FROM meteor_passes WHERE pass_id=?', (r['pass']['id'],)).fetchone()
        if row:
            metadata = json.loads(row[0])
            metadata.update(retention=r['retention'], pinned=r.get('pinned', False),
                            frequency_evaluation=r.get('frequency_evaluation'))
            metadata['raw_iq_state'] = 'deleted' if r['retention']['raw_deleted'] else 'retained' if r['retention']['raw_exists'] else 'missing'
            conn.execute('UPDATE meteor_passes SET metadata=? WHERE pass_id=?', (json.dumps(metadata), r['pass']['id']))

def open_elsewhere(iq):
    """Fail closed on unreadable /proc. Includes container processes on host."""
    s = iq.stat()
    for proc in Path('/proc').glob('[0-9]*'):
        if proc.name == str(os.getpid()):
            continue
        try:
            handles = list((proc / 'fd').iterdir())
        except FileNotFoundError:
            continue
        except OSError:
            return True
        for handle in handles:
            try:
                f = handle.stat()
                if (f.st_dev, f.st_ino) == (s.st_dev, s.st_ino):
                    return True
            except FileNotFoundError:
                continue
            except PermissionError:
                return True
    return False

def audit(root, entry):
    p = Path(root) / 'data/meteor-auto/retention-events.jsonl'
    with p.open('a') as stream:
        stream.write(json.dumps(entry) + '\n')
        stream.flush()
        os.fsync(stream.fileno())

def cleanup(root, c, apply=False, free_gib=None):
    root = Path(root)
    v = settings(c)
    enabled = c.get('cleanup_enabled') is True and v['automatic_deletion_validated']
    if apply and not enabled:
        raise RuntimeError('Deletion remains disabled: cleanup_enabled and validated evaluation are both required')
    with locks(root):
        free = shutil.disk_usage(root).free / 1024**3 if free_gib is None else free_gib
        pressure = 'critical' if free < v['critical_free_gib'] else 'low' if free < v['normal_free_gib'] else 'normal'
        rows, candidates = [], []
        for path, r in inventory_records(root, c):
            try:
                state = classify(r, c)
                rows.append(dict(id=r['pass']['id'], iq=r['iq'], **state))
                if state['eligible']:
                    candidates.append((path, r, state))
                # Dry-run is strictly read-only, including metadata.
                if apply:
                    path.parent.mkdir(parents=True, exist_ok=True)
                    r['retention'] = state
                    atomic(path, r)
                    sync_db(root, r)
            except (OSError, ValueError, KeyError, TypeError) as exc:
                rows.append(dict(record=str(path), eligible=False, error=str(exc)))
        candidates.sort(key=lambda row: (0 if pressure == 'critical' and row[2]['retention_class'] in ('no_signal', 'poor') else 1,
                                         row[1]['pass'].get('record_start', '')))
        deleted = []
        for path, r, state in candidates:
            if not apply:
                continue
            iq = Path(r['iq'])
            allowed = root / 'recordings/satellite'
            if iq.is_symlink() or iq.resolve().parent != allowed.resolve() or iq.suffix != '.cu8':
                continue
            with iq.open('rb') as stream:
                try:
                    fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
                except BlockingIOError:
                    continue
                # Fresh metadata and inode checks under locks immediately before unlink.
                r = json.loads(path.read_text())
                state = classify(r, c)
                if not state['eligible'] or open_elsewhere(iq):
                    continue
                f = os.fstat(stream.fileno())
                if (f.st_dev, f.st_ino, f.st_size, f.st_mtime_ns) != (iq.stat().st_dev, iq.stat().st_ino, iq.stat().st_size, iq.stat().st_mtime_ns):
                    continue
                entry = dict(id=r['pass']['id'], raw_filename=str(iq), size=f.st_size,
                             classification=state['retention_class'], reason='normal grace period expired; disk=' + pressure,
                             timestamp=datetime.now(UTC).isoformat(), frequency_evaluation_completed=state['frequency_evaluation_completed'],
                             supported_procedure_completed=state['supported_procedure_completed'],
                             decode_result=state['result_classification'], image_count=state['useful_image_count'])
                # Persist intent first; if unlink fails it cannot masquerade as deletion.
                audit(root, dict(event='deletion_intent', **entry))
                iq.unlink()
                fd = os.open(str(iq.parent), os.O_DIRECTORY)
                try:
                    os.fsync(fd)
                finally:
                    os.close(fd)
                state.update(deletion=entry, raw_deleted=True, raw_exists=False, eligible=False)
                r['retention'] = state
                atomic(path, r)
                sync_db(root, r)
                audit(root, dict(event='raw_deleted', **entry))
                deleted.append(entry)
        return dict(cleanup_enabled=enabled, dry_run=not apply, disk_free_gib=free, disk_pressure=pressure,
                    warning='Disk critically low; protected recordings retained. New captures require reserve headroom.' if pressure == 'critical' else None,
                    would_delete=[dict(id=r['pass']['id'], iq=r['iq'], reason=s['reason'], deadline=s['deadline'], bytes=s['raw_bytes']) for _, r, s in candidates],
                    deleted=deleted, passes=rows,
                    reclaimable_bytes=sum(s['raw_bytes'] for _, _, s in candidates),
                    summary={label:dict(count=sum(x.get('disposition') == label and x.get('raw_exists') for x in rows),
                        bytes=sum(x.get('raw_bytes', 0) for x in rows if x.get('disposition') == label))
                        for label in ('PROTECTED', 'GRACE', 'DELETABLE', 'REVIEW')})

def refresh(root, c):
    with locks(root):
        for p, r in inventory_records(root, c):
            if r.get('state') in ACTIVE:
                continue
            r['retention'] = classify(r, c)
            p.parent.mkdir(parents=True, exist_ok=True)
            atomic(p, r)
            sync_db(root, r)

def pin(root, c, pid, keep):
    if not re.fullmatch(r'm2[34]-\d{8}T\d{6}Z', pid):
        raise ValueError('Managed METEOR pass ID required')
    with locks(root):
        p = Path(root) / 'data/meteor-auto/passes' / pid / 'pass.json'
        r = json.loads(p.read_text())
        r.update(pinned=keep, pin_changed_at=datetime.now(UTC).isoformat())
        r['retention'] = classify(r, c)
        atomic(p, r)
        sync_db(root, r)
        audit(root, dict(event='pin' if keep else 'unpin', id=pid, timestamp=r['pin_changed_at']))
        return r['retention']

def dashboard(root, c, history):
    by_id = {p['pass_id']: p for p in history}
    for path, r in inventory_records(root, c):
        p = r['pass']
        row = by_id.setdefault(p['id'], dict(pass_id=p['id'], satellite=p['satellite'],
            record_start=p.get('record_start'), sample_rate=p.get('sample_rate'), frequency=p.get('frequency'),
            classification=r.get('classification', r.get('state')), images=[], channel_lines={},
            source='historical_evk' if r.get('owner') == 'meteor-retention-legacy-v1' else 'automatic_evk',
            raw_iq_state='retained' if Path(r['iq']).is_file() else 'missing'))
        row.update(retention=classify(r, c), pinned=r.get('pinned', False), state=r.get('state'))
    free = shutil.disk_usage(root).free / 1024**3
    return dict(passes=sorted(by_id.values(), key=lambda p:p.get('record_start') or '', reverse=True),
                cleanup_enabled=c.get('cleanup_enabled', False) and settings(c)['automatic_deletion_validated'],
                disk_free_gib=round(free, 2), disk_warning=free < settings(c)['normal_free_gib'])
