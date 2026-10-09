import hashlib
import json
from pathlib import Path
import tempfile
import unittest
import wave
from unittest.mock import patch
import tower_anomaly_shadow as s

class Failures(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.output = self.root/'evaluation'

    def folder(self, name, frames=8000):
        f = self.root/'recordings/tower'/name
        f.mkdir(parents=True)
        (f/'processed.json').write_text('{"status":"no_activity"}')
        with wave.open(str(f/'raw.wav'), 'wb') as w:
            w.setparams((1, 2, 8000, 0, 'NONE', 'none'))
            w.writeframes(b'\0\0'*frames)
        return f

    def test_permanent_failures_preserve_originals_and_leave_queue(self):
        folders = [self.folder('zero',0), self.folder('missing'), self.folder('corrupt'),
                   self.folder('short',10),self.folder('valid')]
        (folders[1]/'raw.wav').unlink()
        (folders[2]/'raw.wav').write_bytes(b'corrupt')
        before = {str(p):hashlib.sha256(p.read_bytes()).hexdigest()
                  for f in folders for p in f.iterdir()}
        skipped = s.reclassify(self.root,self.output)
        self.assertEqual({r['reason'] for r in skipped},
                         {'zero_frames','missing_audio','corrupt_audio','too_short_audio'})
        self.assertEqual([f.name for f in s.pending(self.root,self.output)],['valid'])
        self.assertEqual(s.reclassify(self.root,self.output),[])
        self.assertEqual(before,{str(p):hashlib.sha256(p.read_bytes()).hexdigest()
                                for f in folders for p in f.iterdir()})

    def test_retry_backoff_and_exhaustion(self):
        f = self.folder('old'); self.folder('new')
        for attempt in range(5):
            result = s.retry_failure(self.output,f,'inference_error')
        self.assertEqual(result['status'],'failed_terminal')
        self.assertEqual([f.name for f in s.pending(self.root,self.output)],['new'])

    def test_failing_child_yields_to_next_item(self):
        self.folder('a'); self.folder('b')
        with patch.object(s.subprocess,'Popen',side_effect=OSError('unavailable')):
            result = s.run_batch(self.root,'model',self.output,guard=lambda:None)
        self.assertEqual([r['id'] for r in result['failures']],['a','b'])
        self.assertEqual(result['stop_reason'],'retry_backoff')
        self.assertTrue(all(s.read_state(self.output,f)['attempts']==1
                            for f in s.pending(self.root,self.output)))

    def test_preflight_runs_when_resources_busy(self):
        self.folder('zero',0); self.folder('valid')
        with patch.object(s.subprocess,'Popen') as child:
            result = s.run_batch(self.root,'model',self.output,guard=lambda:'RF busy')
        child.assert_not_called()
        self.assertEqual(result['reclassified_count'],1)
        self.assertEqual(result['stop_reason'],'deferred_busy')

    def test_resource_contention_never_exhausts_audio(self):
        f = self.folder('valid')
        for attempt in range(10): s.retry_failure(self.output,f,'resource_preempted')
        self.assertEqual(s.read_state(self.output,f)['attempts'],0)
        self.assertEqual(len(s.pending(self.root,self.output)),1)

    def test_truncated_audio(self):
        f = self.folder('bad')
        raw = f/'raw.wav'
        raw.write_bytes(raw.read_bytes()[:-10])
        self.assertEqual(s.audio_reason(raw),'corrupt_audio')

    def test_successful_scoring_clears_retry_state(self):
        f = self.folder('valid')
        s.save_state(self.output,f,'retry_wait','inference_error',1,0)
        class Child:
            returncode=0
            def poll(self): return 0
        def spawn(argv,**kw):
            Path(argv[argv.index('--output')+1]).write_text('{"summary":{"p100":1},"threshold":2}')
            return Child()
        with patch.object(s.subprocess,'Popen',side_effect=spawn), \
             patch.object(s,'review_metadata',return_value={'shadow_only':True}):
            result=s.run_once(self.root,'model',self.output,guard=lambda:None)
        self.assertEqual(result['status'],'scored')
        self.assertEqual(s.pending(self.root,self.output),[])
        self.assertFalse(s.state_path(self.output,f).exists())

    def test_corrupt_failure_state_does_not_block_next_item(self):
        f=self.folder('a');self.folder('b')
        s.save_state(self.output,f,'retry_wait','inference_error')
        s.state_path(self.output,f).write_text('broken')
        self.assertEqual([x.name for x in s.pending(self.root,self.output)],['b'])

    def test_output_safety_checked_before_reclassification(self):
        self.folder('zero',0)
        with self.assertRaises(ValueError):
            s.run_batch(self.root,'model',self.root/'recordings/tower',guard=lambda:None)

if __name__ == '__main__': unittest.main()
