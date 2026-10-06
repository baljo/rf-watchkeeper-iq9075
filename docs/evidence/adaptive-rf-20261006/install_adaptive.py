from pathlib import Path
import json, shutil, subprocess, time
root=Path('/root/rf-watchkeeper');stage=root/'adaptive-stage-20261006'
import sys
sys.path.insert(0,str(root))
import atis_pipeline
reason=atis_pipeline.satellite_reason(100,margin=0)
if reason: raise SystemExit('Deployment deferred: '+reason)
backup=root/'backups'/('adaptive-rf-'+time.strftime('%Y%m%dT%H%M%SZ',time.gmtime()));backup.mkdir(parents=True)
for name in ('job_manager.py','atis_pipeline.py','jobs-v4.jsonc'):
    shutil.copy2(root/name,backup/name)
config=json.loads((root/'jobs-v4.jsonc').read_text())
config['adaptive_hopping']=True
for job in config['jobs']:
    if job.get('tower_recording'):job.update(dwell_seconds=15,interval_seconds=60,adaptive_tower=True,quiet_seconds=10,max_listen_seconds=75,activity_rms=40)
    if job['mode']=='ais':job['dwell_seconds']=45
subprocess.run(['systemctl','stop','rf-watchkeeper-scheduler.service'],check=True)
for name in ('adaptive_rf.py','job_manager.py','atis_pipeline.py','test_adaptive_rf.py'):
    shutil.copy2(stage/name,root/name)
(root/'jobs-v4.jsonc').write_text(json.dumps(config,indent=2)+'\n')
subprocess.run(['python3','-m','py_compile',str(root/'job_manager.py'),str(root/'atis_pipeline.py'),str(root/'adaptive_rf.py')],check=True)
subprocess.run(['systemctl','start','rf-watchkeeper-scheduler.service'],check=True)
subprocess.run(['systemctl','restart','rf-watchkeeper-atis-process.service'],check=True)
print(json.dumps(dict(backup=str(backup),deployed_at=time.time())))
