"""Read-only ATIS dashboard data; no receiver or model invocation."""
import json
import re
from datetime import datetime, timezone
from urllib.parse import quote
from pathlib import Path

def folder(root, kind="atis"):
    base=(Path(root)/'recordings'/kind).resolve()
    if not base.exists():return None
    candidates=[p for p in base.iterdir() if p.is_dir() and not p.is_symlink() and (p/'capture.json').is_file()]
    if not candidates:return None
    latest=max(candidates,key=lambda p:p.name).resolve()
    if latest.parent!=base:raise ValueError('ATIS directory outside recordings')
    return latest

def read(path):
    try:return json.loads(path.read_text(encoding='utf-8'))
    except FileNotFoundError:return None
    except (ValueError, OSError) as error:
        return {'status':'failed','error':'Cannot read '+path.name+': '+str(error)}

def snapshot(root, kind="atis", recording=None):
    p=recording_folder(root, kind, recording) if recording else folder(root, kind)
    if p is None:return {'status':'waiting','message':'Waiting for the first scheduled ATIS capture.'}
    capture, transcript = read(p/'capture.json'), read(p/'transcript.json')
    interpretation, processing = read(p/'interpretation.json'), read(p/'processed.json')
    state = (processing or {}).get('status')
    status, message = 'needs_review', 'Recording is available. Automatic ATIS recognition remains unreliable; listen to verify all fields.'
    if (capture or {}).get('status') == 'interrupted':
        status, message = 'interrupted', 'Capture interrupted: '+str(capture.get('reason') or 'incomplete audio')
    elif any((item or {}).get('status') == 'failed' and (item or {}).get('error', '').startswith('Cannot read')
             for item in (capture, transcript, interpretation, processing)):
        status, message = 'failed', 'ATIS output could not be read; retained audio is available for review.'
    elif not processing:
        status, message = 'pending', 'Recorded audio is awaiting processing; satellite work can defer ASR.'
    elif state == 'failed':
        status, message = 'failed', 'ATIS transcription failed. '+str(processing.get('error') or 'See segment diagnostics; listen to retained audio.')
    elif state == 'no_activity':
        status, message = 'no_activity', 'No sustained audio activity detected; ASR skipped. This is not a receiver failure.'
    elif state == 'partial_success' or (interpretation or {}).get('status') == 'failed':
        status, message = 'partial_success', 'Transcript available; some recognition or interpretation failed. Listen to verify.'
    if transcript:
        for segment in transcript.get('segments', []):
            if segment.get('normalization'):
                segment['raw_text'] = segment.get('text')
                segment['text'] = segment['normalization']['text']
    if kind == 'tower':
        message = message.replace('ATIS', 'Tower').replace('all fields', 'the transcript')
    return {'status':status,'kind':kind,'recording':p.name,'capture':capture,
            'transcript':transcript,'interpretation':interpretation,
            'processing':processing,'audio_available':audio_path(p) is not None,
            'message':message}

def audio(root, kind="atis", recording=None):
    p=recording_folder(root, kind, recording) if recording else folder(root, kind)
    if p is None:raise FileNotFoundError('No ATIS recording')
    path=audio_path(p)
    if path is None:raise FileNotFoundError('Audio expired or unavailable')
    if path.parent!=p:raise ValueError('ATIS audio outside recording')
    with path.open('rb') as stream:data=stream.read(4*1024*1024+1)
    if len(data)>4*1024*1024:raise ValueError('ATIS audio too large')
    return data

def legacy_tiny(event):
    source=event.get('raw_event') if event.get('event_type')=='interpretation' else event
    if not isinstance(source,dict):return False
    path=str(source.get('input_file','')).replace('\\','/').lower()
    return 'atis' in path and source.get('model')=='whisper_tiny-qcs9075'

def recording_folder(root, kind, recording):
    if kind not in ('atis', 'tower') or not re.fullmatch(r'\d{8}T\d{6}(?:\.\d{6})?Z', recording):
        raise ValueError('Invalid recording identifier')
    base=(Path(root)/'recordings'/kind).resolve()
    p=base/recording
    if p.is_symlink() or p.resolve().parent!=base or not (p/'capture.json').is_file():
        raise FileNotFoundError('Recording unavailable')
    return p

def audio_path(p):
    for name in ('listen.wav', 'raw.wav'):
        path=p/name
        if not path.is_symlink() and path.is_file() and path.resolve().parent==p.resolve():
            return path
    return None

def recent(root, kind='tower', limit=20):
    base=Path(root)/'recordings'/kind
    rows=[]
    candidates=sorted((p for p in base.iterdir() if p.is_dir() and not p.is_symlink()
                       and (p/'capture.json').is_file()),key=lambda p:p.name,reverse=True) if base.exists() else []
    for p in candidates:
        try:
            stamp=datetime.strptime(p.name, '%Y%m%dT%H%M%S.%fZ' if '.' in p.name else '%Y%m%dT%H%M%SZ').replace(tzinfo=timezone.utc)
            row=snapshot(root,kind,p.name)
        except (ValueError, OSError):continue
        row['captured_at']=stamp.isoformat()
        row['duration_seconds']=(row['capture'] or {}).get('audio_seconds')
        row['result']='speech' if any(s.get('text') for s in (row['transcript'] or {}).get('segments',[])) else row['status']
        row['audio_url']='/api/'+kind+'/audio?recording='+quote(p.name) if row['audio_available'] else None
        rows.append(row)
        if len(rows)>=min(20,max(1,limit)):break
    return rows
