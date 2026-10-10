import hashlib
import json
from pathlib import Path
import tempfile
import unittest
import wave
from unittest.mock import patch
import numpy as np
import tower_anomaly as a
import tower_anomaly_shadow as shadow


def wav(path, samples, rate=16000, channels=1):
    with wave.open(str(path),'wb') as f:
        f.setnchannels(channels); f.setsampwidth(2); f.setframerate(rate)
        f.writeframes(np.asarray(samples,dtype='<i2').tobytes())


class AnomalyTests(unittest.TestCase):
    def test_resampling_mono_dc_and_window_boundaries(self):
        with tempfile.TemporaryDirectory() as directory:
            p=Path(directory)/'raw.wav'
            signal=(np.sin(np.arange(20000)*0.2)*100+500).astype(np.int16)
            wav(p,np.repeat(signal[:,None],2,axis=1),8000,2)
            x=a.read_audio(p)
            self.assertEqual(len(x),40000)
            self.assertLess(abs(x.mean()),1e-6)
            f,starts,_=a.features(x)
            self.assertEqual(starts,[0,0.5,1,1.5])
            self.assertEqual(f.shape,(4,26))
            self.assertTrue(np.isfinite(f).all())
            self.assertEqual(a.features(x[:15999])[0].shape,(0,26))

    def test_gmm_separates_unseen_distribution_and_roundtrips(self):
        rng=np.random.RandomState(7)
        train=np.r_[rng.normal(-1,0.2,(300,26)),rng.normal(1,0.2,(300,26))]
        model=a.fit_model(train)
        restored=json.loads(json.dumps(model))
        normal=a.score(rng.normal(1,0.2,(100,26)),restored)
        unusual=a.score(np.full((10,26),5),restored)
        self.assertGreater(unusual.min(),normal.max())
        np.testing.assert_allclose(a.score(train,model),a.score(train,restored))
        with self.assertRaises(ValueError): a.score(train,dict(model,version=2))

    def test_metadata_and_audio_activity_are_excluded(self):
        with tempfile.TemporaryDirectory() as directory:
            p=Path(directory)
            a.save_json(p/'processed.json',{'status':'no_activity'})
            a.save_json(p/'segmentation.json',{'status':'no_activity','regions':[]})
            metrics=[dict(rms=0.01,peak=0.05,spectral_flatness=0.9)]*4
            self.assertEqual(a.screening(p,metrics),[])
            self.assertIn('energy_burst',a.screening(p,metrics+[dict(rms=0.1,peak=0.4,spectral_flatness=0.9)]))
            a.save_json(p/'segmentation.json',{'status':'activity_detected','regions':[{}]})
            self.assertIn('metadata_activity_or_unknown',a.screening(p,metrics))

    def test_benchmark_content_quarantined_even_under_earlier_alias(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            for name in ['000-alias',a.BENCHMARK,'bad-audio']+['candidate-%02d'%i for i in range(40)]:
                folder=root/'recordings/tower'/name; folder.mkdir(parents=True)
                (folder/'raw.wav').write_bytes(b'benchmark' if name in ('000-alias',a.BENCHMARK) else name.encode())
                a.save_json(folder/'processed.json',{'status':'no_activity'})
                a.save_json(folder/'segmentation.json',{'status':'no_activity','regions':[]})
            def fake_audio(path):
                if path.parent.name=='bad-audio': raise EOFError()
                return np.zeros(80000)
            rng=np.random.RandomState(18)
            def fake_features(pcm):
                return rng.normal(0,0.02,(20,26)),list(np.arange(20)*0.5),[dict(rms=0.01,peak=0.05,spectral_flatness=0.9)]*20
            with patch.object(a,'read_audio',side_effect=fake_audio),patch.object(a,'features',side_effect=fake_features):
                report=a.evaluate(root,root/'evaluation')
            self.assertEqual(report['benchmark']['id'],a.BENCHMARK)
            manifest=a.read_json(root/'evaluation/dataset-manifest.json')
            alias=next(e for e in manifest['entries'] if e['id']=='000-alias')
            self.assertEqual(alias['role'],'excluded')
            bad=next(e for e in manifest['entries'] if e['id']=='bad-audio')
            self.assertEqual(bad['reasons'],['invalid_audio:EOFError'])
            model=a.read_json(root/'evaluation/model.json')
            self.assertNotIn(hashlib.sha256(b'benchmark').hexdigest(),model['training_hashes'])

    def test_real_manifest_no_content_leak_and_disjoint_splits(self):
        # Optional retained evaluation is supplied explicitly in CI/replay.
        import os
        base=os.environ.get('TOWER_ANOMALY_EVIDENCE')
        if not base: self.skipTest('Set TOWER_ANOMALY_EVIDENCE to generated evaluation')
        m=a.read_json(Path(base)/'dataset-manifest.json')
        model=a.read_json(Path(base)/'model.json')
        positive=set(m['benchmark_hashes'])
        groups={r:{e['sha256'] for e in m['entries'] if e['role']==r} for r in
                ('background_train','background_calibration','background_test')}
        self.assertTrue(positive)
        for hashes in groups.values(): self.assertFalse(positive & hashes)
        self.assertFalse(groups['background_train'] & groups['background_test'])
        self.assertFalse(groups['background_train'] & groups['background_calibration'])
        self.assertFalse(groups['background_test'] & groups['background_calibration'])
        self.assertEqual(groups['background_train'],set(model['training_hashes']))
        report=a.read_json(Path(base)/'report.json')
        self.assertEqual(report['shadow_threshold'],report['distributions']['background_calibration']['p99.5'])

    def test_shadow_defer_does_not_touch_originals(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            result=shadow.run_once(root,root/'absent',root/'evaluation',guard=lambda:'RF busy')
            self.assertEqual(result['status'],'deferred_busy')
            self.assertFalse((root/'evaluation').exists())
            with self.assertRaises(ValueError): shadow.run_once(root,root/'absent',root/'recordings/tower',guard=lambda:None)

    @unittest.skipUnless(hasattr(__import__('os'),'major'),'Kernel lock device IDs require Linux')
    def test_kernel_lock_guard_does_not_use_stale_owner_metadata(self):
        import os
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'htp.lock'; path.write_text('')
            stat=path.stat()
            table=Path(directory)/'locks'
            table.write_text('')
            self.assertFalse(shadow.lock_is_held(path,table))
            table.write_text('1: FLOCK ADVISORY WRITE 123 %02x:%02x:%d 0 EOF\n'%
                             (os.major(stat.st_dev),os.minor(stat.st_dev),stat.st_ino))
            self.assertTrue(shadow.lock_is_held(path,table))
            self.assertEqual(path.read_text(),'')
            owner=dict(pid=os.getpid(),start=Path('/proc/%d/stat'%os.getpid()).read_text().rsplit(')',1)[1].split()[19],
                       boot=Path('/proc/sys/kernel/random/boot_id').read_text().strip())
            self.assertTrue(shadow.waiter_is_alive(owner))
            self.assertFalse(shadow.waiter_is_alive(dict(owner,boot='different-boot')))

    def test_shadow_scoring_is_additive_and_hash_preserving(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory); folder=root/'recordings/tower'/a.BENCHMARK; folder.mkdir(parents=True)
            rng=np.random.RandomState(5)
            wav(folder/'raw.wav',rng.normal(0,100,32000))
            a.save_json(folder/'processed.json',{'status':'no_activity'})
            before={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in folder.iterdir()}
            x,_,_=a.features(a.read_audio(folder/'raw.wav'))
            model=a.fit_model(np.tile(x,(40,1))+rng.normal(0,0.2,(120,26)))
            model['shadow_threshold']=50
            a.save_json(root/'model.json',model)
            with patch.object(shadow.subprocess, 'Popen', wraps=shadow.subprocess.Popen) as spawn:
                result=shadow.run_once(root,root/'model.json',root/'evaluation',guard=lambda:None)
            self.assertEqual(spawn.call_count,1)
            self.assertIn('--score-child',spawn.call_args.args[0])
            self.assertEqual(Path(spawn.call_args.args[0][1]).name,'tower_anomaly_shadow.py')
            self.assertEqual(result['status'],'scored')
            evidence=a.read_json(root/'evaluation'/(a.BENCHMARK+'.json'))
            self.assertFalse(evidence['affects_retention'])
            self.assertFalse(evidence['affects_transcription'])
            self.assertEqual(before,{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in folder.iterdir()})
            self.assertEqual(shadow.pending(root,root/'evaluation'),[])

    def test_incomplete_and_oversized_audio_get_terminal_preflight(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory); folder=root/'recordings/tower'/'test'; folder.mkdir(parents=True)
            (folder/'raw.wav').write_bytes(b'empty')
            self.assertEqual(shadow.pending(root,root/'evaluation'),[])
            a.save_json(folder/'processed.json',{'status':'failed'})
            with (folder/'raw.wav').open('wb') as f: f.truncate(5_000_001)
            before=(folder/'raw.wav').stat().st_size
            skipped=shadow.reclassify(root,root/'evaluation')
            self.assertEqual(skipped,[{'id':'test','reason':'audio_size_limit'}])
            self.assertEqual(shadow.pending(root,root/'evaluation'),[])
            self.assertEqual((folder/'raw.wav').stat().st_size,before)


class ReviewTests(unittest.TestCase):
    def test_shadow_threshold_and_production_outcomes(self):
        for status in ('no_activity','failed','partial_success','success','pending',None):
            for score in (45.0,45.67438250526811,46.0):
                processing={'status':status,'sentinel':'unchanged'}
                before=json.dumps(processing)
                result=shadow.review_metadata({'summary':{'p100':score},'threshold':45.67438250526811},processing)
                self.assertEqual(result['anomaly_candidate'],status in ('no_activity','failed') and score>45.67438250526811)
                self.assertEqual(before,json.dumps(processing))
                self.assertFalse(result['affects_transcription'])
                self.assertFalse(result['affects_retention'])

    def test_process_identity_guard(self):
        self.assertFalse(shadow.process_is_busy([b'/usr/bin/python3',b'interpret_stream.py',b'--asr',b'genie']))
        for executable in ('rtl_sdr','rtl_fm','satdump','whisper-cli','genie','asr','ais_rx','rtl_ais','VoiceAI'):
            self.assertTrue(shadow.process_is_busy(['/usr/bin/'+executable]))

if __name__=='__main__': unittest.main()
