import unittest
from tower_review_policy import persistent, audit_selected, selection_reason, DETECTOR_THRESHOLD


class ReviewPolicyTests(unittest.TestCase):
    def window(self, start, score):
        return dict(start_seconds=start, end_seconds=start+1, anomaly_score=score)

    def test_persistence(self):
        self.assertTrue(persistent([self.window(0,55), self.window(.5,55)]))
        for windows in ([self.window(0,99)], [self.window(0,55),self.window(1,55)],
                        [self.window(0,55),self.window(.5,54),self.window(1,55)],
                        [self.window(0,55),self.window(0,55)],
                        [self.window(.5,55),self.window(0,55)],
                        [self.window(0,55),self.window(.5,float('nan'))], None):
            self.assertFalse(persistent(windows))

    def test_deterministic_audit_and_boundaries(self):
        selected = [str(i) for i in range(10000) if audit_selected(str(i))]
        self.assertTrue(500 < len(selected) < 1000)
        cid = selected[0]
        row = dict(recording=cid,audio_available=True,anomaly_review=dict(
            score=DETECTOR_THRESHOLD,threshold=DETECTOR_THRESHOLD,scoring_status='scored'))
        self.assertEqual(selection_reason(row),'grey_zone_audit')
        self.assertEqual(selection_reason(row),selection_reason(row))
        row['anomaly_review']['score']=DETECTOR_THRESHOLD-1e-8
        self.assertIsNone(selection_reason(row))
        row['anomaly_review']['score']=55
        self.assertIsNone(selection_reason(row))
        row['anomaly_review']['review_persistent']=True
        self.assertEqual(selection_reason(row),'persistent_ad')
        row['human_review']={'human_review_label':'no_voice'}
        self.assertIsNone(selection_reason(row))

    def test_override_still_requires_score_and_audio(self):
        row=dict(explicit_review_override=True,audio_available=True,
                 anomaly_review=dict(score=1,threshold=DETECTOR_THRESHOLD,scoring_status='scored'))
        self.assertEqual(selection_reason(row),'explicit_override')
        row['audio_available']=False
        self.assertIsNone(selection_reason(row))
        row['audio_available']=True
        row['anomaly_review']['score']=None
        self.assertIsNone(selection_reason(row))
