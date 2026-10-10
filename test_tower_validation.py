import unittest
import tempfile
import json
from pathlib import Path
import tower_validation as v

class ValidationTests(unittest.TestCase):
    def test_duration_union_and_gaps(self):
        windows=[dict(start_seconds=s,score=50) for s in (0,0.5,3)]
        p=v.persistence(windows,45)
        self.assertEqual(p['longest_run_windows'],2)
        self.assertEqual(p['anomalous_union_seconds'],2.5)
        self.assertEqual(p['longest_run_span_seconds'],1.5)

    def test_weak_voice_missing_evidence_and_label_updates(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);b=root/'evaluation/tower-anomaly';(b/'human-review').mkdir(parents=True);(b/'shadow').mkdir();(root/'docs').mkdir()
            cid='20261007T000000Z';path=b/'human-review'/(cid+'.json')
            path.write_text(json.dumps(dict(capture_id=cid,peak_score=54,median_score=40,threshold=45,human_review_label='confirmed_voice')))
            a=v.snapshot(root)
            self.assertEqual(a['rules']['peak_gt_55']['false_negatives'],[cid])
            self.assertEqual(a['rules']['run_ge_2']['unknown_ids'],[cid])
            self.assertTrue(a['formal_analysis_triggers'])
            (b/'shadow'/(cid+'.json')).write_text(json.dumps(dict(summary=dict(count=2,p100=54),threshold=45,windows=[dict(start_seconds=0,score=54),dict(start_seconds=0.5,score=48)])))
            a=v.snapshot(root);self.assertEqual(a['rules']['peak55_or_run2']['recall'],1)
            row=json.loads(path.read_text());row['human_review_label']='no_voice';path.write_text(json.dumps(row))
            a=v.snapshot(root);self.assertEqual(a['total_reviewed'],1);self.assertEqual(a['label_counts']['confirmed_voice'],0)

if __name__=='__main__':unittest.main()
