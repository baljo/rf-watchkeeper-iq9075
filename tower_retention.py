"""Tower development retention and permanent reference pinning."""
import argparse
from contextlib import contextmanager
from datetime import datetime, timezone
import fcntl
import json
from pathlib import Path
import re
import shutil
import time

DAYS = 30
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
        except (OSError,ValueError): pass
    if folder.is_symlink() or any(x in folder.parts for x in ('asr-reference-corpus', 'evaluation', 'aviation-fixtures')):
        return True
    if any((folder/name).exists() for name in ('tower-pin.json','keep','KEEP','.keep','protected.json','reference.json')):
        return True
    try:
        capture = json.loads((folder/'capture.json').read_text())
        return capture.get('source') != 'live' or any(capture.get(k) for k in ('pinned','keep','protected','reference','permanent_reference','reference_sample'))
    except (OSError, ValueError):
        return True

def cleanup(base, now=None):
    base = Path(base)
    # This cleanup never accepts another channel or a reference tree.
    if base.name != 'tower' or base.parent.name != 'recordings' or base.is_symlink():
        return []
    root = base.parent.parent
    removed=[]
    now=time.time() if now is None else now
    with lock(root):
        for folder in sorted(base.iterdir()):
            if not folder.is_dir() or not CAPTURE_ID.fullmatch(folder.name) or protected(folder):
                continue
            try:
                capture=json.loads((folder/'capture.json').read_text())
                processed=json.loads((folder/'processed.json').read_text())
                if capture.get('kind') != 'tower' or not processed.get('status'):
                    continue
                captured=datetime.strptime(folder.name,'%Y%m%dT%H%M%S.%fZ').replace(tzinfo=timezone.utc).timestamp()
                if now-captured < SECONDS:
                    continue
                for name in ('raw.wav','listen.wav'):
                    path=folder/name
                    if path.is_file() and not path.is_symlink():
                        path.unlink()
                        removed.append(str(path))
                # Separate policy audit: preserve all existing classifier/retention metadata.
                (folder/'tower-retention-policy.json').write_text(json.dumps({'status':'development_retention_expired','retention_days':DAYS,'metadata_retained':True},indent=2)+'\n')
            except (OSError, ValueError):
                continue
    return removed

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
    parser.add_argument('action',choices=['pin','cleanup'])
    parser.add_argument('selection',nargs='?')
    args=parser.parse_args()
    root=Path(__file__).resolve().parent
    if args.action=='pin':
        if not args.selection: parser.error('pin requires a capture ID or audio path')
        print(pin(root,args.selection))
    else: print(json.dumps(cleanup(root/'recordings/tower')))
