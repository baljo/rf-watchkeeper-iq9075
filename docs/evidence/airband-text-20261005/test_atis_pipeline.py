import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import wave
import array
import atis_pipeline as a

class SafetyTests(unittest.TestCase):
    def setUp(self):
        guard=patch.object(a,'managed_satellite_reason',return_value=None)
        guard.start();self.addCleanup(guard.stop)
    def test_active_satellite_blocks(self):
        with patch.object(a,'command',return_value='meteor-test.service loaded active running capture'):
            self.assertIn('active',a.satellite_reason(90))

    def test_does_not_match_description(self):
        with patch.object(a,'command',side_effect=['atis.service loaded active running meteor-check','']):
            self.assertIsNone(a.satellite_reason(90))

    def test_upcoming_timer_blocks(self):
        with patch.object(a,'time') as clock,patch.object(a,'command',side_effect=['','meteor-next.timer loaded active waiting','Fri 2026-10-02 19:00:00 UTC']):
            clock.time.return_value=1790967360 # 18:56 UTC
            self.assertIn('timer due',a.satellite_reason(90))

    def test_unknown_schedule_blocks(self):
        with patch.object(a,'command',side_effect=OSError('unavailable')):
            self.assertIn('cannot be verified',a.satellite_reason())

    def test_interval_survives_restart(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d);job={'interval_seconds':1800}
            a.save(p/'atis-last-slot.json',{'attempted_at':10000})
            self.assertFalse(a.due(job,p,11799));self.assertTrue(a.due(job,p,11800))

    def test_preprocessing_preserves_original_and_bounds_clips(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)
            with wave.open(str(p/'raw.wav'),'wb') as w:
                w.setnchannels(1);w.setsampwidth(2);w.setframerate(8000)
                w.writeframes(array.array('h',[0,1000,-1000,0]*8000*10).tobytes())
            before=(p/'raw.wav').read_bytes();clips=a.prepare(p)
            self.assertEqual(before,(p/'raw.wav').read_bytes())
            for _,clip in clips:
                with wave.open(str(clip)) as w:
                    self.assertEqual(w.getframerate(),16000)
                    self.assertLessEqual(w.getnframes()/16000,28)

    def test_processing_does_not_start_during_satellite(self):
        with patch.object(a,'satellite_reason',return_value='satellite'),patch.object(a.subprocess,'Popen') as popen:
            import threading
            with self.assertRaises(InterruptedError):a.guarded_run(['model'],Path('unused'),threading.Event())
            popen.assert_not_called()

if __name__=='__main__':unittest.main()
