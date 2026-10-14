"""Daily Tower/ATIS audio expiry with permanent references and metadata preserved."""
import argparse
from contextlib import contextmanager
from datetime import datetime, timezone
import fcntl
import json
from pathlib import Path
import re
import shutil
import time
import os
from functools import wraps

RETENTION_DAYS = {'tower': 14, 'atis': 7}
DAYS = RETENTION_DAYS['tower']
SECONDS = DAYS * 86400
CAPTURE_ID = re.compile(r'\d{8}T\d{6}\.\d{6}Z')

@contextmanager
def lock(root):
    with (Path(root)/'.tower-retention.lock').open('a') as handle:
        fcntl.flock(handle, fcntl.LOCK_EX)
        yield

def protected(folder):
    folder = Path(folder)
    # ATIS-only bounded review holds use the existing protection gate.
    if folder.parent.name == 'atis':
        try:
            marker=json.loads((folder/'atis-validation-hold.json').read_text())
            if marker.get('until',0)>time.time(): return True
        except (OSError,ValueError,AttributeError,TypeError): pass
    if folder.is_symlink() or any(x in folder.parts for x in ('asr-reference-corpus', 'evaluation', 'aviation-fixtures')):
        return True
    if any((folder/name).exists() for name in ('tower-pin.json','keep','KEEP','.keep','protected.json','reference.json')):
        return True
    try:
        capture = json.loads((folder/'capture.json').read_text())
        return capture.get('source') != 'live' or any(capture.get(k) for k in ('pinned','keep','protected','reference','permanent_reference','reference_sample'))
    except (OSError, ValueError, AttributeError, TypeError):
        return True

def audio_job(function):
    """Serialize a real processing call with expiration, without persistent holds."""
    @wraps(function)
    def wrapped(folder, *args, **kwargs):
        if Path(folder).parent.name != 'atis' and protected(folder):
            return function(folder, *args, **kwargs)
        with folder_lock(Path(folder), blocking=True):
            return function(folder, *args, **kwargs)
    return wrapped

@contextmanager
def folder_lock(folder, blocking=False):
    with (folder/'.audio-processing.lock').open('a') as handle:
        fcntl.flock(handle, fcntl.LOCK_EX | (0 if blocking else fcntl.LOCK_NB))
        yield

def active_paths():
    """Take a fail-closed snapshot of open files and command arguments."""
    found=[]
    for proc in Path('/proc').iterdir():
        if not proc.name.isdigit() or int(proc.name)==os.getpid(): continue
        try:
            found.append((proc/'cmdline').read_bytes().replace(b'\0',b' ').decode(errors='replace'))
            for fd in (proc/'fd').iterdir():
                try: found.append(os.readlink(str(fd)))
                except FileNotFoundError: pass
        except FileNotFoundError: pass  # Process exited during snapshot.
    return found

def expire(base, now=None, apply=False):
    base=Path(base)
    category=base.name
    days=RETENTION_DAYS.get(category)
    result=dict(category=category,retention_days=days,eligible=0,protected=0,
                deleted=0,errors=0,bytes_freed=0,would_free_bytes=0,removed=[],error_details=[],fatal=False)
    if not days or base.parent.name!='recordings' or base.is_symlink():
        result['errors']+=1;result['fatal']=True;return result
    if not base.exists(): return result
    now=time.time() if now is None else now
    root=base.parent.parent
    try:
        with lock(root):
            users=active_paths()
            for folder in sorted(base.iterdir()):
                if not folder.is_dir(): continue
                try:
                    if folder.is_symlink() or not CAPTURE_ID.fullmatch(folder.name):
                        result['protected']+=1;continue
                    if not any(folder.glob('*.wav')): continue
                    capture=json.loads((folder/'capture.json').read_text())
                    if not isinstance(capture,dict):raise ValueError('Capture metadata must be an object')
                    # Timestamped UTC capture ID is the original recording clock.
                    captured=datetime.strptime(folder.name,'%Y%m%dT%H%M%S.%fZ').replace(tzinfo=timezone.utc).timestamp()
                    if capture.get('kind')!=category or capture.get('source')!='live':
                        result['protected']+=1;continue
                    # Review/validation queue state and terminal failures are not holds.
                    permanent=any((folder/n).exists() for n in ('tower-pin.json','keep','KEEP','.keep','protected.json','reference.json','atis-human-reference.json')) or any(capture.get(k) for k in ('pinned','keep','protected','reference','permanent_reference','reference_sample'))
                    if permanent or any(str(folder) in item for item in users):
                        result['protected']+=1;continue
                    if now-captured < days*86400: continue
                    with folder_lock(folder):
                        # Recheck readers after taking the processing exclusion lock.
                        if any(str(folder) in item for item in active_paths()):
                            result['protected']+=1;continue
                        paths=list(folder.glob('*.wav'))
                        if any(p.is_symlink() or not p.is_file() for p in paths):
                            result['errors']+=1;continue
                        sizes={p:p.stat().st_size for p in paths}
                        result['eligible']+=len(paths)
                        result['would_free_bytes']+=sum(sizes.values())
                        if apply:
                            for path,size in sizes.items():
                                path.unlink();result['removed'].append(str(path))
                                result['deleted']+=1;result['bytes_freed']+=size
                            if paths:
                                (folder/'tower-retention-policy.json').write_text(json.dumps(dict(status='audio_retention_expired',retention_days=days,metadata_retained=True,expired_at=now),indent=2)+'\n')
                except BlockingIOError: result['protected']+=1
                except (OSError,ValueError,TypeError) as error:
                    result['errors']+=1
                    result['error_details'].append(dict(capture_id=folder.name,error=type(error).__name__,retained=True))
    except (OSError,ValueError) as error:
        result['errors']+=1;result['fatal']=True
        result['error_details'].append(dict(error=type(error).__name__,retained=True))
    return result

def cleanup(base, now=None):
    # Compatibility API; daily service owns production scheduling.
    return expire(base,now=now,apply=True)['removed'] if Path(base).name=='tower' else []

def pin(root, selection):
    root=Path(root).resolve()
    selection=Path(selection)
    folder=selection if selection.is_absolute() else root/'recordings/tower'/selection
    if folder.is_file(): folder=folder.parent
    folder=folder.resolve()
    base=root/'recordings/tower'
    if folder.parent != base or not CAPTURE_ID.fullmatch(folder.name):
        raise ValueError('Select a Tower capture ID or its original file path')
    with lock(root):
        capture=json.loads((folder/'capture.json').read_text())
        if capture.get('kind') != 'tower': raise ValueError('Not a Tower capture')
        if not any((folder/n).is_file() and not (folder/n).is_symlink() for n in ('raw.wav','listen.wav')):
            raise FileNotFoundError('No original audio remains to pin')
        target=root/'asr-reference-corpus'/('TOWER-PIN-'+folder.name)
        target.mkdir(parents=True,exist_ok=True)
        marker={'permanent_reference':True,'original_directory':str(folder),'reference_directory':str(target)}
        # Protect source before copying; partial copies cannot expose source to cleanup.
        (folder/'tower-pin.json').write_text(json.dumps(marker,indent=2)+'\n')
        for source in folder.iterdir():
            if source.is_file() and not source.is_symlink():
                dest=target/source.name
                if dest.exists():
                    if dest.read_bytes()!=source.read_bytes(): raise ValueError('Existing reference differs: '+str(dest))
                else: shutil.copy2(source,dest)
        (target/'reference.json').write_text(json.dumps(marker,indent=2)+'\n')
        return target

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action',choices=['pin','cleanup','daily'])
    parser.add_argument('selection',nargs='?')
    parser.add_argument('--dry-run',action='store_true')
    args=parser.parse_args()
    root=Path(__file__).resolve().parent
    if args.action=='pin':
        if not args.selection: parser.error('pin requires a capture ID or audio path')
        print(pin(root,args.selection))
    else:
        categories=('tower','atis') if args.action=='daily' else ('tower',)
        results=[expire(root/'recordings'/c,apply=not args.dry_run) for c in categories]
        print(json.dumps(results,indent=2))
        raise SystemExit(1 if any(r['fatal'] for r in results) else 0)
