from pathlib import Path
import hashlib,json,subprocess,time,urllib.request,wave
root=Path('/root/rf-watchkeeper');stage=root/'adaptive-stage-20261006';since=1791301724
samples=[];end=time.monotonic()+210
while time.monotonic()<end:
    rows=subprocess.check_output(['ps','-eo','comm'],text=True).splitlines()
    owners={name:rows.count(name) for name in ('rtl_fm','AIS-catcher','rtl_sdr')}
    samples.append(dict(at=time.time(),owners=owners))
    time.sleep(1)
events=[]
for line in (root/'logs/events.jsonl').read_text().splitlines():
    try:
        r=json.loads(line)
        if r.get('event_type')=='scheduler_state' and r.get('received_at','')>='2026-10-06T15:48:44':events.append(r)
    except ValueError:pass
captures={}
for kind in ('tower','atis'):
    rows=[]
    for p in sorted((root/'recordings'/kind).glob('*/capture.json')):
        if p.stat().st_mtime<since:continue
        r=json.loads(p.read_text());r.pop('receiver_command',None)
        r['recording']=p.parent.name
        if (p.parent/'processed.json').exists():r['processing']=json.loads((p.parent/'processed.json').read_text()).get('status')
        rows.append(r)
    captures[kind]=rows
api={}
for path in ('/','/api/state','/api/tower','/api/atis','/api/meteor'):
    try:
        with urllib.request.urlopen('http://127.0.0.1:8080'+path,timeout=5) as response:api[path]=response.status
    except Exception as e:api[path]=str(e)
services={name:subprocess.run(['systemctl','is-active',name],capture_output=True,text=True).stdout.strip() for name in ('rf-watchkeeper-scheduler','rf-watchkeeper-atis-process','rf-watchkeeper-dashboard','rf-watchkeeper-interpreter','rf-watchkeeper-health.timer')}
hashes={name:hashlib.sha256((root/name).read_bytes()).hexdigest() for name in ('dashboard.py','dashboard.html','atis_view.py','job_manager.py','atis_pipeline.py','adaptive_rf.py','jobs-v4.jsonc')}
report=dict(events=events,captures=captures,metrics=json.loads((root/'logs/adaptive-metrics.json').read_text()),api=api,services=services,hashes=hashes,process_observation=dict(samples=len(samples),collision_samples=sum(sum(x['owners'].values())>1 for x in samples),max_owners=max(sum(x['owners'].values()) for x in samples)))
(stage/'live-validation.json').write_text(json.dumps(report,indent=2))
print(json.dumps({k:v for k,v in report.items() if k not in ('events','captures','hashes')},indent=2))
