"""One kernel-owned HTP lease, shared by production and shadow inference.

Never unlink the lock inode. Children inherit the lease, so a supervisor crash
cannot unlock an accelerator that is still executing. Kernel exit closes it.
"""
import contextlib
import fcntl
import json
import os
from pathlib import Path
import subprocess
import time
import uuid

ROOT = Path(__file__).resolve().parent

def identity(pid=None):
    pid = pid or os.getpid()
    try:
        return {'pid': pid, 'start': Path('/proc/%d/stat' % pid).read_text().rsplit(')',1)[1].split()[19],
                'boot': Path('/proc/sys/kernel/random/boot_id').read_text().strip()}
    except OSError:
        return None

def alive(owner):
    return bool(owner and identity(owner.get('pid')) == {k: owner.get(k) for k in ('pid','start','boot')})

def atomic(path, data):
    temp = path.with_name(path.name+'.'+uuid.uuid4().hex+'.tmp')
    with temp.open('w') as stream:
        json.dump(data,stream,indent=2); stream.flush(); os.fsync(stream.fileno())
    temp.replace(path)

def directory(root):
    p=Path(root)/'data/inference'; p.mkdir(parents=True,exist_ok=True); return p

def production_waiting(root=ROOT):
    for p in directory(root).glob('wait-*.json'):
        try:
            if alive(json.loads(p.read_text())): return True
            p.unlink(missing_ok=True)
        except (OSError, ValueError):
            # A corrupt waiter is bounded by age, not a permanent priority veto.
            if p.exists() and time.time()-p.stat().st_mtime>30: p.unlink(missing_ok=True)
    return False

@contextlib.contextmanager
def lease(owner, timeout=20, production=True, root=ROOT, cancel=lambda:False):
    base=directory(root); handle=(base/'htp.lock').open('a+')
    waiter=base/('wait-'+uuid.uuid4().hex+'.json')
    if production: atomic(waiter,identity())
    acquired=False; deadline=time.monotonic()+timeout
    try:
        while True:
            if cancel(): raise InterruptedError('Inference lease cancelled')
            if not production and production_waiting(root): raise InterruptedError('Production inference waiting')
            try:
                fcntl.flock(handle,fcntl.LOCK_EX|fcntl.LOCK_NB); acquired=True; break
            except BlockingIOError:
                if time.monotonic()>=deadline: raise TimeoutError('HTP inference lease busy: '+owner)
                time.sleep(.1)
        atomic(base/'owner.json',dict(identity(),owner=owner,acquired_at=time.time()))
        print('HTP lease acquired: '+owner+' pid='+str(os.getpid()),flush=True)
        yield handle.fileno()
    finally:
        waiter.unlink(missing_ok=True)
        # Do not explicitly LOCK_UN: an inherited child fd must retain ownership.
        handle.close()
        if acquired: print('HTP lease released by supervisor: '+owner,flush=True)

class LockedPopen(subprocess.Popen):
    """Popen-compatible production entry; preserve the actual native child PID."""
    def __init__(self, *args, **kwargs):
        self._lease=lease('production:'+str(args[0][0]))
        fd=self._lease.__enter__()
        kwargs['pass_fds']=tuple(kwargs.get('pass_fds',()))+(fd,)
        try: super().__init__(*args,**kwargs)
        except BaseException:
            self._release(); raise
    def _release(self):
        cm=self._lease; self._lease=None
        if cm: cm.__exit__(None,None,None)
    def poll(self):
        result=super().poll()
        if result is not None: self._release()
        return result
    def wait(self,*args,**kwargs):
        result=super().wait(*args,**kwargs); self._release(); return result

def run(argv, **kwargs):
    """Bounded Genie invocation, with subprocess.run-compatible result."""
    timeout=kwargs.pop('timeout',120); check=kwargs.pop('check',False)
    if kwargs.pop('capture_output',False): kwargs.update(stdout=subprocess.PIPE,stderr=subprocess.PIPE)
    with LockedPopen(argv,**kwargs) as proc:
        try: out,err=proc.communicate(timeout=timeout)
        except BaseException:
            proc.kill(); proc.communicate(); raise
        result=subprocess.CompletedProcess(argv,proc.returncode,out,err)
        if check: result.check_returncode()
        return result
