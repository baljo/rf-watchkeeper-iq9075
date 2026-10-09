import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import atis_view
import tower_anomaly_review
import dashboard
import threading
from functools import partial
from http.server import ThreadingHTTPServer
from urllib.request import Request, urlopen

class QueueTests(unittest.TestCase):
    def test_labels_and_candidate_types(self):
        for status in ('voice_candidate', 'uncertain', 'probably_non_voice'):
            for anomaly in (False, True):
                row = dict(status=status, anomaly_review=dict(anomaly_candidate=anomaly))
                self.assertEqual(bool(atis_view.needs_tower_review(row)), anomaly or status != 'probably_non_voice')
                for label in (*tower_anomaly_review.LABELS, 'confirmed_non_voice'):
                    row['human_review'] = dict(human_review_label=label)
                    self.assertFalse(atis_view.needs_tower_review(row))
                row.pop('human_review')
                row['anomaly_review']['review_state'] = 'confirmed_voice'
                self.assertFalse(atis_view.needs_tower_review(row))

    def test_save_refills_twenty_and_preserves_history(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            for i in range(25):
                p = root/'recordings/tower'/('20261009T1200%02d.000000Z' % i)
                p.mkdir(parents=True)
                (p/'capture.json').write_text('{"status":"ready"}')
                (p/'segmentation.json').write_text('{"status":"activity_detected"}')
            queue = atis_view.recent(root, candidates_only=True)
            self.assertEqual(len(queue), 20)
            self.assertEqual(queue[0]['recording'], '20261009T120024.000000Z')
            target = queue[0]['recording']
            before = (root/'recordings/tower'/target/'capture.json').read_bytes()
            with patch('tower_validation.snapshot'):
                tower_anomaly_review.save(root, dict(capture_id=target, label='no_voice'))
            after = atis_view.recent(root, candidates_only=True)
            self.assertEqual(len(after), 20)
            self.assertNotIn(target, [r['recording'] for r in after])
            self.assertEqual(after[-1]['recording'], '20261009T120004.000000Z')
            history = atis_view.recent(root)
            self.assertEqual(history[0]['human_review']['human_review_label'], 'no_voice')
            self.assertEqual(before, (root/'recordings/tower'/target/'capture.json').read_bytes())
            self.assertTrue(tower_anomaly_review.load(root, target))

    def test_http_save_refills_queue(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            for i in range(21):
                p = root/'recordings/tower'/('20261009T1300%02d.000000Z' % i)
                p.mkdir(parents=True)
                (p/'capture.json').write_text('{}')
                (p/'segmentation.json').write_text('{"status":"activity_detected"}')
            handler = partial(dashboard.Handler, log_path=None, status_path=None,
                transcription_path=None, db_path=None, sensor_status_path=None,
                workflow=None, control_token='fixture-token')
            with patch.object(dashboard, 'ROOT', root), patch('tower_validation.snapshot'):
                server = ThreadingHTTPServer(('127.0.0.1', 0), handler)
                thread = threading.Thread(target=server.serve_forever, daemon=True)
                thread.start()
                try:
                    base = 'http://127.0.0.1:%s' % server.server_port
                    def get(path):
                        with urlopen(base+path) as response: return json.load(response)
                    queue = get('/api/tower?review=anomaly_candidate')['recent_captures']
                    target = queue[0]['recording']
                    request = Request(base+'/api/tower/review', data=json.dumps(dict(capture_id=target,label='confirmed_voice')).encode(),
                        headers={'Content-Type':'application/json','X-Watchkeeper-Token':'fixture-token'})
                    with urlopen(request) as response:
                        self.assertEqual(json.load(response)['human_review_label'], 'confirmed_voice')
                    after = get('/api/tower?review=anomaly_candidate')['recent_captures']
                    self.assertEqual(len(after),20)
                    self.assertNotIn(target,[r['recording'] for r in after])
                    self.assertEqual(after[-1]['recording'],'20261009T130000.000000Z')
                    self.assertEqual(get('/api/tower')['recent_captures'][0]['human_review']['human_review_label'],'confirmed_voice')
                finally:
                    server.shutdown();server.server_close();thread.join()

if __name__ == '__main__':
    unittest.main()
