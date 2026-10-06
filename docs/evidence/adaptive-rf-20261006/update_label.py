from pathlib import Path
import hashlib,shutil
p=Path('/root/rf-watchkeeper/dashboard.html');raw=p.read_bytes()
old=b'30 s every ~3 min';new=b'15 s probes about every minute / activity hold up to 75 s'
assert raw.count(old)==1
shutil.copy2(p,'/root/rf-watchkeeper/backups/adaptive-rf-20261006T155400Z/dashboard.html')
changed=raw.replace(old,new);assert changed.replace(new,old)==raw
p.write_bytes(changed);print(hashlib.sha256(changed).hexdigest())
