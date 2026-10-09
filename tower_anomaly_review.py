"""Human diagnostic labels; no inference, retention or production decisions."""
import json
import math
from pathlib import Path
from datetime import datetime, timezone

LABELS = ('confirmed_voice', 'probable_voice', 'no_voice', 'carrier_or_squelch', 'interference', 'unclear')

def table(root):
    base = Path(root)/'evaluation/tower-anomaly/human-review'
    if base.is_symlink(): raise ValueError('Invalid review directory')
    return [json.loads(p.read_text()) for p in sorted(base.glob('*.json')) if not p.is_symlink()]

def severity(score, threshold):
    if not math.isfinite(float(score)): raise ValueError('Invalid anomaly score')
    if score < threshold: return 'background / below anomaly threshold'
    if score < 75: return 'weak anomaly'
    if score <= 200: return 'notable anomaly'
    return 'strong anomaly'

def review_path(root, capture):
    import re
    if not isinstance(capture, str) or not re.fullmatch(r'\d{8}T\d{6}(?:\.\d+)?Z', capture):
        raise ValueError('Invalid capture ID')
    base = Path(root)/'evaluation/tower-anomaly/human-review'
    if base.is_symlink(): raise ValueError('Invalid review directory')
    path = base/(capture+'.json')
    if path.is_symlink(): raise ValueError('Invalid review file')
    return path

def load(root, capture):
    path = review_path(root, capture)
    try: return json.loads(path.read_text())
    except FileNotFoundError: return None

def comparison(row):
    review = row['anomaly_review']
    processing = row.get('processing') or {}
    return dict(capture_id=row['recording'], peak_score=review['score'],
                median_score=review.get('median_score'), threshold=review['threshold'],
                severity_band=review['severity_band'],
                vad_result=processing.get('vad', processing.get('classification', 'unavailable')),
                asr_status=processing.get('status', row.get('status')),
                asr_result=row.get('transcript'), human_review_label=review['review_state'])

def save(root, request):
    import atis_view
    capture, label = request.get('capture_id'), request.get('label')
    path = review_path(root, capture)
    if label not in LABELS: raise ValueError('Invalid human review label')
    row = atis_view.snapshot(root, 'tower', capture)
    if not row.get('anomaly_review'): raise ValueError('No anomaly score for this capture')
    row['anomaly_review']['review_state'] = label
    result = comparison(row)
    folder = atis_view.recording_folder(root, 'tower', capture)
    classifier = atis_view.read(folder/'segmentation.json')
    result['vad_result'] = classifier if classifier is not None else result['vad_result']
    result['reviewed_at'] = datetime.now(timezone.utc).isoformat()
    result['source'] = 'human dashboard review'
    previous = load(root, capture) or {}
    for key in ('future_asr_benchmark', 'clarity_assessment', 'permanent_reference'):
        if key in previous: result[key] = previous[key]
    if request.get('clear_benchmark') is True:
        if label != 'confirmed_voice':
            raise ValueError('A clearer benchmark requires confirmed_voice')
        from tower_retention import pin
        result['future_asr_benchmark'] = True
        result['clarity_assessment'] = 'Human marked substantially clearer Tower transmission; ASR deferred'
        result['permanent_reference'] = str(pin(root, capture))
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix('.pending')
    temporary.write_text(json.dumps(result, indent=2)+'\n')
    temporary.replace(path)
    try:
        from tower_validation import snapshot
        snapshot(root)
    except (OSError, ValueError, KeyError, TypeError):
        result['validation_status'] = 'refresh_pending'
    return result
