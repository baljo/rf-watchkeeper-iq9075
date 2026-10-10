"""Durable, bounded ATIS shadow queue. Never publishes production results."""
import argparse
import array
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import signal
import sqlite3
import subprocess
import threading
import time
import wave
import inference_resource as ir

ROOT=Path(__file__).resolve().parent
CANDIDATE=ROOT/'evaluation/atis-prompt-small-20261007'
VERSION='prompt-small-device1-cleanup-full80-shadow-v2'
RUNTIME=ROOT/'atis_runtime_device1.py'
MAX_ATTEMPTS=3
MAX_AGE=48*3600
TIMEOUT=180
FINAL=('completed','failed','skipped')

@contextmanager
def database(root=ROOT):
    base=Path(root)/'data/atis-shadow';base.mkdir(parents=True,exist_ok=True)
    db=sqlite3.connect(str(base/'jobs.sqlite3'),timeout=5)
    db.row_factory=sqlite3.Row
    db.execute('PRAGMA journal_mode=WAL');db.execute('PRAGMA synchronous=FULL')
    db.execute('''CREATE TABLE IF NOT EXISTS jobs (
      capture_id TEXT PRIMARY KEY, folder TEXT NOT NULL, state TEXT NOT NULL,
      attempts INTEGER NOT NULL DEFAULT 0, created REAL NOT NULL, updated REAL NOT NULL,
      next_try REAL NOT NULL DEFAULT 0, reason TEXT, result TEXT, child TEXT)''')
    try: yield db; db.commit()
    finally: db.close()

def read(path, default=None):
    try:return json.loads(Path(path).read_text())
    except (OSError,ValueError):return default

def digest(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as f:
        for b in iter(lambda:f.read(1024*1024),b''):h.update(b)
    return h.hexdigest()

def envelope(folder):
    folder=Path(folder);cid=folder.name
    source=folder/('audio.wav' if cid=='ATIS-REF-001' else 'raw.wav')
    transcript=read(folder/'transcript.json',{})
    reference=read(folder/'reference.json',{})
    timestamp=reference.get('capture_timestamp_utc')
    if not timestamp:
        try:timestamp=datetime.strptime(cid,'%Y%m%dT%H%M%S.%fZ').replace(tzinfo=timezone.utc).isoformat()
        except ValueError:timestamp=None
    return {'capture_id':cid,'capture_timestamp':timestamp,'audio_path':str(source),
        'audio_sha256':digest(source) if source.exists() else None,
        'production_raw_transcript':' '.join((x.get('raw') or {}).get('text',x.get('text','')) for x in transcript.get('segments',[])),
        'production_normalized_transcript':[x.get('normalization') for x in transcript.get('segments',[])],
        'production_runtime_seconds':transcript.get('asr_runtime_seconds'),
        'shadow_raw_transcript':None,'shadow_normalized_transcript':None,'shadow_runtime_seconds':None,
        'candidate_version':VERSION,'configuration':{'prompt':'legacy','beam':1,'preparation':'full80'},
        'execution_evidence':None,'runtime_requested':'HTP; /usr/lib QNN; execution unverified until completion'}

def enqueue(folder, root=ROOT):
    folder=Path(folder)
    cap=read(folder/'capture.json',{})
    if folder.parent != Path(root)/'recordings/atis' or cap.get('status')!='ready':return
    stamp=time.time()
    suitable=3<=cap.get('audio_seconds',90)<=300
    with database(root) as db:
        existing=db.execute('SELECT result FROM jobs WHERE capture_id=?',(folder.name,)).fetchone()
        if existing and existing['result'] is not None:return
        db.execute('INSERT OR IGNORE INTO jobs(capture_id,folder,state,created,updated) VALUES (?,?,?,?,?)',
                   (folder.name,str(folder),'pending' if suitable else 'skipped',stamp,stamp))
        if not suitable:db.execute("UPDATE jobs SET reason='Outside eligible 3–300 second duration' WHERE capture_id=? AND state='skipped'",(folder.name,))
        row=db.execute('SELECT state,reason FROM jobs WHERE capture_id=?',(folder.name,)).fetchone()
        meta=envelope(folder);meta.update(state=row['state'],reason=row['reason'])
        db.execute('UPDATE jobs SET result=? WHERE capture_id=? AND result IS NULL',(json.dumps(meta),folder.name))

def discover(root=ROOT):
    base=Path(root)/'recordings/atis'
    if not base.exists():return
    for folder in base.iterdir():
        if folder.is_dir() and (folder/'processed.json').exists() and (folder/'raw.wav').exists():enqueue(folder,root)

def retention_hold(folder, root=ROOT):
    """Only bounded eligible jobs hold existing silence cleanup; pins stay separate."""
    with database(root) as db:
        row=db.execute('SELECT state,created FROM jobs WHERE capture_id=?',(Path(folder).name,)).fetchone()
        return bool(row and row['state'] not in FINAL and time.time()-row['created']<MAX_AGE)

def update(cid,state,reason=None,result=None,root=ROOT,next_try=0,child=None):
    with database(root) as db:
        previous=db.execute('SELECT folder,result FROM jobs WHERE capture_id=?',(cid,)).fetchone()
        meta=json.loads(previous['result']) if previous and previous['result'] else envelope(previous['folder']) if previous else {}
        if result is not None:meta.update(result)
        meta.update(state=state,reason=reason)
        db.execute('UPDATE jobs SET state=?,updated=?,next_try=?,reason=?,result=COALESCE(?,result),child=? WHERE capture_id=?',
            (state,time.time(),next_try,reason,json.dumps(meta),json.dumps(child) if child else None,cid))
    print('ATIS SHADOW '+cid+' '+state+': '+str(reason or ''),flush=True)

def release_silence_retention(root=ROOT):
    """Finish the existing no-activity rule only after shadow is terminal.

    No general ATIS expiry is invented. Pinned captures are always protected.
    """
    import tower_retention
    with database(root) as db:rows=list(db.execute("SELECT folder FROM jobs WHERE state IN ('completed','failed','skipped')"))
    for row in rows:
        folder=Path(row['folder'])
        if folder.parent!=Path(root)/'recordings/atis' or tower_retention.protected(folder):continue
        if read(folder/'processed.json',{}).get('status')!='no_activity':continue
        if read(folder/'audio-retention.json',{}).get('status')=='silence_removed':continue
        for name in ('raw.wav','listen.wav'):(folder/name).unlink(missing_ok=True)
        ir.atomic(folder/'audio-retention.json',{'status':'silence_removed','metadata_retained':True,'shadow_terminal':True})

def stop_child(proc):
    if proc.poll() is not None:return
    try:os.killpg(proc.pid,signal.SIGTERM)
    except ProcessLookupError:pass
    try:proc.wait(timeout=3)
    except subprocess.TimeoutExpired:
        try:os.killpg(proc.pid,signal.SIGKILL)
        except ProcessLookupError:pass
        proc.wait(timeout=3)

def recover(root=ROOT):
    with database(root) as db:rows=list(db.execute("SELECT * FROM jobs WHERE state='running'"))
    for row in rows:
        child=json.loads(row['child']) if row['child'] else None
        if ir.alive(child):
            try:os.killpg(child['pid'],signal.SIGTERM)
            except ProcessLookupError:pass
        state='failed' if row['attempts']>=MAX_ATTEMPTS else 'deferred'
        update(row['capture_id'],state,'Worker restart; retry original WAV',root=root,next_try=time.time()+30)

def priority_reason(root=ROOT):
    import atis_pipeline as ap
    reason=ap.satellite_reason(TIMEOUT,margin=300)
    if reason:return reason
    if ir.production_waiting(root):return 'Production inference waiting'
    for base in ('atis',):
        for folder in (Path(root)/'recordings'/base).glob('*'):
            if read(folder/'capture.json',{}).get('status')=='ready' and not (folder/'processed.json').exists():
                if not ap.tower_retention.protected(folder):return 'Pending production capture'
    busy=subprocess.check_output(['ps','-eo','comm'],text=True).splitlines()
    if any(x in busy for x in ('voice-ai-ref','genie-t2t-run')):return 'Production inference active'
    commands=subprocess.check_output(['ps','-eo','args'],text=True).splitlines()
    if any('rtl_fm' in x and '-M am' in x for x in commands):return 'Airband capture active'
    return None

def admission_reason():
    # Promote the validated ordinary AIS-window admission rule into automation.
    # This gate applies before launch only; running inference keeps existing preemption.
    uptime=float(Path('/proc/uptime').read_text().split()[0]);hz=os.sysconf('SC_CLK_TCK');ages=[]
    for comm in Path('/proc').glob('[0-9]*/comm'):
        try:
            if comm.read_text().strip()=='AIS-catcher':
                start_tick=int((comm.parent/'stat').read_text().rsplit(')',1)[1].split()[19]);ages.append(uptime-start_tick/hz)
        except (OSError,ValueError):pass
    return None if ages and min(ages)<=18 else 'Awaiting start of ordinary AIS window'

def prepare(source, target):
    # Exact validated full80 recipe, read-only original; only derived clips written.
    with wave.open(str(source)) as w:
        if (w.getnchannels(),w.getsampwidth(),w.getframerate())!=(1,2,8000):raise ValueError('Expected mono PCM16 8 kHz')
        samples=array.array('h',w.readframes(w.getnframes()))
    if not samples:raise ValueError('Empty WAV')
    alpha=math.exp(-2*math.pi*80/8000);prev=last=0.;hp=[]
    for v in samples:
        last=alpha*(last+v-prev);prev=v;hp.append(round(max(-32768,min(32767,last))))
    gain=min(50,29000/max(abs(v) for v in hp)) if any(hp) else 1
    hp=[round(v*gain) for v in hp]
    for offset in range(0,len(hp),224000):
        chunk=hp[offset:offset+224000];b=array.array('h')
        for i,v in enumerate(chunk):b.extend((v,(v+chunk[min(i+1,len(chunk)-1)])//2))
        if len(b)<48000:b.extend([0]*(48000-len(b)))
        with wave.open(str(target/('clip-%06d.wav'%(offset//8))),'wb') as w:
            w.setparams((1,2,16000,0,'NONE','not compressed'));w.writeframes(b.tobytes())

def evidence(record):
    rows=record.get('rows',[])
    if not rows or not all(x.get('eot_reached') for x in rows):raise RuntimeError('Incomplete decoder EOS')
    if not all(x>0 for x in record.get('encoder_accel_execute_us',[])) or not record.get('encoder_accel_execute_us'):
        raise RuntimeError('Missing encoder HTP execution evidence')
    if not record.get('decoder_accel_execute_us') or not all(x>0 for x in record['decoder_accel_execute_us']):
        raise RuntimeError('Missing decoder HTP execution evidence')
    if not any('/usr/lib/libQnnHtp.so' in x for x in record.get('mapped_libraries',[])):
        raise RuntimeError('Unexpected HTP runtime identity')

def attempt(row, stop, root=ROOT, guard=None, command_factory=None):
    cid=row['capture_id'];folder=Path(row['folder']);source=folder/('audio.wav' if cid=='ATIS-REF-001' else 'raw.wav')
    guard=guard or (lambda:priority_reason(root))
    reason=guard()
    if not reason and command_factory is None and Path(root)==ROOT:reason=admission_reason()
    if reason:
        update(cid,'deferred',reason,root=root,next_try=time.time()+30);return
    proc=None;started=None
    try:
        with ir.lease('shadow:'+cid,timeout=.5,production=False,root=root,cancel=stop.is_set) as fd:
            reason=guard()
            if reason:raise InterruptedError(reason)
            with database(root) as db:
                db.execute("UPDATE jobs SET state='running',attempts=attempts+1,updated=? WHERE capture_id=?",(time.time(),cid))
                count=db.execute('SELECT attempts FROM jobs WHERE capture_id=?',(cid,)).fetchone()[0]
            scratch=Path(root)/'data/atis-shadow/runs'/cid/str(count);scratch.mkdir(parents=True,exist_ok=True)
            source_hash=digest(source);prepare(source,scratch)
            output=scratch/'candidate'
            argv=command_factory(scratch,output) if command_factory else [str(CANDIDATE/'python/bin/python3'),str(RUNTIME),
                '--prompt','legacy','--beam','1','--input-dir',str(scratch),'--output-name',str(output)]
            env=dict(os.environ,HF_HOME=str(CANDIDATE/'hf-cache'),LD_LIBRARY_PATH='/usr/lib',RF_SHADOW_LEASE_FD=str(fd),OPENBLAS_NUM_THREADS='1',OMP_NUM_THREADS='1')
            started=time.monotonic()
            with (scratch/'runtime.log').open('wb') as log:
                proc=subprocess.Popen(argv,stdout=log,stderr=subprocess.STDOUT,env=env,start_new_session=True,pass_fds=(fd,))
                update(cid,'running',root=root,child=ir.identity(proc.pid))
                try:
                    while proc.poll() is None:
                        if stop.wait(.5):raise InterruptedError('Worker stopping')
                        reason=guard()
                        if reason:raise InterruptedError(reason)
                        if time.monotonic()-started>TIMEOUT:raise TimeoutError('Candidate timeout')
                    if proc.returncode:raise RuntimeError('Candidate exit '+str(proc.returncode)+'; '+str(scratch/'runtime.log'))
                finally:stop_child(proc)
            record=read(output/'record.json',{});evidence(record)
            expected=sorted(scratch.glob('clip-*.wav'))
            if [digest(p) for p in expected]!=[r['input_sha256'] for r in record['rows']]:raise RuntimeError('Incomplete or mismatched candidate inputs')
            if digest(source)!=source_hash:raise RuntimeError('Original WAV changed during inference')
            transcript=read(folder/'transcript.json',{})
            cap=read(folder/'capture.json',{})
            reference=read(folder/'reference.json',{}) if cid=='ATIS-REF-001' else {}
            timestamp=reference.get('capture_timestamp_utc') or datetime.strptime(cid,'%Y%m%dT%H%M%S.%fZ').replace(tzinfo=timezone.utc).isoformat()
            result={'capture_id':cid,'audio_path':str(source),'audio_sha256':source_hash,'capture_timestamp':timestamp,
              'capture_metadata':read(folder/'capture.json',{}),'production_raw_transcript':' '.join((x.get('raw') or {}).get('text',x.get('text','')) for x in transcript.get('segments',[])),
              'production_normalized_transcript':[x.get('normalization') for x in transcript.get('segments',[])],
              'production_runtime_seconds':transcript.get('asr_runtime_seconds'),
              'production_runtime_note':'Unavailable for older captures' if transcript.get('asr_runtime_seconds') is None else 'ASR calls including lock waits',
              'shadow_raw_transcript':record['text'],'shadow_normalized_transcript':[x.get('normalization') for x in record['rows']],
              'shadow_runtime_seconds':record['wall_seconds'],'supervised_runtime_seconds':time.monotonic()-started,
              'candidate_version':VERSION,'candidate_source_sha256':digest(RUNTIME),
              'shadow_worker_sha256':digest(ROOT/'atis_shadow.py'),
              'state':'completed','attempt':count,'completed_at':datetime.now(timezone.utc).isoformat(),'execution_evidence':record,
              'human_reference':bool(reference.get('human_reference_transcript')),
              'manual_transcription_priority':bool(transcript.get('segments') and record['text']!=' '.join(x.get('text','') for x in transcript.get('segments',[]))),
              'manual_transcription_review':'Successful HTP decode with production disagreement: useful for manual listening/transcription; clarity and truth unverified'}
            update(cid,'completed',result=result,root=root)
            # Derived audio is disposable; original is never copied/deleted here.
            for p in scratch.glob('clip-*.wav'):p.unlink()
    except (InterruptedError,TimeoutError,RuntimeError,OSError,ValueError,AssertionError) as error:
        if proc:stop_child(proc)
        with database(root) as db:current=db.execute('SELECT * FROM jobs WHERE capture_id=?',(cid,)).fetchone()
        final=current['attempts']>=MAX_ATTEMPTS or time.time()-current['created']>=MAX_AGE
        partial={'supervised_runtime_seconds':time.monotonic()-started if started else None,
                 'runtime_log':str(scratch/'runtime.log') if 'scratch' in locals() else None}
        update(cid,'failed' if final else 'deferred',str(error),result=partial,root=root,next_try=time.time()+min(600,30*2**current['attempts']))
    finally:
        if proc:stop_child(proc)
        # Retain diagnostics and chunk hashes, not repeatable derived WAVs.
        if 'scratch' in locals():
            for p in scratch.glob('clip-*.wav'):p.unlink(missing_ok=True)

def snapshot(root=ROOT):
    with database(root) as db:
        counts=dict(db.execute('SELECT state,count(*) FROM jobs GROUP BY state').fetchall())
        latest=db.execute('SELECT * FROM jobs ORDER BY updated DESC LIMIT 1').fetchone()
        complete=db.execute("SELECT result FROM jobs WHERE state='completed' ORDER BY updated DESC LIMIT 1").fetchone()
        failures=[dict(r) for r in db.execute("SELECT capture_id,state,reason,updated FROM jobs WHERE reason IS NOT NULL ORDER BY updated DESC LIMIT 5")]
    data={'mode':'shadow; production unchanged','counts':counts,'pending_deferred':sum(counts.get(x,0) for x in ('pending','deferred','running')),
          'latest':dict(latest) if latest else None,'latest_completed':json.loads(complete[0]) if complete else None,'recent_issues':failures}
    if data['latest']:data['latest'].pop('result',None)
    return data

def worker(stop,root=ROOT):
    # Distinct queue worker singleton: not a second accelerator lock.
    import fcntl
    singleton=(ir.directory(root)/'shadow-worker.lock').open('a')
    fcntl.flock(singleton,fcntl.LOCK_EX|fcntl.LOCK_NB)
    recover(root)
    while not stop.is_set():
        try:
            discover(root)
            release_silence_retention(root)
            with database(root) as db:
                expired=list(db.execute("SELECT capture_id,result FROM jobs WHERE state NOT IN ('completed','failed','skipped') AND created<?",(time.time()-MAX_AGE,)))
                for old in expired:
                    meta=json.loads(old['result']) if old['result'] else {}
                    meta.update(state='failed',reason='48-hour bounded queue expiry')
                    db.execute("UPDATE jobs SET state='failed',reason=?,updated=?,result=? WHERE capture_id=?",(meta['reason'],time.time(),json.dumps(meta),old['capture_id']))
                    print('ATIS SHADOW '+old['capture_id']+' failed: '+meta['reason'],flush=True)
                row=db.execute("SELECT * FROM jobs WHERE state IN ('pending','deferred') AND next_try<=? AND attempts<? ORDER BY capture_id DESC LIMIT 1",(time.time(),MAX_ATTEMPTS)).fetchone()
            if row:attempt(row,stop,root)
        except Exception as exc:print('ATIS SHADOW worker error: '+repr(exc),flush=True)
        stop.wait(10)

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--status',action='store_true');args=parser.parse_args()
    if args.status:print(json.dumps(snapshot(),indent=2))
    else:
        stop=threading.Event()
        for sig in (signal.SIGTERM,signal.SIGINT):signal.signal(sig,lambda *_:stop.set())
        worker(stop)
