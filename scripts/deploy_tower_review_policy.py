"""Apply only reviewed HTML text changes, preserving private local map settings."""
from pathlib import Path
import subprocess
import json
root=Path('/root/rf-watchkeeper')
changes=json.loads(Path('/tmp/tower-review-html-changes.json').read_text())
p=root/'dashboard.html'
s=p.read_bytes().decode('utf-8',errors='surrogateescape')
for old,new in changes:
    if old not in s: raise RuntimeError('Expected review wording missing')
    s=s.replace(old,new)
p.write_bytes(s.encode('utf-8',errors='surrogateescape'))
subprocess.run(['systemctl','restart','rf-watchkeeper-dashboard.service'],check=True)
