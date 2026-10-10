"""Isolated safety checks: no receiver, real recordings, scheduler or HTP."""
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from unittest import mock
import wave
import atis_shadow as sh
import inference_resource as ir

class Safety(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
        self.folder=self.root/'recordings/atis/20261007T000000.000000Z';self.folder.mkdir(parents=True)
        with wave.open(str(self.folder/'raw.wav'),'wb') as w:
            w.setparams((1,2,8000,0,'NONE','not compressed'));w.writeframes(b'\x01\x00'*32000)
        (self.folder/'capture.json').write_text(json.dumps({'status':'ready','source':'live','kind':'atis'}))
        (self.folder/'processed.json').write_text('{"status":"completed"}')
        (self.folder/'transcript.json').write_text('{"segments":[{"text":"production unchanged","raw":{"text":"[0ms - 1ms] production unchanged"}}]}')
        self.original=sh.digest(self.folder/'raw.wav');sh.enqueue(self.folder,self.root)
    def tearDown(self):self.temp.cleanup()
    def row(self):
        with sh.database(self.root) as db:return dict(db.execute('SELECT * FROM jobs').fetchone())
    def fake(self, kind='success'):
        def cmd(scratch,out):
            if kind=='crash':return [sys.executable,'-c','raise RuntimeError("injected failure")']
            if kind=='hang':return [sys.executable,'-c','import time;time.sleep(60)']
            record={'rows':[{'input_sha256':sh.digest(p),'eot_reached':True} for p in sorted(scratch.glob('clip-*.wav'))],
                'text':'candidate','wall_seconds':.1,'encoder_accel_execute_us':[1],'decoder_accel_execute_us':[1],
                'mapped_libraries':['/usr/lib/libQnnHtp.so']}
            code='from pathlib import Path; p=Path('+repr(str(out))+');p.mkdir();(p/"record.json").write_text('+repr(json.dumps(record))+')'
            return [sys.executable,'-c',code]
        return cmd
    def run_attempt(self,kind='success',guard=lambda:None):
        sh.attempt(self.row(),threading.Event(),self.root,guard,self.fake(kind))
    def test_normal_separate_and_unique(self):
        self.run_attempt();self.assertEqual(self.row()['state'],'completed')
        sh.enqueue(self.folder,self.root);self.assertEqual(self.row()['attempts'],1)
        self.assertEqual(sh.digest(self.folder/'raw.wav'),self.original)
        self.assertEqual(json.loads((self.folder/'transcript.json').read_text())['segments'][0]['text'],'production unchanged')
        self.assertEqual(json.loads(self.row()['result'])['production_raw_transcript'],'[0ms - 1ms] production unchanged')
    def test_contention_and_stale_metadata(self):
        with ir.lease('other',production=False,root=self.root):
            self.run_attempt();self.assertEqual(self.row()['state'],'deferred');self.assertEqual(self.row()['attempts'],0)
        ir.atomic(ir.directory(self.root)/'owner.json',{'pid':999999,'owner':'stale'})
        self.run_attempt();self.assertEqual(self.row()['state'],'completed')
    def test_crash_bounded_and_production_preserved(self):
        for _ in range(3):self.run_attempt('crash')
        self.assertEqual(self.row()['state'],'failed');self.assertFalse(sh.retention_hold(self.folder,self.root))
        result=json.loads(self.row()['result']);self.assertEqual(result['audio_sha256'],self.original)
        self.assertEqual(result['state'],'failed');self.assertTrue(result['runtime_log'])
        self.assertEqual(sh.digest(self.folder/'raw.wav'),self.original)
        self.assertTrue((self.folder/'processed.json').exists())
    def test_retry_then_one_result(self):
        self.run_attempt('crash');self.run_attempt();sh.enqueue(self.folder,self.root)
        self.assertEqual(self.row()['state'],'completed');self.assertEqual(self.row()['attempts'],2)
        with sh.database(self.root) as db:self.assertEqual(db.execute('SELECT count(*) FROM jobs').fetchone()[0],1)
    def test_preemption_restart(self):
        started=time.monotonic()
        self.run_attempt('hang',lambda:'Satellite reservation' if time.monotonic()-started>1 else None)
        self.assertEqual(self.row()['state'],'deferred');self.assertIn('Satellite',self.row()['reason'])
        self.run_attempt();self.assertEqual(self.row()['state'],'completed')
    def test_timeout(self):
        old=sh.TIMEOUT;sh.TIMEOUT=.1
        try:self.run_attempt('hang')
        finally:sh.TIMEOUT=old
        self.assertEqual(self.row()['state'],'deferred');self.assertIn('timeout',self.row()['reason'])
    def test_worker_recovery_and_reboot_identity(self):
        sh.update(self.folder.name,'running',root=self.root,child={'pid':os.getpid(),'boot':'prior-boot','start':'bad'})
        sh.recover(self.root);self.assertEqual(self.row()['state'],'deferred')
        self.run_attempt();self.assertEqual(self.row()['state'],'completed')
    def test_production_waiter_priority(self):
        marker=ir.directory(self.root)/'wait-test.json';ir.atomic(marker,ir.identity())
        with self.assertRaises(InterruptedError):
            with ir.lease('shadow',production=False,root=self.root):pass
        ir.atomic(marker,{'pid':999999,'boot':'old','start':'0'});self.assertFalse(ir.production_waiting(self.root))
    def test_actual_production_waiter_acquires_after_preempt(self):
        acquired=threading.Event()
        def production():
            with ir.lease('production-test',timeout=3,root=self.root):acquired.set()
        with ir.lease('shadow-test',production=False,root=self.root):
            thread=threading.Thread(target=production);thread.start()
            deadline=time.monotonic()+2
            while not ir.production_waiting(self.root) and time.monotonic()<deadline:time.sleep(.05)
            self.assertTrue(ir.production_waiting(self.root));self.assertFalse(acquired.is_set())
        thread.join(3);self.assertTrue(acquired.is_set())
    def test_inherited_fd_stays_locked_after_supervisor_crash(self):
        code='import sys,subprocess;sys.path.insert(0,'+repr(str(sh.ROOT))+');import inference_resource as ir;cm=ir.lease("parent",production=False,root='+repr(str(self.root))+');fd=cm.__enter__();p=subprocess.Popen(["sleep","2"],pass_fds=(fd,));print("child",p.pid,flush=True);import time;time.sleep(60)'
        parent=subprocess.Popen([sys.executable,'-c',code],stdout=subprocess.PIPE,text=True)
        try:
            while True:
                line=parent.stdout.readline()
                if line.startswith('child '):break
            parent.kill();parent.wait()
            with self.assertRaises(TimeoutError):
                with ir.lease('probe',timeout=.2,production=False,root=self.root):pass
            time.sleep(2)
            with ir.lease('recovered',timeout=.5,production=False,root=self.root):pass
        finally:
            if parent.poll() is None:parent.kill();parent.wait()
            parent.stdout.close()
    def test_retention_hold_expires_without_unpinning(self):
        self.assertTrue(sh.retention_hold(self.folder,self.root))
        with sh.database(self.root) as db:db.execute('UPDATE jobs SET created=?',(time.time()-sh.MAX_AGE-1,))
        self.assertFalse(sh.retention_hold(self.folder,self.root));self.assertEqual(sh.digest(self.folder/'raw.wav'),self.original)
    def test_production_finishes_when_shadow_enqueue_crashes(self):
        import atis_pipeline as ap
        (self.root/'data').mkdir(exist_ok=True)
        def native(argv,log_path,stop,**kwargs):
            log_path.write_text('CLEANUP_COMPLETE\n')
            if '--output-name' in argv:
                output=Path(argv[argv.index('--output-name')+1]);output.mkdir()
                inputs=Path(argv[argv.index('--input-dir')+1])
                record={'text':'Wind two seven zero degrees QNH nine nine six','rows':[{'input_sha256':sh.digest(p),'eot_reached':True} for p in sorted(inputs.glob('clip-*.wav'))], 'encoder_accel_execute_us':[1],'decoder_accel_execute_us':[1],'mapped_libraries':['/usr/lib/libQnnHtp.so']}
                (output/'record.json').write_text(json.dumps(record))
            elif '-o' in argv:
                Path(argv[argv.index('-o')+1]).write_text(json.dumps({'text':'Wind two seven zero degrees QNH nine nine six'}))
            else:raise RuntimeError('Injected Genie failure, independently handled')
        with mock.patch.object(ap,'ROOT',self.root),mock.patch.object(ap,'guarded_run',native),mock.patch.object(sh,'enqueue',side_effect=RuntimeError('Injected shadow database failure')):
            ap.process(self.folder,threading.Event())
        self.assertTrue(json.loads((self.folder/'transcript.json').read_text())['segments'][0]['text'])
        self.assertEqual(json.loads((self.folder/'processed.json').read_text())['status'],'partial_success')
        self.assertEqual(sh.digest(self.folder/'raw.wav'),self.original)
    def test_lock_released_after_crash_child_exit(self):
        code='import sys,time;sys.path.insert(0,'+repr(str(sh.ROOT))+');import inference_resource as ir;cm=ir.lease("crash-owner",root='+repr(str(self.root))+');cm.__enter__();print("ready",flush=True);time.sleep(60)'
        p=subprocess.Popen([sys.executable,'-c',code],stdout=subprocess.PIPE,text=True)
        try:
            while p.stdout.readline().strip()!='ready':pass
            p.kill();p.wait()
            with ir.lease('recovered',timeout=.5,root=self.root):pass
        finally:
            if p.poll() is None:p.kill();p.wait()
            p.stdout.close()

if __name__=='__main__':unittest.main()
