import json
import sqlite3
import tempfile
import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch
import atis_validation as v


class CapacityTests(unittest.TestCase):
    def test_concurrent_requests_share_snapshot_and_save_invalidates(self):
        v.invalidate_dashboard()
        def snapshot(root):
            time.sleep(.02)
            return {'captures': []}
        with patch.object(v, 'snapshot', side_effect=snapshot) as build:
            with ThreadPoolExecutor(max_workers=4) as pool:
                bodies=list(pool.map(lambda _: v.dashboard_response(Path('/tmp/cache-fixture'), 'test-token'),range(4)))
            self.assertEqual(build.call_count,1)
            self.assertTrue(all(body==bodies[0] for body in bodies))
            self.assertEqual(json.loads(bodies[0])['control_token'],'test-token')
            with patch('tower_retention.lock'), patch.object(v, '_save', return_value={'saved': True}):
                v.save({},Path('/tmp/cache-fixture'))
            v.dashboard_response(Path('/tmp/cache-fixture'), 'test-token')
            self.assertEqual(build.call_count,2)
        v.invalidate_dashboard()

    def fixture(self, root, selected):
        source = root / 'data/atis-shadow/jobs.sqlite3'
        source.parent.mkdir(parents=True)
        with sqlite3.connect(str(source)) as c:
            c.execute('CREATE TABLE jobs(capture_id TEXT,state TEXT,result TEXT)')
        with v.db(root) as c:
            for i in range(selected + 3):
                cid = '20261015T000000.%06dZ' % i
                folder = root / 'recordings/atis' / cid
                folder.mkdir(parents=True)
                (folder / 'raw.wav').write_bytes(b'fixture')
                data = dict(eligible=True, audio_sha256=str(i),
                            production_raw_transcript='unique %d' % i,
                            shadow_raw_transcript='different %d' % i,
                            production_fields=v.extract(''), shadow_fields=v.extract(''))
                c.execute('INSERT INTO captures(id,state,rank,data,updated) VALUES (?,?,?,?,?)',
                          (cid, 'needs_review' if i < selected else 'candidate',
                           100-i, json.dumps(data), time.time()))

    def test_full_queue_does_not_compare_or_change_records(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.fixture(root, 10)
            with v.db(root) as c:
                before = [tuple(r) for r in c.execute('SELECT * FROM captures ORDER BY id')]
            with patch.object(v.difflib, 'SequenceMatcher', side_effect=AssertionError('full queue compared')):
                v.sync(root)
                v.sync(root)
            with v.db(root) as c:
                self.assertEqual(before, [tuple(r) for r in c.execute('SELECT * FROM captures ORDER BY id')])

    def test_free_slot_is_filled_then_comparisons_stop(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.fixture(root, 9)
            with patch.object(v.difflib, 'SequenceMatcher') as matcher:
                matcher.return_value.ratio.return_value = 0
                v.sync(root)
                self.assertEqual(matcher.call_count, 18)
            with v.db(root) as c:
                self.assertEqual(c.execute("SELECT count(*) FROM captures WHERE state='needs_review'").fetchone()[0], 10)

    def test_duplicate_does_not_take_free_slot(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.fixture(root, 9)
            with patch.object(v.difflib, 'SequenceMatcher') as matcher:
                matcher.return_value.ratio.return_value = 1
                v.sync(root)
            with v.db(root) as c:
                self.assertEqual(c.execute("SELECT count(*) FROM captures WHERE state='needs_review'").fetchone()[0], 9)
                candidates = c.execute("SELECT data FROM captures WHERE state='candidate'").fetchall()
                self.assertTrue(all(json.loads(r[0])['duplicate_of'] for r in candidates))


if __name__ == '__main__':
    unittest.main()
