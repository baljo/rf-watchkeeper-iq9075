"""Isolated prompt-aware Small host decoding over unchanged QNN HTP contexts."""
import argparse,hashlib,json,os,resource,sys,time,wave
from pathlib import Path
import numpy as np
R=Path('/root/rf-watchkeeper');H=Path('/root/rf-watchkeeper/evaluation/atis-prompt-small-20261007');OLD=R/'evaluation/atis-model-bakeoff-20261007'
os.environ.setdefault('HF_HOME',str(H/'hf-cache'))
sys.path.insert(0,str(R));import atis_pipeline as ap
from transformers import WhisperTokenizer,WhisperFeatureExtractor
from qai_appbuilder import QNNContext,QNNConfig,Runtime,LogLevel,ProfilingLevel,DataType

def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def save(p,x):p.write_text(json.dumps(x,indent=2))
def guard():
 if os.environ.get('RF_ATIS_PRODUCTION'):
  import inference_resource as ir
  assert any(os.path.realpath(str(p))==str(ir.directory(R)/'htp.lock') for p in Path('/proc/self/fd').iterdir()), 'Production lease missing'
  reason=ap.satellite_reason(60,margin=0)
  if reason:raise InterruptedError(reason)
  return
 if os.environ.get('RF_SHADOW_LEASE_FD'):
  # A supervised shadow child must actually inherit the kernel lease.
  import inference_resource as ir
  fd=int(os.environ['RF_SHADOW_LEASE_FD']);os.fstat(fd)
  assert os.path.realpath('/proc/self/fd/'+str(fd))==str(ir.directory(R)/'htp.lock')
  if ir.production_waiting(R):raise InterruptedError('Production inference waiting')
 reason=ap.satellite_reason(60,margin=0)
 busy=subprocess.check_output(['ps','-eo','comm'],text=True).splitlines()
 if reason is None:
  for base in [R/'recordings/atis']:
   for folder in base.iterdir():
    cap=folder/'capture.json'
    if folder.is_dir() and cap.exists() and not (folder/'processed.json').exists():
     try:
      if json.loads(cap.read_text()).get('status')=='ready' and not ap.tower_retention.protected(folder):reason='Pending production capture';break
     except (OSError,ValueError):reason='Unverifiable pending capture';break
  commands=subprocess.check_output(['ps','-eo','args'],text=True).splitlines()
  if any('rtl_fm' in x and '-M am' in x for x in commands):reason='Airband capture active'
 if reason or any(n in busy for n in ['voice-ai-ref','genie-t2t-run']):raise InterruptedError(reason or 'Production inference active')
import subprocess
args=argparse.ArgumentParser();args.add_argument('--beam',type=int,default=1);args.add_argument('--prompt',choices=['fixed','legacy','none'],default='legacy');args.add_argument('--inputs',default='matched_hp');args.add_argument('--input-dir',type=Path);args.add_argument('--output-name');a=args.parse_args()
name=f'candidate_v2_{a.inputs}_{a.prompt}_beam{a.beam}';outdir=H/(a.output_name or name);outdir.mkdir(exist_ok=True)
# Standalone evaluation participates in the same accelerator lease.
if not os.environ.get('RF_SHADOW_LEASE_FD') and not os.environ.get('RF_ATIS_PRODUCTION'):
 import inference_resource as ir
 standalone_lease=ir.lease('candidate-standalone',timeout=1,production=False)
 standalone_fd=standalone_lease.__enter__()
# Supervised TERM must unwind native contexts instead of abandoning DSP mappings.
import signal
def diagnostic_stop(signum, frame):
 raise InterruptedError('Diagnostic preempted by signal '+str(signum))
signal.signal(signal.SIGTERM,diagnostic_stop)
signal.signal(signal.SIGINT,diagnostic_stop)
enc=dec=None
print('RUNTIME_DMA_BEFORE',Path('/sys/kernel/debug/dma_buf/bufinfo').read_text().splitlines()[-1],flush=True)
try:
 guard();start=time.monotonic();cpu0=time.process_time()
 QNNConfig.Config('/usr/lib',Runtime.HTP,LogLevel.ERROR,ProfilingLevel.BASIC)
 enc=QNNContext('atis_small_enc',str(ap.SMALL/'encoder_model_htp.bin'),input_data_type=DataType.NATIVE,output_data_type=DataType.NATIVE,deviceID=1)
 dec=QNNContext('atis_small_dec',str(ap.SMALL/'decoder_model_htp.bin'),input_data_type=DataType.NATIVE,output_data_type=DataType.NATIVE,deviceID=1)
 load=time.monotonic()-start
 print('GRAPH_LOAD_COMPLETE',load,flush=True)
 tok=WhisperTokenizer.from_pretrained('openai/whisper-small',local_files_only=True);fe=WhisperFeatureExtractor.from_pretrained('openai/whisper-small',local_files_only=True)
 inputs=json.loads((OLD/'inputs.json').read_text());prompt=inputs['prompt' if a.prompt=='fixed' else 'legacy_prompt'] if a.prompt!='none' else None
 prefix=([50361]+tok.encode(' '+prompt,add_special_tokens=False) if prompt else [])+[50258,50259,50359,50363]
 # OpenAI default suppression list, model-owned configuration; no reference values.
 config=json.loads((H/'generation_config.json').read_text());supp=config['suppress_tokens']
 names=dec.getInputName();shapes=dec.getInputShapes();outnames=dec.getOutputName();outshapes=dec.getOutputShapes()
 files=sorted((R/'asr-reference-corpus/ATIS-REF-001/qualcomm-results/q_full_audio_highpass80').glob('*.input.wav')) if a.inputs=='matched_hp' else sorted((H/('hp14' if a.inputs=='hp14' else 'after')).glob('*.wav'))
 if a.input_dir:files=sorted(a.input_dir.glob('clip-*.wav')) or sorted(a.input_dir.glob('*.wav'))
 assert files, 'No WAV inputs'
 rows=[];lastguard=0;decoder_accel_us=[];encoder_accel_us=[]
 for p in files:
  guard();t=time.monotonic();cput=time.process_time()
  with wave.open(str(p)) as w: assert w.getframerate()==16000;audio=np.frombuffer(w.readframes(w.getnframes()),dtype='<i2').astype(np.float32)/32768
  mel=fe(audio,sampling_rate=16000,return_tensors='np')['input_features'].astype(np.float16)
  assert mel.shape==(1,80,3000)
  cross=dict(zip(enc.getOutputName(),enc.Inference([mel])))
  encoder_accel_us.append(int(enc.getProfilingEvent(3004)))
  assert all(x.dtype==np.float16 and np.isfinite(x).all() for x in cross.values())
  selfstate={n:np.zeros(s,dtype=np.float16) for n,s in zip(names,shapes) if '_self_' in n}
  def step(token,pos,cache):
   global lastguard
   if time.monotonic()-lastguard>3:guard();lastguard=time.monotonic()
   mask=np.full((1,1,1,200),-100,dtype=np.float16);mask[...,max(0,199-pos):]=0
   state=dict(cross,**cache);state.update(input_ids=np.array([[token]],np.int32),position_ids=np.array([pos],np.int32),attention_mask=mask)
   outputs=dec.Inference([state[n] for n in names]);assert len(outputs)==25
   decoder_accel_us.append(int(dec.getProfilingEvent(3004)))
   cache={n.replace('_out','_in'):v.copy() for n,v in zip(outnames,outputs) if '_self_' in n}
   logits=outputs[outnames.index('logits')].reshape(-1).astype(np.float32)
   assert np.isfinite(logits).all()
   return logits,cache
  for pos,token in enumerate(prefix):logits,selfstate=step(token,pos,selfstate)
  prefill=time.monotonic()-t
  # Beam search: independent immutable native self-cache per branch, shared cross-cache.
  beams=[([],0.0,selfstate,logits)];finished=[];generated=0
  for pos in range(len(prefix),200):
   options=[]
   for ids,score,cache,logits in beams:
    logits=logits.copy();logits[supp]=-np.inf;logits[50258:]=-np.inf
    if not ids:logits[[50257,220]]=-np.inf
    m=logits.max();lp=logits-m-np.log(np.exp(logits-m).sum())
    top=np.argpartition(lp,-a.beam)[-a.beam:]
    for token in top:options.append((score+float(lp[token]),int(token),ids,cache))
   options.sort(key=lambda x:x[0],reverse=True);nextbeams=[]
   for score,token,ids,cache in options:
    if token==50257:finished.append((ids,score));continue
    if len(nextbeams)>=a.beam:continue
    lg,cs=step(token,pos,cache);nextbeams.append((ids+[token],score,cs,lg))
    if len(nextbeams)>=a.beam:break
   beams=nextbeams;generated+=1
   if len(finished)>=a.beam or not beams:break
  pool=finished or [(ids,s) for ids,s,_,_ in beams]
  best=max(pool,key=lambda x:x[1]/max(1,len(x[0])))
  row={'input':str(p),'input_sha256':sha(p),'text':tok.decode(best[0],skip_special_tokens=True).strip(),'normalization':ap.airband_text.normalize(tok.decode(best[0],skip_special_tokens=True).strip()),'tokens':best[0],'score':best[1],'wall_seconds':time.monotonic()-t,'cpu_seconds':time.process_time()-cput,'prefill_seconds':prefill,'eot_reached':bool(finished),'prefix_tokens':prefix,'context_limit':200,'decode_steps':generated}
  rows.append(row);save(outdir/(p.stem+'.json'),row);print('CHUNK',row['wall_seconds'],row['text'],flush=True)
 report={'model':'Whisper Small v0.50.2 unchanged HTP graphs','beam':a.beam,'prompt':prompt,'frontend':'HF WhisperFeatureExtractor CPU numpy; no VoiceAI VAD','rows':rows,'text':' '.join(x['text'] for x in rows),'wall_seconds':time.monotonic()-start,'chunk_wall_seconds':sum(x['wall_seconds'] for x in rows),'cpu_seconds':time.process_time()-cpu0,'load_seconds':load,'rss_kib':resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,'input_hash':inputs['source_sha256'],'model_hashes':{p.name:sha(p) for p in ap.SMALL.glob('*')},'mapped_libraries':[l.split()[-1] for l in Path('/proc/self/maps').read_text().splitlines() if any(x in l for x in ['Qnn','Htp','appbuilder'])],'device_fds':[]}
 for q in Path('/proc/self/fd').iterdir():
  try:
   dest=os.readlink(q)
   if 'fastrpc' in dest:report['device_fds'].append(dest)
  except OSError:pass
 report['device_id']=1;report['runtime_source_sha256']=sha(Path(__file__));report['encoder_accel_execute_us']=encoder_accel_us;report['decoder_accel_execute_us']=decoder_accel_us
 report['mapped_libraries']=sorted(set(report['mapped_libraries']));report['input_hash']=None if a.input_dir else inputs['source_sha256']
 report['cpu_percent_one_core']=100*report['cpu_seconds']/report['wall_seconds'];save(outdir/'record.json',report);print('COMPLETE',report['wall_seconds'],report['text'],flush=True)
finally:
 # Guard-triggered unwinding can overlap a supervisor TERM; finish cleanup once.
 signal.signal(signal.SIGTERM,signal.SIG_IGN)
 signal.signal(signal.SIGINT,signal.SIG_IGN)
 print('CLEANUP_START',flush=True)
 if dec is not None:del dec
 if enc is not None:del enc
 import gc;gc.collect()
 print('CLEANUP_COMPLETE',flush=True)
 print('RUNTIME_DMA_AFTER',Path('/sys/kernel/debug/dma_buf/bufinfo').read_text().splitlines()[-1],flush=True)
