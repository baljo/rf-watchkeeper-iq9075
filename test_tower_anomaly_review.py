import json
import tempfile
import unittest
from pathlib import Path
import tower_anomaly_review as review
import atis_view

class HumanReviewTests(unittest.TestCase):
    def test_bands(self):
        t=45.67438250526811
        for score, expected in [(t-0.01,'background / below anomaly threshold'),(t,'weak anomaly'),(74.999,'weak anomaly'),(75,'notable anomaly'),(200,'notable anomaly'),(200.01,'strong anomaly')]:
            self.assertEqual(review.severity(score,t),expected)
        with self.assertRaises(ValueError): review.severity(float('nan'),t)

    def test_saved_labels_and_history_are_additive(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory); cid='20261007T132451.116831Z'
            folder=root/'recordings/tower'/cid; folder.mkdir(parents=True)
            originals={'capture.json':{},'processed.json':{'status':'no_activity'},'segmentation.json':{'status':'no_activity'}}
            for name,data in originals.items(): (folder/name).write_text(json.dumps(data))
            before={p.name:p.read_bytes() for p in folder.iterdir()}
            shadow=root/'evaluation/tower-anomaly/shadow';shadow.mkdir(parents=True)
            path=shadow/(cid+'.json')
            def score(value): path.write_text(json.dumps({'mode':'shadow_only','threshold':45.67438250526811,'summary':{'count':1,'p100':value,'p50':40}}))
            score(50)
            for label in review.LABELS:
                result=review.save(root,{'capture_id':cid,'label':label})
                self.assertEqual(result['human_review_label'],label)
                self.assertEqual(result['median_score'],40)
                self.assertEqual(result['vad_result'],originals['segmentation.json'])
                self.assertEqual(atis_view.snapshot(root,'tower',cid)['anomaly_review']['review_state'],label)
            self.assertEqual(len(review.table(root)),1)
            score(20)
            self.assertEqual(len(atis_view.recent(root)),1)
            self.assertEqual(atis_view.recent(root,candidates_only=True),[])
            self.assertEqual(before,{p.name:p.read_bytes() for p in folder.iterdir()})
            for request in [{'capture_id':'../bad','label':'no_voice'},{'capture_id':cid,'label':'speech_probability'}]:
                with self.assertRaises(ValueError):review.save(root,request)

if __name__=='__main__': unittest.main()
