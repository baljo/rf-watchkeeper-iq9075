import array
import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch, Mock
import adaptive_rf
import job_manager
import atis_pipeline

TOWER=dict(id='tower',name='Tower',mode='am',frequency_hz=120950000,dwell_seconds=15,interval_seconds=60,tower_recording=True,adaptive_tower=True,enabled=True)
ATIS=dict(id='atis',name='ATIS',mode='am',frequency_hz=136450000,dwell_seconds=90,interval_seconds=600,atis_recording=True,enabled=True)
AIS=dict(id='ais',name='AIS',mode='ais',frequency_hz=162000000,dwell_seconds=45,enabled=True)

class AdaptiveTests(unittest.TestCase):
    def choose(self,now,tower=0,atis=0,available=lambda j:True):
        return adaptive_rf.choose([TOWER,ATIS,AIS],now,lambda j:tower if j.get('tower_recording') else atis,available)
    def test_due_atis_then_tower_then_ais(self):
        self.assertEqual(self.choose(600)['id'],'atis')
        self.assertEqual(self.choose(600,atis=600)['id'],'tower')
        self.assertEqual(self.choose(600,tower=600,atis=600)['id'],'ais')
    def test_filler_finishes_at_next_tower_due(self):
        self.assertEqual(self.choose(15,tower=0,atis=0)['dwell_seconds'],45)
        self.assertEqual(self.choose(50,tower=0,atis=0)['dwell_seconds'],10)
    def test_window_preserved_and_no_backlog(self):
        self.assertEqual(self.choose(200,available=lambda j:not j.get('tower_recording'))['id'],'ais')
        self.assertEqual(self.choose(500,tower=500,atis=500)['id'],'ais')
    def test_corrupt_missing_and_future_cadence_recovery(self):
        with tempfile.TemporaryDirectory() as d:
            output=Path(d)
            self.assertEqual(job_manager.last_slot(TOWER,output),0)
            atis_pipeline.slot_path(TOWER,output).write_text('broken')
            self.assertGreater(job_manager.last_slot(TOWER,output),0)
            self.assertFalse(atis_pipeline.due(TOWER,output))
    def feed(self,hold,seconds,level):
        hold.feed(array.array('h',[level,-level]*int(8000*seconds/2)).tobytes())
    def test_silence_dc_and_click_do_not_extend(self):
        h=adaptive_rf.TowerHold(8000,TOWER)
        h.feed(array.array('h',[2000]*8000).tobytes())
        self.feed(h,.2,2000);self.feed(h,14,0)
        self.assertFalse(h.triggered);self.assertEqual(h.duration(),15)
    def test_weak_energy_extends_without_asr_and_quiet_tail(self):
        h=adaptive_rf.TowerHold(8000,TOWER)
        self.feed(h,13,0);self.feed(h,2,45)
        self.assertTrue(h.triggered);self.assertAlmostEqual(h.duration(),25)
        self.feed(h,10,0);self.assertAlmostEqual(h.duration(),25)
    def test_continuous_noise_is_bounded(self):
        h=adaptive_rf.TowerHold(8000,TOWER)
        self.feed(h,90,50);self.assertEqual(h.duration(),75)
    def test_activity_resumes_tail(self):
        h=adaptive_rf.TowerHold(8000,TOWER)
        self.feed(h,14,100);self.feed(h,5,0);self.feed(h,1,100)
        self.assertEqual(h.duration(),30)
    def test_schedule_executes_one_due_backend_at_a_time(self):
        # Single synchronous backend owns the slot; chooser runs only after it releases.
        stop=threading.Event();calls=[]
        with tempfile.TemporaryDirectory() as d:
            out=Path(d);pub=Mock(mode='simulation')
            def execute(config,job,*args):
                calls.append(job['id']);stop.set();return True
            with patch.object(job_manager,'execute',side_effect=execute):
                job_manager.schedule(dict(adaptive_hopping=True,jobs=[TOWER,ATIS,AIS]),out,stop,pub)
            self.assertEqual(calls,['atis'])
    def test_meteor_guard_opens_nothing_and_does_not_reserve(self):
        stop=threading.Event()
        with tempfile.TemporaryDirectory() as d:
            out=Path(d);pub=Mock(mode='live')
            with patch.object(atis_pipeline,'satellite_reason',return_value='Satellite managed reservation: test'),patch.object(job_manager,'execute') as run,patch.object(job_manager,'wait_slot',side_effect=lambda *a:stop.set()):
                job_manager.schedule(dict(adaptive_hopping=True,jobs=[TOWER,ATIS,AIS]),out,stop,pub)
            run.assert_not_called();self.assertFalse(atis_pipeline.slot_path(TOWER,out).exists())
            self.assertEqual(json.loads((out/'adaptive-metrics.json').read_text())['meteor_skips'],1)
    def test_due_atis_deferred_to_safe_tower_before_meteor(self):
        stop=threading.Event()
        with tempfile.TemporaryDirectory() as d:
            out=Path(d);pub=Mock(mode='live')
            def guard(seconds=0,**kwargs):
                return 'Satellite upcoming' if seconds>30 else None
            def execute(config,job,*args):
                self.assertEqual(job['id'],'tower');stop.set();return True
            with patch.object(atis_pipeline,'satellite_reason',side_effect=guard),patch.object(job_manager,'in_window',return_value=True),patch.object(job_manager,'dependency_error',return_value=None),patch.object(job_manager,'execute',side_effect=execute),patch.object(job_manager.rf_health,'begin',return_value=1),patch.object(job_manager.rf_health,'cancel'),patch.object(job_manager.rf_health,'finish'):
                job_manager.schedule(dict(adaptive_hopping=True,jobs=[TOWER,ATIS,AIS]),out,stop,pub)
            self.assertFalse(atis_pipeline.slot_path(ATIS,out).exists())
    def test_capture_guard_prevents_receiver_open(self):
        with patch.object(atis_pipeline,'satellite_reason',return_value='Satellite test'),patch.object(atis_pipeline.subprocess,'Popen') as run:
            self.assertEqual(atis_pipeline.capture({},TOWER,threading.Event(),Mock()),'skipped')
            run.assert_not_called()
    def capture_fixture(self, active_until=0, meteor_at=None):
        with tempfile.TemporaryDirectory() as d:
            clock=[0.0];proc=Mock(returncode=-15);proc.poll.return_value=None
            proc.stdout.fileno.return_value=1
            def read(*args):
                clock[0]+=.02
                level=60 if clock[0] <= active_until else 0
                return array.array('h',[level,-level]*80).tobytes()
            def guard(*args,**kwargs):
                return 'Satellite test reservation' if meteor_at and clock[0]>=meteor_at else None
            job=dict(TOWER)
            with patch.object(atis_pipeline,'ROOT',Path(d)),patch.object(atis_pipeline,'satellite_reason',side_effect=guard),patch.object(atis_pipeline.time,'monotonic',side_effect=lambda:clock[0]),patch.object(atis_pipeline.subprocess,'Popen',return_value=proc),patch.object(atis_pipeline.select,'select',return_value=([1],[],[])),patch.object(atis_pipeline.os,'read',side_effect=read):
                result=atis_pipeline.capture(dict(device='test'),job,threading.Event(),Mock())
            proc.terminate.assert_called_once();proc.wait.assert_called_once()
            report=json.loads(next(Path(d).glob('recordings/tower/*/capture.json')).read_text())
            return result,report
    def test_capture_live_loop_quiet_tail_and_hard_limit(self):
        result,report=self.capture_fixture(active_until=20)
        self.assertTrue(result);self.assertAlmostEqual(report['audio_seconds'],30,delta=.1)
        self.assertTrue(report['activity_extended'])
        result,report=self.capture_fixture(active_until=100)
        self.assertTrue(result);self.assertAlmostEqual(report['audio_seconds'],75,delta=.1)
    def test_capture_active_hold_preempted_and_receiver_reaped(self):
        result,report=self.capture_fixture(active_until=100,meteor_at=18)
        self.assertEqual(result,'skipped');self.assertEqual(report['status'],'interrupted')
        self.assertLess(report['audio_seconds'],20)
    def test_ais_preempted_and_group_reaped(self):
        proc=Mock(pid=123);proc.poll.return_value=None
        pub=Mock(mode='live');stop=threading.Event()
        with patch.object(job_manager.subprocess,'Popen',return_value=proc),patch.object(atis_pipeline,'satellite_reason',return_value='Satellite test'),patch.object(job_manager.os,'killpg') as kill:
            self.assertEqual(job_manager.execute({},dict(AIS),Path('.'),stop,pub),'skipped')
            kill.assert_called_with(123,job_manager.signal.SIGTERM);proc.wait.assert_called()
    def test_managed_trigger_and_post_margin(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);(root/'data/meteor-auto').mkdir(parents=True)
            (root/'data/meteor-auto/plan.json').write_text(json.dumps({'passes':[dict(status='planned',id='test',trigger='1970-01-01T00:01:40Z',record_start='1970-01-01T00:03:20Z',record_stop='1970-01-01T00:05:00Z')]}))
            with patch.object(atis_pipeline.rf_health,'ROOT',root),patch.object(atis_pipeline.rf_health,'satellite_guard',return_value=None),patch.object(atis_pipeline.time,'time',return_value=100):
                self.assertIsNotNone(atis_pipeline.managed_satellite_reason(0,0))
            with patch.object(atis_pipeline.rf_health,'ROOT',root),patch.object(atis_pipeline.rf_health,'satellite_guard',return_value=None),patch.object(atis_pipeline.time,'time',return_value=301):
                self.assertIsNone(atis_pipeline.managed_satellite_reason(0,0))

if __name__=='__main__':unittest.main()
