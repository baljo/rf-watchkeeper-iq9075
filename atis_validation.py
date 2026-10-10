"""ATIS validation only: durable human labels, raw evidence, no inference."""
import contextlib, datetime, difflib, hashlib, json, re, sqlite3, time, wave
from pathlib import Path
ROOT=Path(__file__).resolve().parent
FIELDS=['approach','runway','report_time','condition_code','surface','transition_level','wind_direction','wind_speed','variable_wind','visibility_weather','temperature','dew_point','qnh','information']
STATES=['candidate','needs_review','in_review','referenced','rejected_unusable']
LABELS=['Approach type','Runway','Runway-condition report time (HHMM UTC)','Runway condition code','Surface / state','Transition level','Wind direction (degrees)','Wind speed (knots)','Variable wind range (DDD-DDD)','Visibility / weather','Temperature (C)','Dew point (C)','QNH (hPa)','ATIS information letter (NATO)']
DIGITS=dict(zip('zero one two three four five six seven eight nine niner'.split(),'0 1 2 3 4 5 6 7 8 9 9'.split()))
ATOM=r'(?:\d+|'+ '|'.join(DIGITS)+r')\b'
NUM=ATOM+r'(?:[\s,.-]+'+ATOM+r')*'
SEP=r'[\s,:.\-]*(?:is\s+)?'
VERSION='strict-raw-v1'
def read(p,default=None):
 try:return json.loads(Path(p).read_text())
 except (OSError,ValueError):return default

def atomic(p,d):
 p=Path(p);p.parent.mkdir(parents=True,exist_ok=True);tmp=p.with_suffix(p.suffix+'.tmp');tmp.write_text(json.dumps(d,indent=2)+'\n');tmp.replace(p)

def sha(p):
 h=hashlib.sha256()
 with Path(p).open('rb') as f:
  for b in iter(lambda:f.read(1024*1024),b''):h.update(b)
 return h.hexdigest()

@contextlib.contextmanager
def db(root=ROOT):
 p=Path(root)/'data/atis-validation';p.mkdir(parents=True,exist_ok=True)
 c=sqlite3.connect(str(p/'review.sqlite3'),timeout=10);c.row_factory=sqlite3.Row
 c.execute('PRAGMA journal_mode=WAL');c.execute('PRAGMA synchronous=FULL')
 c.execute('CREATE TABLE IF NOT EXISTS captures(id TEXT PRIMARY KEY,state TEXT NOT NULL,rank REAL,data TEXT NOT NULL,reference TEXT,revision INTEGER NOT NULL DEFAULT 0,hold_until REAL,updated REAL NOT NULL)')
 c.execute('CREATE TABLE IF NOT EXISTS judgements(capture_id TEXT PRIMARY KEY, judgement TEXT NOT NULL, updated REAL NOT NULL)')
 c.execute('CREATE TABLE IF NOT EXISTS audit(id INTEGER PRIMARY KEY,capture_id TEXT,at REAL,action TEXT,payload TEXT)')
 try:yield c;c.commit()
 except: c.rollback();raise
 finally:c.close()

def numeric(s):
 tokens=re.findall(r'\d+|[a-z]+',s.lower())
 return ''.join(DIGITS.get(t,t) for t in tokens) if tokens and all(t.isdigit() or t in DIGITS for t in tokens) else None

def extract(text):
 """Only raw associations; all contradictory recognized repetitions invalidate credit."""
 text=re.sub(r'\[\d+ms\s*-\s*\d+ms\]',' ',text or '')
 out={k:{'value':None,'evidence':[],'status':'missing'} for k in FIELDS}
 def put(k,value,quote):out[k]['evidence'].append({'value':value,'quote':quote})
 def numbers(k,pattern,width=None,low=None,high=None,padded=False):
  for m in re.finditer(pattern,text,re.I):
   v=numeric(m[1]);valid=v is not None and (width is None or len(v)==width) and (low is None or low<=int(v)<=high)
   put(k, (v.zfill(width) if padded else v if k in ('report_time','wind_direction','condition_code') else str(int(v))) if valid else None,m.group())
 numbers('runway',r'\brunway\s+('+NUM+r')',low=1,high=36)
 numbers('report_time',r'\bconditions?\s+report'+SEP+r'(?:at'+SEP+r')?('+NUM+r')\s*[,;]?\s*UTC\b',width=4)
 numbers('condition_code',r'\brunway\s+condition\s+code'+SEP+'('+NUM+r')',width=3)
 numbers('transition_level',r'\btransition\s+level'+SEP+'('+NUM+r')',low=1,high=200)
 numbers('wind_direction',r'\b(?:wind\s+(?:touchdown\s+)?zone|wind(?:\s+touchdown\s+zone)?|zone)'+SEP+'('+NUM+r')\s*[,;]?\s*degrees?\b',width=3,low=0,high=360)
 numbers('wind_speed',r'\b(?:wind\s+(?:touchdown\s+)?zone|wind(?:\s+touchdown\s+zone)?|zone)'+SEP+NUM+r'\s*[,;]?\s*degrees?'+SEP+'('+NUM+r')\s*[,;]?\s*knots?\b',low=0,high=150)
 numbers('temperature',r'\btemperature'+SEP+r'((?:minus\s+)?'+NUM+r')')
 numbers('dew_point',r'\bdew\s+point'+SEP+r'((?:minus\s+)?'+NUM+r')')
 numbers('qnh',r'\bq\s*n\s*h'+SEP+'('+NUM+r')',low=850,high=1100)
 for m in re.finditer(r'\b(?:variable|area)\s+between'+SEP+'('+NUM+r')'+SEP+r'and'+SEP+'('+NUM+r')\s*[,;]?\s*degrees?\b',text,re.I):
  a,b=numeric(m[1]),numeric(m[2]);put('variable_wind',a+'-'+b if a and b and len(a)==len(b)==3 and max(int(a),int(b))<=360 else None,m.group())
 for m in re.finditer(r'\b(RNAV|ILS|visual|VOR|NDB|RNP)\s+approach\b',text,re.I):put('approach',m[1].upper(),m.group())
 for m in re.finditer(r'\b(?:RMP|RMT|RNT|RNG|R&T|R&P)\s+approach\b',text,re.I):put('approach',None,m.group())
 for m in re.finditer(r'\bCAVOK\b',text,re.I):put('visibility_weather','CAVOK',m.group())
 for m in re.finditer(r'\b(?:runway\s+condition\s+code[^.!?]{0,80}|all\s+(?:are\s+)?)\b(dry|wet|snow|ice)\b',text,re.I):put('surface',m[1].upper(),m.group())
 nato='alpha bravo charlie delta echo foxtrot golf hotel india juliet kilo lima mike november oscar papa quebec romeo sierra tango uniform victor whiskey x-ray yankee zulu'.split()
 for m in re.finditer(r'\binformation'+SEP+'('+'|'.join(nato)+r')\b',text,re.I):put('information',m[1].upper(),m.group())
 # Negative temperatures require explicit minus; do not treat separator hyphens as negatives.
 # Explicit incompatible information identifiers invalidate a correct repetition.
 for m in re.finditer(r'\binformation'+SEP+r'([a-z][a-z-]*|'+NUM+r')',text,re.I):
  if m[1].lower() not in nato:put('information',None,m.group())
 for k in ('temperature','dew_point'):
  out[k]['evidence']=[]
  label=r'temperature' if k=='temperature' else r'dew\s+point'
  for m in re.finditer(r'\b'+label+SEP+r'(minus\s+)?('+NUM+r')',text,re.I):
   v=numeric(m[2]);n=int(v) if v else None;put(k,str(-n if m[1] else n) if n is not None and n<=60 else None,m.group())
 for k,v in out.items():
  values={e['value'] for e in v['evidence']}
  if len(values)==1 and None not in values:v.update(value=next(iter(values)),status='supported')
  elif v['evidence']:v['status']='conflicting_or_unintelligible'
 return out

def score(data,reference):
 results={}
 for system in ('production','shadow','external'):
  if system=='external' and not data.get('external_raw_transcript'):continue
  fields=extract(data.get(system+'_raw_transcript'));correct={};assessed={}
  for k in FIELDS:
   r=reference[k];assessed[k]=r['status']=='confirmed'
   correct[k]=bool(assessed[k] and fields[k]['status']=='supported' and fields[k]['value']==r['value'])
  results[system]={'correct':sum(correct.values()),'possible':14,'assessable':sum(assessed.values()),'per_field':correct,'assessed':assessed,'runtime_seconds':data.get(system+'_runtime_seconds'),'policy':VERSION}
 return results

def folder_for(root,cid):
 if not re.fullmatch(r'\d{8}T\d{6}\.\d{6}Z',cid):raise ValueError('Invalid capture ID')
 folder=Path(root)/'recordings/atis'/cid
 if folder.is_symlink():raise ValueError('Symlink capture not allowed')
 return folder

def hold(folder,root=ROOT):
 try:
  with db(root) as c:r=c.execute('SELECT state,hold_until FROM captures WHERE id=?',(Path(folder).name,)).fetchone()
  return bool(r and (r['state']=='referenced' or r['state'] in ('needs_review','in_review') and (r['hold_until'] or 0)>time.time()))
 except sqlite3.Error:return True

def sync(root=ROOT):
 """Read results only, discover new completions, queue at most ten distinct messages."""
 root=Path(root);source=root/'data/atis-shadow/jobs.sqlite3'
 if not source.exists():return
 s=sqlite3.connect('file:'+str(source)+'?mode=ro',uri=True);s.row_factory=sqlite3.Row
 try:jobs=list(s.execute('SELECT * FROM jobs'))
 finally:s.close()
 with db(root) as c:
  for job in jobs:
   cid=job['capture_id']
   if not re.fullmatch(r'\d{8}T\d{6}\.\d{6}Z',cid):continue
   old=c.execute('SELECT * FROM captures WHERE id=?',(cid,)).fetchone()
   if old and (old['state']!='candidate' or (json.loads(old['data']).get('processing_status')==job['state'] and json.loads(old['data']).get('parser_version')==VERSION)):continue
   folder=folder_for(root,cid);cap=read(folder/'capture.json',{});prod=read(folder/'transcript.json',{});processed=read(folder/'processed.json',{})
   d=json.loads(job['result'] or '{}');d.pop('execution_evidence',None)
   d.update(capture_id=cid,capture_timestamp=datetime.datetime.strptime(cid,'%Y%m%dT%H%M%S.%fZ').replace(tzinfo=datetime.timezone.utc).isoformat(),processing_status=job['state'],production_status=processed.get('status'),audio_duration=cap.get('audio_seconds'),quality_metrics={k:v for k,v in cap.items() if any(x in k for x in ('rms','snr','quality','peak','clipp','truncat'))},external_raw_transcript=None,external_normalized_transcript=None,external_runtime_seconds=None)
   d['production_raw_transcript']=' '.join((x.get('raw') or {}).get('text',x.get('text','')) for x in prod.get('segments',[]))
   d['production_runtime_seconds']=prod.get('asr_runtime_seconds',d.get('production_runtime_seconds'))
   d['production_normalized_transcript']=[x.get('normalization') for x in prod.get('segments',[])]
   for system in ('production','shadow'):d[system+'_fields']=extract(d.get(system+'_raw_transcript'))
   audio=folder/'raw.wav';d['audio_available']=audio.is_file();d['audio_path']=str(audio)
   if d['audio_available'] and job['state']=='completed':d['audio_sha256']=sha(audio)
   p,q=d['production_fields'],d['shadow_fields'];coverage=[sum(v['status']=='supported' for v in x.values()) for x in (p,q)]
   disagreement=sum(p[k]['value']!=q[k]['value'] for k in FIELDS)
   textp=d.get('production_raw_transcript') or '';textq=d.get('shadow_raw_transcript') or ''
   complete=all(len(t.split())>=35 for t in (textp,textq)) and (d.get('audio_duration') or 0)>=60
   d['parser_version']=VERSION
   eligible=job['state']=='completed' and d['audio_available'] and processed.get('status') not in ('failed','no_activity') and complete and max(coverage)>=4 and min(coverage)>=2 and not any(cap.get(k) for k in ('truncated','clipped'))
   conflicts=sum(v['status']=='conflicting_or_unintelligible' for x in (p,q) for v in x.values())
   rank=round(20+2*sum(coverage)+2*disagreement+10*complete-2*conflicts,2) if eligible else -100
   d.update(conflicting_fields=conflicts,coverage=coverage,disagreements=disagreement,eligible=eligible,rank_reasons=[('Both recognizers completed; original audio available' if eligible else 'Incomplete, failed, sparse, or missing audio: not selected'),str(coverage)+' supported raw fields; '+str(disagreement)+' field disagreements','Approximate message completeness; listening must confirm quality'],duplicate_of=None)
   c.execute('INSERT INTO captures(id,state,rank,data,updated) VALUES (?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET rank=excluded.rank,data=excluded.data,updated=excluded.updated',(cid,'candidate',rank,json.dumps(d),time.time()))
  rows=list(c.execute('SELECT * FROM captures ORDER BY rank DESC,id DESC'));selected=[r for r in rows if r['state'] in ('needs_review','in_review','referenced')]
  for row in rows:
   if row['state']!='candidate':continue
   d=json.loads(row['data'])
   if not d['eligible']:continue
   duplicate=None
   for prev in selected:
    e=json.loads(prev['data'])
    samehash=d.get('audio_sha256')==e.get('audio_sha256')
    similarity=sum(difflib.SequenceMatcher(None,d.get(k+'_raw_transcript',''),e.get(k+'_raw_transcript','')).ratio() for k in ('production','shadow'))/2
    # Consensus signature is a duplicate hint, never a reference label.
    keys=('information','qnh','temperature','dew_point','wind_direction','report_time')
    sig=lambda x:tuple(x['production_fields'][k]['value'] if x['production_fields'][k]['value']==x['shadow_fields'][k]['value'] else None for k in keys)
    a,b=sig(d),sig(e)
    same_message=sum(v is not None for v in a)>=3 and a==b
    def message_signature(x):
     values=[]
     for k in ('information','qnh'):
      found={x[system+'_fields'][k]['value'] for system in ('production','shadow')} - {None}
      values.append(next(iter(found)) if len(found)==1 else None)
     return tuple(values)
    sa,sb=message_signature(d),message_signature(e)
    same_message=same_message or all(sa) and sa==sb
    if samehash or similarity>.80 or same_message:duplicate=prev['id'];break
   if duplicate:
    d['duplicate_of']=duplicate;c.execute('UPDATE captures SET data=? WHERE id=?',(json.dumps(d),row['id']));continue
   if len(selected)>=10:continue
   if hold_marker(folder_for(root,row['id']),time.time()+30*86400):
    c.execute("UPDATE captures SET state='needs_review',hold_until=?,updated=? WHERE id=?",(time.time()+30*86400,time.time(),row['id']));selected.append(row)

def hold_marker(folder,until):
 if not (folder/'raw.wav').is_file():return False
 atomic(folder/'atis-validation-hold.json',{'until':until,'purpose':'bounded human ATIS review','permanent':False});return True

def snapshot(root=ROOT):
 sync(root)
 with db(root) as c:
  rows=[dict(r) for r in c.execute('SELECT * FROM captures ORDER BY id DESC')]
  judgements={r['capture_id']:r['judgement'] for r in c.execute('SELECT * FROM judgements')}
 for r in rows:
  r['judgement']=judgements.get(r['id']);r['data']=json.loads(r['data']);r['reference']=json.loads(r['reference']) if r['reference'] else None
  for system in ('production','shadow','external'):
   if system!='external' or r['data'].get('external_raw_transcript'):r['data'][system+'_fields']=extract(r['data'].get(system+'_raw_transcript'))
 refs=[r for r in rows if r['state']=='referenced'];summary={'referenced':len(refs),'awaiting_review':sum(r['state'] in ('needs_review','in_review') for r in rows),'evaluated':len(rows),'completed_real':sum(r['data']['processing_status']=='completed' for r in rows),'target':'5–10 independent recordings; promotion is a human decision','systems':{}}
 for system in ('production','shadow','external'):
  scores=[score(r['data'],r['reference']).get(system) for r in refs];scores=[s for s in scores if s];runtimes=[s['runtime_seconds'] for s in scores if s['runtime_seconds'] is not None]
  summary['systems'][system]={'correct':sum(s['correct'] for s in scores),'possible':14*len(scores),'assessable':sum(s['assessable'] for s in scores),'per_field':{k:{'correct':sum(s['per_field'][k] for s in scores),'possible':sum(s['assessed'][k] for s in scores)} for k in FIELDS},'runtime_average_seconds':sum(runtimes)/len(runtimes) if runtimes else None,'runtime_samples':len(runtimes)}
 for r in refs:r['scores']=score(r['data'],r['reference'])
 return {'fields':dict(zip(FIELDS,LABELS)),'summary':summary,'captures':rows,'scoring_policy':'Strict raw associations only; no label repair; contradictions get no credit. Uncertain/unknown/clipped fields earn no credit in /14, and are excluded from assessable accuracy.'}

def save(request,root=ROOT):
 cid=request['id'];folder=folder_for(root,cid);action=request['action']
 if action not in ('draft','approve','reject','start','judge'):raise ValueError('Unknown review action')
 with db(root) as c:
  c.execute('BEGIN IMMEDIATE');r=c.execute('SELECT * FROM captures WHERE id=?',(cid,)).fetchone()
  if not r:raise ValueError('Capture not found')
  if request.get('revision')!=r['revision']:raise ValueError('Review changed; reload before saving')
  if action=='judge':
   judgement=request.get('judgement')
   if judgement not in ('correct','partly_correct','wrong','unintelligible'):raise ValueError('Invalid judgement')
   c.execute('INSERT INTO judgements VALUES (?,?,?) ON CONFLICT(capture_id) DO UPDATE SET judgement=excluded.judgement,updated=excluded.updated',(cid,judgement,time.time()))
   c.execute('UPDATE captures SET revision=revision+1 WHERE id=?',(cid,))
   c.execute('INSERT INTO audit(capture_id,at,action,payload) VALUES (?,?,?,?)',(cid,time.time(),'judge',json.dumps({'judgement':judgement,'revision':r['revision']+1})))
   return {'id':cid,'state':r['state'],'revision':r['revision']+1,'judgement':judgement}
  if r['state']=='referenced':raise ValueError('Approved reference is immutable; use an audited correction workflow')
  if r['state'] not in ('needs_review','in_review') and not (r['state']=='candidate' and json.loads(r['data']).get('eligible')):raise ValueError('Capture is not eligible for reference review')
  if r['state']=='candidate':
   if not hold_marker(folder,time.time()+30*86400):raise ValueError('Audio unavailable')
   c.execute('UPDATE captures SET hold_until=? WHERE id=?',(time.time()+30*86400,cid))
  reference=request.get('reference');d=json.loads(r['data']);state={'start':'in_review','draft':'in_review','approve':'referenced','reject':'rejected_unusable'}[action]
  if action in ('draft','approve'):
   if not isinstance(reference,dict) or set(reference)!=set(FIELDS):raise ValueError('Exactly 14 reference fields required')
   for k,v in reference.items():
    if not isinstance(v,dict) or v.get('status') not in ('unverified','confirmed','unknown','uncertain','not_present_clipped'):raise ValueError('Invalid field status')
    if not isinstance(v.get('value',''),str) or len(v.get('value',''))>80:raise ValueError('Invalid field value')
    if v['status']=='confirmed' and not v.get('value','').strip():raise ValueError('Confirmed fields need a value')
    if action=='approve' and v['status']=='unverified':raise ValueError('Resolve every field: confirm, unknown, uncertain, or not present / clipped')
    v['value']=v.get('value','').strip()
    if v['status']=='confirmed':
     if k in ('approach','surface','visibility_weather','information'):v['value']=v['value'].upper()
     if k=='report_time' and not (re.fullmatch(r'\d{4}',v['value']) and int(v['value'][:2])<24 and int(v['value'][2:])<60):raise ValueError('Report time must be HHMM UTC')
     if k=='condition_code' and not re.fullmatch(r'[0-6]{3}',v['value']):raise ValueError('Condition code needs three digits from 0 to 6, e.g. 666')
     if k in ('temperature','dew_point','qnh','wind_speed','transition_level') and not re.fullmatch(r'-?\d+',v['value']):raise ValueError('Use an integer for '+k)
     if k=='wind_direction' and not (re.fullmatch(r'\d{3}',v['value']) and int(v['value'])<=360):raise ValueError('Wind direction needs three digits, 000-360')
     if k=='variable_wind' and not (re.fullmatch(r'\d{3}-\d{3}',v['value']) and all(int(x)<=360 for x in v['value'].split('-'))):raise ValueError('Wind range needs DDD-DDD')
    v['approved_by_human']=action=='approve'
   if action=='approve':
    if not any(v['status']=='confirmed' for v in reference.values()):raise ValueError('A reference needs at least one confirmed operational field; reject unusable audio instead')
    if not d['audio_available'] or not (folder/'raw.wav').is_file() or sha(folder/'raw.wav')!=d['audio_sha256']:raise ValueError('Source audio missing or changed')
    # Existing permanent pin framework; protect original without WAV duplication.
    atomic(folder/'protected.json',{'permanent_reference':True,'purpose':'human-approved ATIS validation','capture_id':cid,'audio_sha256':d['audio_sha256']})
    atomic(folder/'atis-human-reference.json',{'capture_id':cid,'approved_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'fields':reference,'source_sha256':d['audio_sha256'],'policy':VERSION,'scores':score(d,reference)})
  if action=='reject':reference=None
  if action=='start':reference=json.loads(r['reference']) if r['reference'] else None
  c.execute('UPDATE captures SET state=?,reference=?,revision=revision+1,updated=? WHERE id=?',(state,json.dumps(reference) if reference else None,time.time(),cid))
  c.execute('INSERT INTO audit(capture_id,at,action,payload) VALUES (?,?,?,?)',(cid,time.time(),action,json.dumps({'fields':reference,'revision':r['revision']+1})))
 if action=='reject':(folder/'atis-validation-hold.json').unlink(missing_ok=True)
 return {'id':cid,'state':state,'revision':r['revision']+1,'scores':score(d,reference) if state=='referenced' else None}

def supply_external(cid,text,normalized=None,runtime=None,root=ROOT):
 if not isinstance(text,str) or not text.strip() or len(text)>50000:raise ValueError('Supply a manual transcript')
 if runtime is not None and (not isinstance(runtime,(int,float)) or not 0<=runtime<36000):raise ValueError('Invalid runtime')
 with db(root) as c:
  r=c.execute('SELECT data FROM captures WHERE id=?',(cid,)).fetchone()
  if not r:raise ValueError('Unknown capture')
  d=json.loads(r['data']);d.update(external_raw_transcript=text,external_normalized_transcript=normalized,external_runtime_seconds=runtime,external_fields=extract(text))
  c.execute('UPDATE captures SET data=?,revision=revision+1,updated=? WHERE id=?',(json.dumps(d),time.time(),cid))
  c.execute('INSERT INTO audit(capture_id,at,action,payload) VALUES (?,?,?,?)',(cid,time.time(),'manual_external_transcript',json.dumps({'sha256':hashlib.sha256(text.encode()).hexdigest()})))

if __name__=='__main__':
 import argparse
 a=argparse.ArgumentParser();a.add_argument('--sync',action='store_true');args=a.parse_args()
 if args.sync:sync()
 else:print(json.dumps(snapshot(),indent=2))
