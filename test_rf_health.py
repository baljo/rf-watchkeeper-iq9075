"""Safety tests use temporary databases and controlled processes; never reset SDR/reboot."""
import json
import subprocess
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch
import rf_health as h
import rf_health_monitor as m

class HealthTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.db=Path(self.tmp.name)/'health.db'
        self.db_patch=patch.object(h,'DB',self.db)
        self.db_patch.start()
        self.pause_patch=patch.object(m,'PAUSE',Path(self.tmp.name)/'pause.json')
        self.pause_patch.start()

    def tearDown(self):
        self.db_patch.stop()
        self.pause_patch.stop()
        self.tmp.cleanup()

    def test_quiet_application_and_no_samples(self):
        identity=h.begin('ais',120)
        h.finish(identity,True,12.5,'AIS sample DSP milliseconds',254,application={'messages':0,'status':'quiet'})
        rows=h.snapshot()
        self.assertEqual(rows[0]['status'],'GREEN')
        self.assertEqual(rows[1]['status'],'DISABLED')
        bad=h.begin('ais',120)
        h.finish(bad,True,0,application={'messages':500})
        with h.connect() as db:
            self.assertEqual(db.execute('SELECT capture_ok FROM rf_health_jobs WHERE id=?',(bad,)).fetchone()[0],0)

    def test_hourly_guard_survives_reopen(self):
        self.assertTrue(h.reboot_allowed('test',now=10000))
        self.assertFalse(h.reboot_allowed('test',now=10001))
        self.assertFalse(h.reboot_allowed('test',now=13599))
        self.assertTrue(h.reboot_allowed('test',now=13600))

    def test_active_satellite_no_probe_or_service_action(self):
        with patch.object(h,'control_lock',return_value=__import__('contextlib').nullcontext()), \
             patch.object(h,'satellite_guard',return_value='active METEOR'), \
             patch.object(h,'probe') as probe,patch.object(m,'systemctl') as service:
            self.assertEqual(m.run(force=True),0)
            probe.assert_not_called()
            service.assert_not_called()

    def test_stale_owner_cleanup_controlled_process(self):
        script=Path(self.tmp.name)/'ais_collector.py'
        script.write_text('import time; time.sleep(120)')
        p=subprocess.Popen(['/usr/bin/python3',str(script),'--seconds','1','V4MAIN01'])
        argv=['/usr/bin/python3',str(script),'--seconds','1','V4MAIN01']
        try:
            token=m.age(p.pid)[1]
            with patch.object(m.meteor_recovery,'v4_owners',return_value=[(p.pid,argv)]), \
                 patch.object(h,'satellite_guard',return_value=None):
                self.assertTrue(m.clean_stale('V4MAIN01'))
                self.assertIsNone(p.poll()) # Within dwell: preserve.
                with patch.object(m,'age',return_value=(100,token)), \
                     patch.object(h,'satellite_guard',return_value='METEOR'):
                    self.assertFalse(m.clean_stale('V4MAIN01'))
                    self.assertIsNone(p.poll())
                real_age=m.age
                with patch.object(m,'age',side_effect=lambda pid:(100,real_age(pid)[1])):
                    m.clean_stale('V4MAIN01')
                p.wait(timeout=5)
                self.assertIsNotNone(p.returncode)
        finally:
            if p.poll() is None:
                p.kill();p.wait(timeout=3)

    def test_unknown_owner_is_protected(self):
        self.assertIsNone(m.stale_limit(['rtl_sdr','-d','V4MAIN01','output.cu8']))
        self.assertIsNone(m.stale_limit(['AIS-catcher','-d','V4MAIN01']))
        self.assertEqual(m.stale_limit(['AIS-catcher','-T','120']),150)

    def test_pending_report_cannot_overwrite_success(self):
        identity=h.begin('fm',35)
        h.finish(identity,True,1024,code=-15)
        h.finish(identity,False,reason='generic finalizer')
        with h.connect() as db:
            self.assertEqual(db.execute('SELECT capture_ok FROM rf_health_jobs WHERE id=?',(identity,)).fetchone()[0],1)

    def test_quiet_ais_with_partial_line_is_bounded(self):
        import ais_collector
        script=Path(self.tmp.name)/'fake_sample_processing.py'
        script.write_text('''import signal,time,sys
def stop(*args):
 print("\\n[AIS engine v1 base] 12.50 ms",flush=True)
 sys.exit(0)
signal.signal(signal.SIGINT,stop)
print("partial diagnostic",end="",flush=True)
while True: time.sleep(.05)
''')
        started=time.monotonic()
        with patch.object(ais_collector,'COMMAND',['/usr/bin/python3',str(script)]), \
             patch.object(ais_collector,'write_status'), \
             patch('sys.argv',['ais_collector.py','--seconds','0.4']):
            ais_collector.main()
        self.assertLess(time.monotonic()-started,3)
        with h.connect() as db:
            row=db.execute('SELECT * FROM rf_health_jobs ORDER BY id DESC LIMIT 1').fetchone()
            self.assertEqual(row['capture_ok'],1)
            self.assertEqual(json.loads(row['application_status'])['messages'],0)

    def test_failed_stages_respect_reboot_rate_limit(self):
        from contextlib import nullcontext
        from types import SimpleNamespace
        with patch.object(h,'control_lock',return_value=nullcontext()), \
             patch.object(h,'satellite_guard',return_value=None), \
             patch.object(m,'approaching',return_value=(float('inf'),None)), \
             patch.object(h,'probe',return_value=False) as probe, \
             patch.object(h,'reboot_allowed',return_value=False) as reboot_guard, \
             patch.object(m,'clean_stale',return_value=True), \
             patch.object(m.meteor_recovery,'v4_owners',return_value=[]), \
             patch.object(m.watchkeeper,'device_lock',side_effect=lambda serial:nullcontext()), \
             patch.object(m.subprocess,'run',return_value=SimpleNamespace(returncode=0)), \
             patch.object(m,'systemctl',return_value=SimpleNamespace(stdout='')) as systemctl:
            self.assertEqual(m.run(force=True),0)
            self.assertEqual(probe.call_count,4)
            reboot_guard.assert_called_once()
            self.assertNotIn(('reboot',),[call.args for call in systemctl.call_args_list])
            self.assertIn(('start',m.SCHEDULER),[call.args for call in systemctl.call_args_list])
        self.assertFalse(m.PAUSE.exists())

    def test_restore_after_interrupted_health_service(self):
        m.PAUSE.write_text(json.dumps({'restore':True,'boot_id':h.boot_id()}))
        with patch.object(h,'satellite_guard',return_value='METEOR'),patch.object(m,'systemctl') as service:
            m.restore_scheduler()
            service.assert_not_called()
            self.assertTrue(m.PAUSE.exists())
        with patch.object(h,'satellite_guard',return_value=None),patch.object(m,'systemctl') as service:
            m.restore_scheduler()
            service.assert_called_once_with('start',m.SCHEDULER)
            self.assertFalse(m.PAUSE.exists())

    def test_scheduler_hard_timeout_cleans_process_group(self):
        import job_manager
        import threading
        from types import SimpleNamespace
        real_popen=subprocess.Popen
        children=[]
        def dummy(*args,**kwargs):
            child=real_popen(['/usr/bin/python3','-c','import time;time.sleep(60)'],start_new_session=True)
            children.append(child)
            return child
        identity=h.begin('ais-timeout-simulation',.01)
        publisher=SimpleNamespace(mode='live',tick=lambda:None)
        try:
            with patch.object(job_manager.subprocess,'Popen',side_effect=dummy), \
                 patch.object(job_manager.time,'monotonic',side_effect=[0,100]):
                result=job_manager.execute({'device':'V4MAIN01'},
                    {'mode':'ais','dwell_seconds':.01,'_rf_health_id':identity},
                    Path(self.tmp.name),threading.Event(),publisher)
            self.assertFalse(result)
            self.assertIsNotNone(children[0].poll())
            with h.connect() as db:
                row=db.execute('SELECT * FROM rf_health_jobs WHERE id=?',(identity,)).fetchone()
                self.assertEqual(row['capture_ok'],0)
                self.assertIn('hard timeout',row['failure_reason'])
        finally:
            for child in children:
                if child.poll() is None:
                    child.kill();child.wait(timeout=3)

    def test_intentional_scheduler_stop_exits_cleanly(self):
        import job_manager
        import threading
        from types import SimpleNamespace
        stop=threading.Event()
        job={'id':'ais','name':'AIS','enabled':True,'mode':'ais','frequency_hz':162000000,'dwell_seconds':120}
        publisher=SimpleNamespace(mode='live',transition=lambda *args,**kwargs:None)
        def interrupted(*args):
            stop.set()
            return False
        with patch.object(job_manager,'dependency_error',return_value=None), \
             patch.object(job_manager,'execute',side_effect=interrupted):
            result=job_manager.schedule({'device':'V4MAIN01','jobs':[job]},Path(self.tmp.name),stop,publisher,cycles=1)
        self.assertEqual(result,0)
        with h.connect() as db:
            row=db.execute('SELECT * FROM rf_health_jobs ORDER BY id DESC LIMIT 1').fetchone()
            self.assertIsNone(row['capture_ok'])
            self.assertIsNotNone(row['completion_time'])

if __name__=='__main__':
    unittest.main()
