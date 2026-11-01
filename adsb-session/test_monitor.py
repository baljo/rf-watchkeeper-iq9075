import importlib.util
import json
from pathlib import Path
import sqlite3
import tempfile
import time
import unittest

spec=importlib.util.spec_from_file_location('monitor', Path(__file__).with_name('monitor.py'))
m=importlib.util.module_from_spec(spec); spec.loader.exec_module(m)

class MonitorTests(unittest.TestCase):
    def test_session_scope_completion_and_privacy(self):
        with tempfile.TemporaryDirectory() as directory:
            p=Path(directory); sid='20261101T190045Z'; (p/sid).mkdir()
            lease=dict(session=sid,start=time.time()-100,expiry=time.time()+100,phase='capturing',attempts=1,before={'rf-watchkeeper-scheduler.service':dict(ActiveState='active',UnitFileState='enabled')})
            m.atomic(p/'lease.json',lease)
            m.atomic(p/sid/'health.json',dict(utc=m.dt.datetime.now(m.dt.timezone.utc).isoformat(),attempt=1,decoder_stats=dict(samples_processed=24000000,samples_dropped=0)))
            with sqlite3.connect(p/'aircraft.sqlite') as db:
                db.executescript('CREATE TABLE frames(session,utc,icao); CREATE TABLE snapshots(session,utc,kind,json);')
                utc=m.dt.datetime.now(m.dt.timezone.utc).isoformat()
                db.execute('INSERT INTO frames VALUES(?,?,?)',('other',utc,'ffffff'))
                db.execute('INSERT INTO frames VALUES(?,?,?)',(sid,utc,'abcdef'))
                db.execute('INSERT INTO snapshots VALUES(?,?,?,?)',(sid,utc,'aircraft',json.dumps(dict(now=time.time(),aircraft=[dict(hex='abcdef',seen=0,flight='<script>',lat=1,lon=2)]))))
                db.execute('INSERT INTO snapshots VALUES(?,?,?,?)',(sid,utc,'stats',json.dumps(dict(total=dict(local=dict(samples_processed=24000000,samples_dropped=0))))))
            def services(u):
                return dict(ActiveState='inactive' if 'scheduler' in u else 'active',UnitFileState='enabled')
            s=m.observe(p,services)
            self.assertEqual(s['unique_aircraft'],1); self.assertEqual(s['valid_frames'],1)
            self.assertEqual(s['aircraft_with_decoded_positions'],1)
            self.assertNotIn('lat',s['recent_aircraft'][0]); self.assertEqual(s['status'],'Receiving valid aircraft messages')
            lease.update(phase='restored',restored_at=utc)
            m.atomic(p/(sid+'-restored.json'),lease); (p/'lease.json').unlink()
            s=m.observe(p,lambda u:dict(ActiveState='active',UnitFileState='enabled'))
            self.assertTrue(s['completed']); self.assertTrue(s['report']['ready'])
            self.assertEqual(s['report']['database_integrity'],'ok')
            self.assertTrue((p/(sid+'-health-summary.json')).exists())

    def test_empty_and_stale(self):
        with tempfile.TemporaryDirectory() as directory:
            p=Path(directory); sid='20261101T190045Z'; (p/sid).mkdir()
            m.atomic(p/'lease.json',dict(session=sid,start=time.time()-100,expiry=time.time()+100,phase='capturing'))
            h=dict(utc=m.dt.datetime.now(m.dt.timezone.utc).isoformat(),attempt=1,decoder_stats=dict(samples_processed=1))
            m.atomic(p/sid/'health.json',h)
            with sqlite3.connect(p/'aircraft.sqlite') as db:
                db.executescript('CREATE TABLE frames(session,utc,icao); CREATE TABLE snapshots(session,utc,kind,json);')
            fn=lambda u:dict(ActiveState='active')
            self.assertEqual(m.observe(p,fn)['status'],'Healthy receiver — no valid messages yet')
            h['utc']='2020-01-01T00:00:00+00:00'; m.atomic(p/sid/'health.json',h)
            self.assertEqual(m.observe(p,fn)['status'],'Stale receiver health')
            lease=m.read(p/'lease.json'); lease['abort']='fixture early abort'; m.atomic(p/'lease.json',lease)
            m.observe(p,fn)
            alert=m.read(p/(sid+'-health-alert.json'))
            self.assertEqual(alert['database_integrity'],'ok')
            self.assertIn('failure',alert['status'])
            lease['phase']='restored'; m.atomic(p/(sid+'-restored.json'),lease); (p/'lease.json').unlink()
            result=m.observe(p,fn)
            self.assertTrue(result['report']['ready']); self.assertEqual(result['unique_aircraft'],0)

    def test_read_only_connection(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'test.sqlite'
            db=sqlite3.connect(path); db.execute('CREATE TABLE test(value)'); db.commit(); db.close()
            with m.connect(path) as reader:
                with self.assertRaises(sqlite3.OperationalError):
                    reader.execute('INSERT INTO test VALUES(1)')

    def test_missing_session(self):
        with tempfile.TemporaryDirectory() as directory:
            self.assertEqual(m.observe(Path(directory))['status'],'No ADS-B session')
            sid='20261101T190045Z'
            m.atomic(Path(directory)/(sid+'-restored.json'),dict(session=sid,start=0,expiry=1,phase='restored',abort='startup failure'))
            result=m.observe(Path(directory),lambda u:dict(ActiveState='inactive'))
            self.assertTrue(result['report']['ready'])
            self.assertIn('Unavailable',result['report']['database_integrity'])

if __name__=='__main__': unittest.main()
