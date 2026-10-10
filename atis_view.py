"""Read-only ATIS dashboard data; no receiver or model invocation."""
import json
import math
import re
from datetime import datetime, timezone
from urllib.parse import quote
from pathlib import Path
import atis_parser
import atis_lexicon
import atis_consensus

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
    structured = None
    if kind == 'atis':
        structured = read(p/'structured-atis.json')
        if transcript and (structured is None or structured.get('parser_version') != atis_parser.VERSION):
            # Historical captures receive the same pure parser without rewriting evidence.
            structured = atis_parser.parse(transcript)
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
        from tower_classification import classify
        classification = classify(p)
        status, message = classification['status'], classification['message']
    result = {'status':status,'kind':kind,'recording':p.name,'capture':capture,
            'transcript':transcript,'interpretation':interpretation,
            'processing':processing,'audio_available':audio_path(p) is not None,
            'message':message}
    if kind == 'atis':
        result['structured_atis'] = structured
        result.update(atis_details(transcript, structured, state, p.name))
    elif kind == 'tower':
        evidence = read(Path(root)/'evaluation/tower-anomaly/shadow'/(p.name+'.json'))
        if completed_tower_score(evidence):
            from tower_anomaly_shadow import review_metadata
            try:
                result['anomaly_review'] = dict(review_metadata(evidence, processing or {}),
                    model_sha256=evidence.get('model_sha256'), scoring_status='scored')
                from tower_anomaly_review import load
                human = load(root, p.name)
                if human: result['anomaly_review']['review_state'] = human['human_review_label']
            except (KeyError, TypeError, ValueError): pass
    if kind == 'tower':
        result['classification'] = classification
        result['processing'] = read(p/'tower-classification.json') or classification
        from tower_anomaly_review import load
        human = load(root, p.name)
        result['human_review'] = human
        result.setdefault('anomaly_review', dict(score=None, median_score=None, threshold=None, severity_band='acoustic evidence / no anomaly score', review_state='unreviewed'))
        result['anomaly_review']['review_state'] = (human or {}).get('human_review_label', 'unreviewed')
        result['anomaly_review'].setdefault('anomaly_candidate', False)
    return result

def atis_details(transcript, structured, processing_state, recording):
    """Explicit display layers; counts measure extraction, not speech accuracy."""
    segments=[]
    for index,s in enumerate((transcript or {}).get('segments',[])):
        raw=(s.get('raw') or {}).get('text',s.get('raw_text',s.get('text','')))
        raw=raw if isinstance(raw,str) else ''
        normalized=(s.get('normalization') or {}).get('text',raw)
        normalized=normalized if isinstance(normalized,str) else raw
        corrected=atis_lexicon.correct(normalized)
        segments.append({'segment_index':index,'start_seconds':s.get('start_seconds'),
            'status':s.get('status'),'error':s.get('error'),'raw_text':raw,
            'normalized_text':corrected['text'],'normalization':s.get('normalization'),
            'lexical_corrections':corrected['corrections']})
    states=(structured or {}).get('field_status',{})
    recognized=sum(states.get(k)=='recognized' for k in atis_parser.FIELDS)
    conflicts=sum(states.get(k)=='conflicting' for k in atis_parser.FIELDS)
    if not structured:
        parser_status='failed' if processing_state=='failed' else 'unavailable'
    elif recognized==len(atis_parser.FIELDS):parser_status='complete'
    elif recognized or conflicts:parser_status='partial'
    else:parser_status='failed'
    stamp=datetime.strptime(recording,'%Y%m%dT%H%M%S.%fZ' if '.' in recording else '%Y%m%dT%H%M%SZ').replace(tzinfo=timezone.utc)
    return {'captured_at':stamp.isoformat(),'raw_asr':{'text':'\n'.join(s['raw_text'] for s in segments),'segments':segments},
        'normalized':{'text':'\n'.join(s['normalized_text'] for s in segments),
            'basis':'Existing transcript normalization followed by conservative lexical correction; parser uses raw ASR with its own lexical correction.'},
        'parser_status':parser_status,'parser_status_basis':'Complete means all supported fields recognized; partial means some recognized or conflicting; failed means no fields recognized or processing failed; unavailable means no parser result.',
        'quality':{'recognized_fields':recognized,'supported_fields':len(atis_parser.FIELDS),
            'conflicting_fields':conflicts,'asr_segments':len(segments),
            'failed_asr_segments':sum(s['status']=='failed' for s in segments),
            'basis':'Field and segment counts only; no ASR confidence probabilities available.',
            'human_review_required':True}}

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

def finite_number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def completed_tower_score(evidence):
    """The worker atomically publishes final JSON only after successful scoring."""
    if not isinstance(evidence, dict) or evidence.get('mode') != 'shadow_only':
        return False
    if evidence.get('status') not in (None, 'scored'):
        return False
    summary = evidence.get('summary')
    return (isinstance(summary, dict) and finite_number(summary.get('count')) and
            summary['count'] > 0 and finite_number(summary.get('p100')) and
            finite_number(evidence.get('threshold')))


def needs_tower_review(row):
    human_label = (row.get('human_review') or {}).get('human_review_label')
    review = row.get('anomaly_review') or {}
    state = human_label or review.get('review_state')
    reviewed = bool(state and state != 'unreviewed')
    scored = (review.get('scoring_status') == 'scored' and
              finite_number(review.get('score')) and finite_number(review.get('threshold')))
    # Acoustic classifications must not bypass the AD candidate threshold.
    return not reviewed and scored and review['score'] >= review['threshold']


def recent(root, kind='tower', limit=20, end_recording=None, candidates_only=False):
    base=Path(root)/'recordings'/kind
    rows=[]
    candidates=sorted((p for p in base.iterdir() if p.is_dir() and not p.is_symlink()
                       and (p/'capture.json').is_file()),key=lambda p:p.name,reverse=True) if base.exists() else []
    if end_recording is not None:candidates=[p for p in candidates if p.name<=end_recording]
    for p in candidates:
        try:
            stamp=datetime.strptime(p.name, '%Y%m%dT%H%M%S.%fZ' if '.' in p.name else '%Y%m%dT%H%M%SZ').replace(tzinfo=timezone.utc)
            row=snapshot(root,kind,p.name)
            if candidates_only and not needs_tower_review(row): continue
        except (ValueError, OSError):continue
        row['captured_at']=stamp.isoformat()
        row['duration_seconds']=(row['capture'] or {}).get('audio_seconds')
        row['result']='speech' if any(s.get('text') for s in (row['transcript'] or {}).get('segments',[])) else row['status']
        row['audio_url']='/api/'+kind+'/audio?recording='+quote(p.name) if row['audio_available'] else None
        rows.append(row)
        if len(rows)>=min(20,max(1,limit)):break
    return rows

def atis_response(root, recording=None):
    """Keep individual parsing separate; consensus is derived read-only."""
    if recording is not None:recording_folder(root,'atis',recording)
    rows=recent(root,'atis',end_recording=recording)
    # Copy the newest row before adding history to avoid circular responses.
    data=dict(rows[0]) if rows else snapshot(root,recording=recording)
    individual={'recording':data.get('recording'),'captured_at':data.get('captured_at'),
                'structured_atis':data.get('structured_atis')}
    data['individual_atis']=individual
    data['consensus_atis']=atis_consensus.build(rows)
    if recording is None:
        data['latest_individual_atis']=individual
        data['recent_results']=rows
    return data
