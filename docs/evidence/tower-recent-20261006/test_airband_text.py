import array
import hashlib
import json
import math
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch
import wave
import airband_text as text
import atis_pipeline as pipeline
import atis_view as view


class AirbandTests(unittest.TestCase):
    def tone(self, seconds, amplitude=1000):
        return array.array('h', (round(amplitude * math.sin(2*math.pi*440*i/8000))
                                for i in range(int(seconds*8000))))

    def recording(self, root, samples):
        folder = root/'recordings/atis/20261005T000000Z'
        folder.mkdir(parents=True)
        pipeline.save(folder/'capture.json', {'status':'ready'})
        with wave.open(str(folder/'raw.wav'), 'wb') as wav:
            wav.setparams((1,2,8000,0,'NONE','not compressed'))
            wav.writeframes(samples.tobytes())
        return folder

    def test_separate_bursts_and_click_rejection(self):
        samples = array.array('h', [0]*8000)+self.tone(1)+array.array('h',[0]*16000)+self.tone(1)+array.array('h',[0]*8000)
        regions, report = text.activity_regions(samples,8000)
        self.assertEqual(len(regions),2)
        self.assertLess(regions[0][1],regions[1][0])
        self.assertEqual(report['status'],'activity_detected')
        samples = array.array('h',[0]*8000)+self.tone(.1)+array.array('h',[0]*8000)
        self.assertEqual(text.activity_regions(samples,8000)[0],[])

    def test_continuous_audio_is_retained_but_not_certified_as_speech(self):
        regions, report = text.activity_regions(self.tone(60),8000)
        self.assertEqual(report['status'],'continuous_or_noise')
        self.assertEqual(sum(e-s for s,e in regions),60*8000)
        self.assertTrue(all(e-s <= 28*8000 for s,e in regions))

    def test_spelling_is_auditable_and_does_not_repair_weather_numbers(self):
        raw = 'Q N H niner niner one, I L S runway 16 temperature 140.11 LASA'
        normalized = text.normalize(raw)
        self.assertEqual(normalized['text'],'QNH nine nine one, ILS runway 16 temperature 140.11 LASA')
        self.assertEqual(len(normalized['changes']),4)
        self.assertFalse(normalized['numeric_values_verified'])

    def test_silence_skips_models_and_is_not_failure(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);folder=self.recording(root,array.array('h',[1200]*8000*4))
            original=hashlib.sha256((folder/'raw.wav').read_bytes()).hexdigest()
            with patch.object(pipeline,'guarded_run') as run:
                pipeline.process(folder,threading.Event())
                run.assert_not_called()
            self.assertEqual(json.loads((folder/'processed.json').read_text())['status'],'no_activity')
            self.assertEqual(view.snapshot(root)['status'],'no_activity')
            self.assertFalse((folder/'raw.wav').exists())
            self.assertTrue((folder/'capture.json').exists())

    def test_short_speech_is_padded_not_discarded(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder=self.recording(Path(tmp),array.array('h',[0]*8000)+self.tone(.4)+array.array('h',[0]*8000))
            clips=pipeline.prepare(folder)
            self.assertEqual(len(clips),1)
            with wave.open(str(clips[0][1])) as wav:
                self.assertEqual(wav.getnframes(),48000)

    def test_asr_and_genie_failures_have_distinct_status(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);folder=self.recording(root,self.tone(4))
            with patch.object(pipeline,'guarded_run',side_effect=RuntimeError('Model exited with code 1')):
                pipeline.process(folder,threading.Event())
            self.assertEqual(view.snapshot(root)['status'],'failed')
            def model(argv, *args, **kwargs):
                if argv[0]=='genie-t2t-run':raise RuntimeError('Genie failure')
                Path(argv[argv.index('-o')+1]).write_text(json.dumps({'text':'Q N H niner one','language':'English'}))
            with patch.object(pipeline,'guarded_run',side_effect=model):
                pipeline.process(folder,threading.Event())
            shown=view.snapshot(root)
            self.assertEqual(shown['status'],'partial_success')
            self.assertEqual(shown['transcript']['segments'][0]['text'],'QNH nine one')
            self.assertEqual(json.loads((folder/'transcript.json').read_text())['segments'][0]['text'],'Q N H niner one')

    def test_pending_interrupted_and_corrupt_outputs(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);folder=self.recording(root,self.tone(1))
            self.assertEqual(view.snapshot(root)['status'],'pending')
            (folder/'transcript.json').write_text('{broken')
            self.assertEqual(view.snapshot(root)['status'],'failed')
            pipeline.save(folder/'capture.json',{'status':'interrupted','reason':'Satellite reservation'})
            self.assertEqual(view.snapshot(root)['status'],'interrupted')

    def test_preemption_leaves_recording_retryable(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder=self.recording(Path(tmp),self.tone(4))
            with patch.object(pipeline,'guarded_run',side_effect=InterruptedError('satellite')):
                with self.assertRaises(InterruptedError):pipeline.process(folder,threading.Event())
            self.assertFalse((folder/'processed.json').exists())

    def test_managed_reservation_and_corrupt_plan_block(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);(root/'data/meteor-auto').mkdir(parents=True)
            plan=root/'data/meteor-auto/plan.json'
            pipeline.save(plan,{'passes':[{'status':'planned','record_start':'2026-10-05T00:04:00+00:00',
                                          'record_stop':'2026-10-05T00:20:00+00:00','id':'managed-pass'}]})
            with patch.object(pipeline.rf_health,'ROOT',root), patch.object(pipeline.rf_health,'satellite_guard',return_value=None), patch.object(pipeline.time,'time',return_value=1791158400):
                self.assertIn('managed-pass',pipeline.satellite_reason(90))
                plan.write_text('{broken')
                self.assertIn('cannot be verified',pipeline.satellite_reason(90))

    def test_active_persisted_ownership_blocks(self):
        with patch.object(pipeline.rf_health,'satellite_guard',return_value='persisted capture reservation'):
            self.assertIn('ownership',pipeline.satellite_reason(90))

    def test_model_without_new_output_cannot_reuse_stale_transcript(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder=self.recording(Path(tmp),self.tone(4))
            clips=pipeline.prepare(folder)
            pipeline.save(clips[0][1].with_suffix('.json'),{'text':'stale runway 16'})
            with patch.object(pipeline,'guarded_run'):
                pipeline.process(folder,threading.Event())
            result=json.loads((folder/'transcript.json').read_text())
            self.assertEqual(result['status'],'failed')
            self.assertFalse(any(r.get('text') for r in result['segments']))


if __name__=='__main__':unittest.main()
