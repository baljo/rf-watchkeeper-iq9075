import json
from pathlib import Path
import tempfile
import unittest
import atis_view
import atis_pipeline

class TowerRecentTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name);self.base=self.root/'recordings/tower';self.base.mkdir(parents=True)
    def capture(self,i,status='no_activity',source='live'):
        p=self.base/('20261006T1200%02d.000000Z'%i);p.mkdir()
        (p/'capture.json').write_text(json.dumps(dict(status='ready',audio_seconds=29.184,source=source,kind='tower')))
        (p/'processed.json').write_text(json.dumps(dict(status=status)))
        (p/'listen.wav').write_bytes(b'RIFFtest');(p/'raw.wav').write_bytes(b'RIFFraw')
        return p
    def test_history_includes_twenty_silent_attempts_and_missing_audio(self):
        for i in range(25):self.capture(i)
        p=self.base/'20261006T120024.000000Z';(p/'listen.wav').unlink();(p/'raw.wav').unlink()
        rows=atis_view.recent(self.root)
        self.assertEqual(len(rows),20);self.assertEqual(rows[0]['result'],'no_activity')
        self.assertEqual(rows[0]['duration_seconds'],29.184);self.assertIsNone(rows[0]['audio_url'])
        self.assertTrue(rows[0]['captured_at'].endswith('+00:00'))
    def test_audio_is_pinned_to_selected_capture_and_rejects_escape(self):
        p=self.capture(1);q=self.capture(2);(q/'listen.wav').write_bytes(b'newer')
        self.assertEqual(atis_view.audio(self.root,'tower',p.name),b'RIFFtest')
        for value in ('../atis','/etc/passwd','20261006T120001.000000Z/../../x'):
            with self.assertRaises(ValueError):atis_view.audio(self.root,'tower',value)
        (p/'listen.wav').unlink();(p/'listen.wav').symlink_to(q/'listen.wav');(p/'raw.wav').unlink()
        with self.assertRaises(FileNotFoundError):atis_view.audio(self.root,'tower',p.name)
    def test_retention_preserves_speech_references_metadata_and_latest_twenty(self):
        old=self.capture(0);speech=self.capture(1,'completed');reference=self.capture(2,source='reference')
        for i in range(3,25):self.capture(i)
        atis_pipeline.retain_tower_audio(self.base)
        self.assertFalse((old/'listen.wav').exists());self.assertTrue((old/'capture.json').exists())
        self.assertTrue((speech/'listen.wav').exists());self.assertTrue((reference/'listen.wav').exists())
        self.assertTrue((self.base/'20261006T120005.000000Z/listen.wav').exists())
    def test_speech_and_failure_status(self):
        p=self.capture(1,'completed');(p/'transcript.json').write_text('{"segments":[{"text":"Tower hello"}]}')
        self.assertEqual(atis_view.recent(self.root)[0]['result'],'speech')
        self.capture(2,'failed');self.assertEqual(atis_view.recent(self.root)[0]['result'],'failed')

if __name__=='__main__':unittest.main()
