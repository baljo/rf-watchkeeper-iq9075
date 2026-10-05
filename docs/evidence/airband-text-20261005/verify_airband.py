"""Read-only deployment/service/API evidence for this Airband workstream."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess
import urllib.request
import atis_pipeline as pipeline

root=Path('/root/rf-watchkeeper')
pipeline.ROOT=root
pipeline.rf_health.ROOT=root
stage=root/'airband-text-stage-20261005'
protected=['jobs-v4.jsonc','job_manager.py','satellite_capture.py','satellite_planner.py',
           'satellite_schedule.py','satellite_v4_preflight.sh','data/meteor-auto/plan.json']
services=['rf-watchkeeper-scheduler.service','rf-watchkeeper-atis-process.service',
          'rf-watchkeeper-dashboard.service']
result={'checked_at':datetime.now(timezone.utc).isoformat(),
        'boot_id':Path('/proc/sys/kernel/random/boot_id').read_text().strip(),
        'protected_hashes':{name:hashlib.sha256((root/name).read_bytes()).hexdigest() for name in protected},
        'services':{name:subprocess.check_output(['systemctl','show',name,'-p','MainPID','-p','ActiveState','-p','Result'],text=True).strip() for name in services}}
if __import__('sys').argv[-1]=='--before':
    pipeline.save(stage/'before.json',result)
else:
    before=json.loads((stage/'before.json').read_text())
    result['protected_unchanged']=result['protected_hashes']==before['protected_hashes']
    result['boot_unchanged']=result['boot_id']==before['boot_id']
    result['scheduler_unchanged']=result['services'][services[0]]==before['services'][services[0]]
    for path in ['/api/atis','/api/atis/audio']:
        try:
            with urllib.request.urlopen('http://127.0.0.1:8080'+path,timeout=10) as response:
                data=response.read()
                result[path]={'status':response.status,'bytes':len(data)}
                if path=='/api/atis':result[path]['body']=json.loads(data)
        except Exception as error:result[path]={'error':str(error)}
    # Use operational module in final verification (stage shadow avoided by caller).
    result['satellite_guard']=pipeline.satellite_reason(240)
    pipeline.save(stage/'verification.json',result)
print(json.dumps(result,indent=2))
