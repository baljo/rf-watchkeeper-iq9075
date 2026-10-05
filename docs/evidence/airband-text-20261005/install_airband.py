"""Airband-only guarded install; no scheduler or satellite mutations."""
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import difflib

stage=Path(__file__).resolve().parent
root=stage.parent
expected=json.loads((stage/'expected-original.json').read_text())
for name, digest in expected.items():
    assert hashlib.sha256((root/name).read_bytes()).hexdigest()==digest, 'Concurrent edit: '+name
names=['airband_text.py','atis_pipeline.py','atis_view.py']
backup=root/'backups'/('airband-text-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ'))
backup.mkdir()
patch=[]
for name in names:
    dest=root/name
    old=dest.read_text() if dest.exists() else ''
    if dest.exists():shutil.copy2(dest,backup/name)
    new=(stage/name).read_text()
    patch.extend(difflib.unified_diff(old.splitlines(True),new.splitlines(True),fromfile='a/'+name,tofile='b/'+name))
    temp=root/(name+'.airband.tmp')
    shutil.copy2(stage/name,temp)
    os.chmod(temp,dest.stat().st_mode if dest.exists() else 0o600)
    os.replace(temp,dest)
evidence=root/'docs/evidence/airband-text-20261005'
evidence.mkdir(exist_ok=True)
(evidence/'airband-text.patch').write_text(''.join(patch))
for name in ['tests.txt','test_airband_text.py','test_atis_pipeline.py','replay-segmentation.json','replay-model-result.json','replay_airband.py','install_airband.py']:
    if (stage/name).exists():shutil.copy2(stage/name,evidence/name)
for unit in ['rf-watchkeeper-atis-process.service','rf-watchkeeper-dashboard.service']:
    subprocess.run(['systemctl','restart',unit],check=True,timeout=30)
report={'installed_at':datetime.now(timezone.utc).isoformat(),'backup':str(backup),
        'runtime_files':names,'restarted_services':['rf-watchkeeper-atis-process.service','rf-watchkeeper-dashboard.service'],
        'scheduler_restarted':False,'rebooted':False,
        'hashes':{name:hashlib.sha256((root/name).read_bytes()).hexdigest() for name in names}}
(evidence/'install.json').write_text(json.dumps(report,indent=2))
print(json.dumps(report,indent=2))
