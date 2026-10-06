from pathlib import Path
import hashlib,io,json,sqlite3,subprocess,time,urllib.request,wave
root=Path('/root/rf-watchkeeper');stage=root/'adaptive-stage-20261006'
p=stage/'live-validation.json';r=json.loads(p.read_text());r['initial_api_attempt']=r.pop('api');r['initial_api_attempt_note']='Verifier used wrong port 8765; configured dashboard service uses 8080. Corrected read-only checks follow.'
r['api']={}
for path in ('/','/api/state','/api/tower','/api/atis','/api/meteor'):
    with urllib.request.urlopen('http://127.0.0.1:8080'+path,timeout=10) as response:
        r['api'][path]=response.status
        body=response.read()
        if path=='/':r['dashboard_label_updated']=b'15 s probes about every minute' in body
        if path=='/api/tower':tower=json.loads(body)
rows=tower['recent_captures'];r['tower_recent_count']=len(rows)
row=next(x for x in rows if x.get('audio_url') and x['result']=='no_activity')
with urllib.request.urlopen('http://127.0.0.1:8080'+row['audio_url'],timeout=10) as response:
    with wave.open(io.BytesIO(response.read())) as wav:r['silent_audio_api']=dict(status=response.status,recording=row['recording'],rate=wav.getframerate(),channels=wav.getnchannels(),seconds=wav.getnframes()/wav.getframerate())
raw=(root/'dashboard.html').read_bytes();before=(root/'backups/adaptive-rf-20261006T155400Z/dashboard.html').read_bytes()
r['dashboard_only_label_changed']=raw.replace(b'15 s probes about every minute / activity hold up to 75 s',b'30 s every ~3 min')==before
r['hashes']={name:hashlib.sha256((root/name).read_bytes()).hexdigest() for name in r['hashes']}
r['final_scheduler_unit']=subprocess.check_output(['systemctl','show','rf-watchkeeper-scheduler','-p','NRestarts','-p','ActiveState'],text=True).splitlines()
r['final_metrics']=json.loads((root/'logs/adaptive-metrics.json').read_text())
r['receiver_health']=[]
with sqlite3.connect(root/'data/watchkeeper.db') as db:
    db.row_factory=sqlite3.Row
    r['receiver_health']=[dict(x) for x in db.execute("SELECT job_type,start_time,completion_time,capture_ok,evidence_value,evidence_kind,failure_reason FROM rf_health_jobs WHERE start_time>='2026-10-06T15:48:44' ORDER BY id")]
channels={'A':0,'B':0}
logs=subprocess.check_output(['journalctl','-u','rf-watchkeeper-scheduler','--since','2026-10-06 15:48:44 UTC','--no-pager','-o','cat'],text=True)
for line in logs.splitlines():
    try:
        channel=json.loads(line).get('channel')
        if channel in channels:channels[channel]+=1
    except ValueError:pass
r['received_ais_channels']=channels
r['final_checked_at']=time.time()
p.write_text(json.dumps(r,indent=2))
print(json.dumps({k:r[k] for k in ('api','tower_recent_count','silent_audio_api','dashboard_only_label_changed','final_scheduler_unit','received_ais_channels')},indent=2))
