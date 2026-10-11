"""Privacy-safe live read-only HTTP/service acceptance snapshot."""
import collections
import json
import subprocess
from urllib.request import urlopen
from datetime import datetime, timezone
from pathlib import Path
import sys
sys.path.insert(0, '/root/rf-watchkeeper')
from tower_review_policy import selection_reason

result=dict(observed_utc=datetime.now(timezone.utc).isoformat(),api={})
for path in ('/api/tower?review=anomaly_candidate','/api/state','/api/atis','/api/meteor/schedule'):
    try:
        with urlopen('http://localhost:8080'+path,timeout=25) as response:
            data=json.load(response)
            item=dict(status=response.status)
            if path.startswith('/api/tower'):
                rows=data['recent_captures']
                reasons=collections.Counter(selection_reason(row) for row in rows)
                assert None not in reasons
                assert all(row.get('audio_available') for row in rows)
                item.update(displayed=len(rows),selection_reasons=dict(reasons),all_eligible=True)
            result['api'][path]=item
    except Exception as error:
        result['api'][path]=dict(error=type(error).__name__)
result['services']=subprocess.check_output(['systemctl','is-active','rf-watchkeeper-dashboard.service',
    'rf-watchkeeper-scheduler.service','rf-watchkeeper-atis-process.service',
    'rf-watchkeeper-atis-shadow.service','rf-watchkeeper-tower-anomaly-shadow.timer'],text=True).splitlines()
result['automatic_worker']=subprocess.check_output(['systemctl','show',
    'rf-watchkeeper-tower-anomaly-shadow.service','-p','Result','-p','ExecMainStartTimestamp'],text=True).splitlines()
html=(Path('/root/rf-watchkeeper')/'dashboard.html').read_bytes()
result['ui_wording_present']=all(text in html for text in
    (b'Detector threshold: 45.6744 (unchanged)',b'8% reproducible audit',b'review gate 55 + 2 adjacent windows'))
print(json.dumps(result,indent=2))
