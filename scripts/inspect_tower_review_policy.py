"""Read-only live census, aggregate output only; run from repository root."""
import collections
import json
import sys
from pathlib import Path
from datetime import datetime, timezone
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import atis_view
from tower_review_policy import metadata, selection_reason

root = Path(sys.argv[1]) if len(sys.argv)>1 else Path('.')
counts = collections.Counter()
for folder in sorted((root/'recordings/tower').iterdir()):
    if folder.is_symlink() or not (folder/'capture.json').is_file(): continue
    row = atis_view.snapshot(root,'tower',folder.name)
    counts['captures'] += 1
    review = row.get('anomaly_review') or {}
    state = (row.get('human_review') or {}).get('human_review_label') or review.get('review_state')
    if state and state != 'unreviewed': counts['reviewed'] += 1
    valid = review.get('scoring_status')=='scored' and atis_view.finite_number(review.get('score'))
    if not valid: counts['unscored'] += 1; continue
    if (not state or state=='unreviewed') and review['score']>=review['threshold']:
        counts['before_queue'] += 1
    evidence = atis_view.read(root/'evaluation/tower-anomaly/shadow'/(folder.name+'.json'))
    review.update(metadata(evidence,folder.name))
    if 'explicit_review_override' not in row:
        capture=row.get('capture') or {}
        row['explicit_review_override']=(folder/'tower-pin.json').is_file() or any(capture.get(k) is True for k in ('pinned','reference','permanent_reference','reference_sample','review_override'))
    reason=selection_reason(row)
    if reason: counts['after_queue'] += 1; counts[reason] += 1
    if (not state or state=='unreviewed') and row.get('audio_available') and 45.67438250526811<=review['score']<55 and not row['explicit_review_override']:
        counts['grey_zone_pool'] += 1
print(json.dumps(dict(observed_utc=datetime.now(timezone.utc).isoformat(),counts=dict(counts)),indent=2))
