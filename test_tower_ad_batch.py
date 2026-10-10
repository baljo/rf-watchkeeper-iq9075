import unittest
from tower_anomaly_shadow import run_batch
class BatchTests(unittest.TestCase):
    def test_continues_and_stops_on_busy(self):
        results=iter([{'status':'scored','id':'a'},{'status':'scored','id':'b'},{'status':'deferred_busy'}])
        calls=[]
        def runner(*args,**kw): calls.append(kw);return next(results)
        guard=lambda:None
        r=run_batch(None,None,None,guard=guard,runner=runner,clock=lambda:0)
        self.assertEqual(r['ids'],['a','b']);self.assertEqual(r['stop_reason'],'deferred_busy')
        self.assertTrue(all(c['guard'] is guard for c in calls))
    def test_recording_bound(self):
        r=run_batch(None,None,None,max_recordings=2,runner=lambda *a,**k:{'status':'scored','id':'x'},clock=lambda:0)
        self.assertEqual(r['scored_count'],2)
    def test_time_bound_and_child_budget(self):
        ticks=iter([0,40,46,46]);budgets=[]
        def runner(*a,**kw):budgets.append(kw['timeout']);return {'status':'scored','id':'x'}
        r=run_batch(None,None,None,runner=runner,clock=lambda:next(ticks))
        self.assertEqual(budgets,[5]);self.assertEqual(r['scored_count'],1)
    def test_failure_stops(self):
        r=run_batch(None,None,None,runner=lambda *a,**k:{'status':'failed_or_deferred'},clock=lambda:0)
        self.assertEqual(r['scored_count'],0)
if __name__=='__main__':unittest.main()
