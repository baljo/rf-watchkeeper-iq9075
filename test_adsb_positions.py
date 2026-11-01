import importlib.util,json,sqlite3,tempfile,time,unittest
from pathlib import Path
from unittest.mock import patch
import adsb_positions as m
class Positions(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.p=Path(self.tmp.name);self.now=time.time();m._cache=(0,None)
  self.status=dict(session='20261101T190045Z',observed_at=self.now,receiver={'ActiveState':'active'},health_age_seconds=1)
  self.write_status();self.db=sqlite3.connect(self.p/'aircraft.sqlite');self.db.execute('CREATE TABLE snapshots(session TEXT,utc TEXT,kind TEXT,json TEXT)')
 def tearDown(self):self.db.close();self.tmp.cleanup()
 def write_status(self): (self.p/'live-status.json').write_text(json.dumps(self.status))
 def add(self,ac,sid='20261101T190045Z'):
  self.db.execute('INSERT INTO snapshots VALUES(?,?,?,?)',(sid,'','aircraft',json.dumps(dict(now=self.now,aircraft=ac))));self.db.commit()
 def ac(self,**kw):return dict(hex='abcdef',lat=10,lon=20,seen_pos=1,seen=1,flight='<script>X</script>',**kw)
 def test_projection_and_readonly(self):
  self.add([self.ac()]);before=(self.p/'aircraft.sqlite').read_bytes();r=m.positions(self.p)['aircraft'][0];self.assertTrue(r['fresh']);self.assertNotIn('<',r['callsign']);self.assertEqual(before,(self.p/'aircraft.sqlite').read_bytes());self.assertNotIn('receiver',r)
 def test_unknown_age_and_invalid(self):
  a=self.ac();a.pop('seen_pos');self.add([a,dict(hex='123456',lat=float('nan'),lon=2)]);r=m.positions(self.p)['aircraft'];self.assertEqual(len(r),1);self.assertFalse(r[0]['fresh']);self.assertIsNone(r[0]['position_time'])
 def test_completed_and_old(self):
  self.status['completed']=True;self.write_status();self.add([self.ac()]);self.assertFalse(m.positions(self.p)['aircraft'][0]['fresh'])
 def test_session_isolation_empty(self):
  self.add([self.ac()],sid='20261101T000000Z');self.assertEqual(m.positions(self.p)['aircraft'],[])
 def test_row_limit(self):
  self.add([self.ac()]);
  for _ in range(5001):self.add([])
  self.assertEqual(m.positions(self.p)['aircraft'],[])
 def test_stale_monitor(self):
  self.status['observed_at']=self.now-100;self.write_status();self.add([self.ac()]);self.assertFalse(m.positions(self.p)['aircraft'][0]['fresh'])
if __name__=='__main__':unittest.main()
