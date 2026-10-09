import collections
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import urllib.request
from datetime import datetime, timezone
sys.path.insert(0, '/root/rf-watchkeeper')
import atis_view
root = Path('/root/rf-watchkeeper')
rows = []
for p in sorted((root/'recordings/tower').iterdir(), reverse=True):
    if p.is_dir() and (p/'capture.json').is_file():
        row = atis_view.snapshot(root, 'tower', p.name)
        review = row.get('anomaly_review') or {}
        rows.append(dict(id=p.name, status=row['status'], anomaly=bool(review.get('anomaly_candidate')),
                         label=(row.get('human_review') or {}).get('human_review_label'),
                         eligible=bool(not (row.get('human_review') or {}).get('human_review_label') and (review.get('anomaly_candidate') or row['status'] in ('voice_candidate', 'uncertain')))))
protected = ['tower_retention.py','tower_classification.py','job_manager.py','watchkeeper.py','tower_anomaly_shadow.py','tower_anomaly_review.py']
hashes = {name: hashlib.sha256((root/name).read_bytes()).hexdigest() for name in protected}
hashes['human_reviews'] = hashlib.sha256(b''.join(p.read_bytes() for p in sorted((root/'evaluation/tower-anomaly/human-review').glob('*.json')))).hexdigest()
units = subprocess.check_output(['systemctl','list-units','--type=service','--state=running','--no-legend']).decode()
services = [line.split()[0] for line in units.splitlines() if any(x in line for x in ('rf-watchkeeper','atis','tower','meteor'))]
pids = {name:subprocess.check_output(['systemctl','show',name,'--property=MainPID','--value']).decode().strip() for name in services}
days = {}
for day in ('20261008','20261009'):
    subset = [r for r in rows if r['id'].startswith(day)]
    days[day] = dict(total=len(subset), unreviewed_eligible=sum(r['eligible'] for r in subset), reviewed=sum(bool(r['label']) for r in subset), status_counts=dict(collections.Counter(r['status'] for r in subset)), anomaly_candidates=sum(r['anomaly'] for r in subset))
result = dict(observed_at=datetime.now(timezone.utc).isoformat(), total=len(rows), days_utc=days, eligible_total=sum(r['eligible'] for r in rows), queue=[r['id'] for r in rows if r['eligible']][:20], protected_hashes=hashes, service_pids=pids)
if len(sys.argv)>1 and sys.argv[1]=='after':
    def get(path):
        with urllib.request.urlopen('http://127.0.0.1:8080'+path, timeout=30) as response: return json.load(response)
    queue = get('/api/tower?review=anomaly_candidate')['recent_captures']
    assert [r['recording'] for r in queue] == result['queue']
    assert all(atis_view.needs_tower_review(r) for r in queue)
    assert [r['recording'] for r in get('/api/tower?review=candidate_voice')['recent_captures']] == result['queue']
    history = get('/api/tower')['recent_captures']
    assert [r['recording'] for r in history] == [r['id'] for r in rows[:20]]
    result['live_api'] = dict(queue_count=len(queue), history_count=len(history), historical_reviews=len(get('/api/tower/reviews')['reviews']), compatible_alias=True)
print(json.dumps(result,indent=2))

