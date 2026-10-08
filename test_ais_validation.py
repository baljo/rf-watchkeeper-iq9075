# Verify AIS outlier rejection, active target timeouts, and identity retention using isolated SQLite data; 2026-10-03 22:52 EEST, Thomas Vikström.
import unittest
import tempfile
import sqlite3
from pathlib import Path
from datetime import datetime, timezone, timedelta
import ais_store as store

class Validation(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parent)
        self.db = Path(self.temp.name)/'test.db'
        self.now = datetime.now(timezone.utc)
        store.observer_position = lambda: (63.08, 21.57)

    def tearDown(self):
        import gc
        gc.collect()
        self.temp.cleanup()

    def report(self, mmsi=230040000, **fields):
        return dict(mmsi=mmsi, timestamp=self.now.isoformat(), type=1, lat=63.1, lon=21.7, speed=12, shipname='AURORA BOTNIA', **fields)

    def test_history_uses_position_time_and_keeps_live_filter(self):
        for mmsi, hours in [(101, 2), (102, 25), (103, 168), (104, 169)]:
            message = self.report(mmsi)
            message['timestamp'] = (self.now-timedelta(hours=hours)).isoformat()
            store.store_target(message, db_path=self.db)
        store.store_target(dict(mmsi=104, type=5, timestamp=self.now.isoformat(), shipname='OLD POSITION'), db_path=self.db)
        self.assertEqual([t['mmsi'] for t in store.historical_targets(24, db_path=self.db, now=self.now)], [101])
        self.assertEqual([t['mmsi'] for t in store.historical_targets(168, db_path=self.db, now=self.now)], [101, 102, 103])
        self.assertEqual(store.historical_targets(168, 1, self.db, self.now)[0]['mmsi'], 101)
        self.assertTrue(all(t['latitude'] is None for t in store.recent_targets(db_path=self.db, now=self.now)))
        with sqlite3.connect(self.db) as con:
            con.execute('UPDATE ais_targets SET latitude=-84.05, longitude=-59.24 WHERE mmsi=101')
        self.assertEqual(store.historical_targets(24, db_path=self.db, now=self.now), [])

    def test_outliers(self):
        self.assertTrue(store.store_target(self.report(), db_path=self.db))
        for lat,lon in [(-84.05,-59.24),(91,20),(63,181),(float('nan'),20),(63,None)]:
            report=self.report(); report.update(lat=lat,lon=lon)
            self.assertFalse(store.store_target(report, db_path=self.db))
        live=store.recent_targets(db_path=self.db,now=self.now)
        self.assertEqual(live[0]['latitude'],63.1)
        self.assertLess(live[0]['distance_km'],20)
        bogus=self.report(463653452); bogus.update(lat=-84.05,lon=-59.24)
        self.assertFalse(store.store_target(bogus,db_path=self.db))
        print('Antarctic MMSI 463653452 rejected; distance %.1f km; nearby map radius remains 20 km' % store.position_distance(-84.05,-59.24))

    def test_timeouts_and_retention(self):
        for mmsi,typ,speed,position,timeout in [(230040000,1,12,True,1800),(2,1,0,True,3600),(3,1,None,True,3600),(2300077,4,None,True,86400),(5,5,None,False,7200)]:
            msg=self.report(mmsi); msg.update(type=typ,speed=speed)
            if not position: msg.update(lat=None,lon=None)
            self.assertTrue(store.store_target(msg,db_path=self.db))
            self.assertIn(mmsi,[t['mmsi'] for t in store.recent_targets(db_path=self.db,now=self.now+timedelta(seconds=timeout))])
            self.assertNotIn(mmsi,[t['mmsi'] for t in store.recent_targets(db_path=self.db,now=self.now+timedelta(seconds=timeout+1))])
            print('MMSI %s active through %s seconds; hidden after boundary' % (mmsi,timeout))
        with sqlite3.connect(self.db) as con: self.assertEqual(con.execute('SELECT count(*) FROM ais_targets').fetchone()[0],5)
        msg=self.report(); msg['timestamp']=(self.now+timedelta(hours=2)).isoformat()
        store.store_target(msg,db_path=self.db)
        with sqlite3.connect(self.db) as con:
            row=con.execute('SELECT count(*),message_count,vessel_name,first_seen FROM ais_targets WHERE mmsi=230040000').fetchone()
            self.assertEqual(row[:3],(1,2,'AURORA BOTNIA')); self.assertEqual(row[3],self.now.isoformat())
        print('All identities retained; returning AURORA BOTNIA updates one existing MMSI')

    def test_static_does_not_refresh_position(self):
        store.store_target(self.report(),db_path=self.db)
        msg=dict(mmsi=230040000,type=5,timestamp=(self.now+timedelta(minutes=40)).isoformat(),shipname='AURORA BOTNIA')
        store.store_target(msg,db_path=self.db)
        target=store.recent_targets(db_path=self.db,now=self.now+timedelta(minutes=40))[0]
        self.assertIsNone(target['latitude'])
        print('Static message keeps identity active while stale position is hidden')

    def test_jump(self):
        store.store_target(self.report(),db_path=self.db)
        msg=self.report(); msg.update(lat=64,timestamp=(self.now+timedelta(seconds=60)).isoformat())
        self.assertFalse(store.store_target(msg,db_path=self.db))
        self.assertEqual(store.recent_targets(db_path=self.db,now=self.now)[0]['latitude'],63.1)
        print('Impossible 100 km jump in 60 seconds rejected; previous position retained')

    def test_backward_compatible_migration(self):
        with sqlite3.connect(self.db) as con:
            con.executescript(store.SCHEMA)
            con.execute(store.UPSERT,(2300077,self.now.isoformat(),self.now.isoformat(),4,'A',63.1,21.7,1,None,None,None,None,None,'REF POINT LERVIKSUDD',None,None))
        row=store.recent_targets(db_path=self.db,now=self.now+timedelta(hours=23))[0]
        self.assertEqual(row['mmsi'],2300077); self.assertIsNotNone(row['latitude'])
        print('Existing schema migrated; historical base station still active at 23 hours')

if __name__ == '__main__': unittest.main(verbosity=2)
