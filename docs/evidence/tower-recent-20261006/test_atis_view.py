import hashlib
import json
from pathlib import Path
import tempfile
import unittest
import wave
import atis_view
import audio_workflow

class ATISViewTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);self.p=self.root/'recordings/atis/20261002T190000Z';self.p.mkdir(parents=True)
        (self.p/'capture.json').write_text(json.dumps({'status':'ready','audio_seconds':20}))
        self.clip=self.p/'clip-000.wav'
        with wave.open(str(self.clip),'wb') as w:
            w.setparams((1,2,16000,0,'NONE','not compressed'));w.writeframes(b'\0\0'*1600)
        (self.p/'listen.wav').write_bytes(self.clip.read_bytes())

    def test_status_is_review_required_even_after_success(self):
        (self.p/'processed.json').write_text('{"status":"completed"}')
        self.assertEqual(atis_view.snapshot(self.root)['status'],'needs_review')
        self.assertEqual(atis_view.audio(self.root),self.clip.read_bytes())

    def test_tiny_cannot_be_run_on_stale_atis_id(self):
        flow=audio_workflow.AudioWorkflow(self.root,self.root/'events',self.root/'genie')
        self.assertFalse(flow.catalog())
        key=hashlib.sha256(self.clip.relative_to(self.root).as_posix().encode()).hexdigest()[:24]
        with self.assertRaisesRegex(ValueError,'tiny-model'):flow.start(key,'en')
        self.assertIsNone(flow.worker)

    def test_old_summary_is_not_exposed_as_success(self):
        flow=audio_workflow.AudioWorkflow(self.root,self.root/'events',self.root/'genie')
        flow.state={'state':'completed','recording':'recordings/atis/one/clip.wav','transcription':{'model':'whisper_tiny-qcs9075','text':'Conviction'},'interpretation':{'summary':'Conviction'}}
        shown=flow.snapshot()
        self.assertEqual(shown['state'],'unreliable');self.assertIsNone(shown['interpretation'])
        self.assertEqual(flow.state['interpretation']['summary'],'Conviction')

    def test_interpretation_classification_uses_actual_source(self):
        event={'event_type':'transcription','model':'whisper_tiny-qcs9075','input_file':'/root/rf-watchkeeper/recordings/atis/one/clip.wav'}
        self.assertTrue(atis_view.legacy_tiny(event))
        self.assertTrue(atis_view.legacy_tiny({'event_type':'interpretation','raw_event':event}))
        self.assertFalse(atis_view.legacy_tiny(dict(event,input_file='/root/recordings/fm.wav')))

if __name__=='__main__':unittest.main()
