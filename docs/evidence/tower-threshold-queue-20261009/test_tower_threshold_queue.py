import unittest
from atis_view import needs_tower_review, completed_tower_score
class ThresholdQueue(unittest.TestCase):
 def row(self,score=46,threshold=45.67438250526811,**kw):
  return dict(status='voice_candidate',anomaly_review=dict(score=score,threshold=threshold,scoring_status='scored',review_state='unreviewed',**kw))
 def test_threshold(self):
  for score in [36.656,39.476,41.334]:
   for status in ['voice_candidate','uncertain','no_activity']:
    r=self.row(score,anomaly_candidate=True);r['status']=status
    self.assertFalse(needs_tower_review(r))
  self.assertTrue(needs_tower_review(self.row()))
  self.assertTrue(needs_tower_review(self.row(45.67438250526811)))
  self.assertFalse(needs_tower_review(self.row(46,50)))
 def test_invalid(self):
  for value in [None,True,'50',float('nan'),float('inf')]:
   self.assertFalse(needs_tower_review(self.row(value)))
   self.assertFalse(needs_tower_review(self.row(50,value)))
  r=self.row();del r['anomaly_review']['scoring_status'];self.assertFalse(needs_tower_review(r))
  r=self.row();r['human_review']={'human_review_label':'confirmed_voice'};self.assertFalse(needs_tower_review(r))
 def test_completion(self):
  for status in ['pending','failed']:
   self.assertFalse(completed_tower_score(dict(mode='shadow_only',status=status,summary={'count':1,'p100':50},threshold=45)))
