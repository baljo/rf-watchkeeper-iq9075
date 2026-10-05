"""Offline retained-audio verification; all writes stay in the Airband stage."""
import hashlib
import json
from pathlib import Path
import shutil
import threading
import time
import atis_pipeline as pipeline

stage=Path(__file__).resolve().parent
operational=stage.parent
pipeline.ROOT=operational
pipeline.SMALL=operational/'model-trials/whisper-small-v0.50.2/model'
pipeline.rf_health.ROOT=operational
models = __import__('sys').argv[-1]=='--models'
cached = stage/'replay-segmentation.json'
records=json.loads(cached.read_text())['records'] if models and cached.exists() else []
sources=[] if records else sorted((operational/'recordings/atis').iterdir())
for source in sources:
    if not source.is_dir() or not (source/'raw.wav').is_file():continue
    capture=json.loads((source/'capture.json').read_text())
    if capture['status']!='ready':continue
    target=stage/'replay'/source.name
    target.mkdir(parents=True,exist_ok=True)
    shutil.copy2(source/'raw.wav',target/'raw.wav')
    shutil.copy2(source/'capture.json',target/'capture.json')
    before=hashlib.sha256((source/'raw.wav').read_bytes()).hexdigest()
    started=time.monotonic()
    clips=pipeline.prepare(target)
    segmentation=json.loads((target/'segmentation.json').read_text())
    records.append({'recording':source.name,'original_sha256':before,
        'original_unchanged':before==hashlib.sha256((source/'raw.wav').read_bytes()).hexdigest(),
        'audio_seconds':capture['audio_seconds'],'clips':len(clips),
        'candidate_seconds':sum(r['end_seconds']-r['start_seconds'] for r in segmentation['regions']),
        'preparation_seconds':time.monotonic()-started,'segmentation':segmentation})
pipeline.save(stage/'replay-segmentation.json',{'records':records})
print('Retained captures:',len(records),'originals unchanged:',all(r['original_unchanged'] for r in records))
print('Latest:',json.dumps(records[-1]))
if models:
    reason=pipeline.satellite_reason(240)
    if reason:raise RuntimeError(reason)
    busy=pipeline.command(['ps','-eo','comm']).splitlines()
    if any(name in ('voice-ai-ref','genie-t2t-run') for name in busy):
        raise RuntimeError('Existing inference is busy; replay deferred')
    target=stage/'replay'/records[-1]['recording']
    started=time.monotonic()
    pipeline.process(target,threading.Event())
    pipeline.save(stage/'replay-model-result.json',{'recording':target.name,
        'elapsed_seconds':time.monotonic()-started,
        'processing':json.loads((target/'processed.json').read_text()),
        'transcript':json.loads((target/'transcript.json').read_text()),
        'interpretation':json.loads((target/'interpretation.json').read_text())})
    print('Native saved-audio result:',(target/'processed.json').read_text())
