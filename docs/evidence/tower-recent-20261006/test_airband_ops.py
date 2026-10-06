import array
from datetime import datetime, timezone
import io
import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch
import wave
import atis_view as v
import atis_pipeline as a
import job_manager as j

class OperatingTests(unittest.TestCase):
    def test_valid_empty_asr_is_normal_no_speech(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder=Path(tmp)/'tower'/'test';folder.mkdir(parents=True)
            with wave.open(str(folder/'raw.wav'),'wb') as wav:
                wav.setparams((1,2,8000,0,'NONE','none'));wav.writeframes(array.array('h',[1000,-1000]*16000).tobytes())
            def model(argv,*args,**kwargs):
                Path(argv[argv.index('-o')+1]).write_text(json.dumps({'text':''}))
            with patch.object(a,'guarded_run',side_effect=model):a.process(folder,threading.Event())
            self.assertEqual(json.loads((folder/'processed.json').read_text())['status'],'no_activity')
            self.assertTrue((folder/'raw.wav').exists())

    def test_helsinki_window_boundaries_and_winter(self):
        for date, expected in [('2026-10-05T01:59:00+00:00',False),('2026-10-05T02:00:00+00:00',True),
                               ('2026-10-05T22:29:00+00:00',True),('2026-10-05T22:30:00+00:00',False),
                               ('2026-12-05T03:00:00+00:00',True),('2026-12-05T23:30:00+00:00',False)]:
            self.assertEqual(j.in_window({'tower_recording':True},datetime.fromisoformat(date)),expected)

    def test_independent_slots_and_restart(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);tower={'tower_recording':True,'interval_seconds':180};atis={'atis_recording':True,'interval_seconds':600}
            with patch.object(a.time,'time',return_value=10000):a.reserve(tower,root);a.reserve(atis,root)
            self.assertTrue(a.due(tower,root,10180));self.assertFalse(a.due(atis,root,10180))
            self.assertTrue(a.due(atis,root,10600))
            a.slot_path(tower,root).write_text('{')
            self.assertFalse(a.due(tower,root,20000))

    def test_meteor_skip_is_recorded_without_execute_or_health_failure(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);stop=threading.Event();stream=io.StringIO();publisher=j.Publisher(stream,root/'status.json','live')
            job={'id':'tower','name':'Tower','mode':'am','frequency_hz':120950000,'dwell_seconds':30,'tower_recording':True,'enabled':True}
            with patch.object(j,'in_window',return_value=True),patch.object(a,'satellite_reason',return_value='Satellite ownership: meteor-auto-capture.service'),patch.object(j,'execute') as execute,patch.object(j.rf_health,'begin') as health,patch.object(j,'wait_slot'):
                self.assertEqual(j.schedule({'jobs':[job],'device':'V4MAIN01'},root,stop,publisher,cycles=1),0)
                execute.assert_not_called();health.assert_not_called()
            events=[json.loads(x) for x in stream.getvalue().splitlines()]
            self.assertTrue(any(e['state']=='skipped' and 'METEOR' in e['reason'] for e in events))
            self.assertFalse(any(e['state']=='failed' for e in events))

    def test_tower_uses_base_asr_without_genie_and_keeps_positive_audio(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);folder=root/'recordings/tower/20261005T000000Z';folder.mkdir(parents=True)
            a.save(folder/'capture.json',{'status':'ready','kind':'tower'})
            with wave.open(str(folder/'raw.wav'),'wb') as wav:
                wav.setparams((1,2,8000,0,'NONE','none'));wav.writeframes(array.array('h',[1000,-1000]*16000).tobytes())
            def model(argv,*args,**kwargs):
                self.assertNotEqual(argv[0],'genie-t2t-run')
                Path(argv[argv.index('-o')+1]).write_text(json.dumps({'text':'Tower Q N H niner one'}))
            with patch.object(a,'guarded_run',side_effect=model):a.process(folder,threading.Event())
            self.assertEqual(v.snapshot(root,'tower')['transcript']['segments'][0]['text'],'Tower QNH nine one')
            self.assertEqual(json.loads((folder/'processed.json').read_text())['status'],'completed')
            self.assertTrue((folder/'raw.wav').exists());self.assertFalse(list(folder.glob('clip-*.wav')))

    def test_genie_preemption_preserves_base_transcript(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder=Path(tmp)/'atis'/'test';folder.mkdir(parents=True)
            with wave.open(str(folder/'raw.wav'),'wb') as wav:
                wav.setparams((1,2,8000,0,'NONE','none'));wav.writeframes(array.array('h',[1000,-1000]*16000).tobytes())
            def model(argv,*args,**kwargs):
                if argv[0]=='genie-t2t-run':raise InterruptedError('METEOR')
                Path(argv[argv.index('-o')+1]).write_text(json.dumps({'text':'wind 170 degrees'}))
            with patch.object(a,'guarded_run',side_effect=model):a.process(folder,threading.Event())
            self.assertEqual(json.loads((folder/'processed.json').read_text())['status'],'partial_success')
            self.assertEqual(json.loads((folder/'interpretation.json').read_text())['status'],'deferred')

if __name__=='__main__':unittest.main()
