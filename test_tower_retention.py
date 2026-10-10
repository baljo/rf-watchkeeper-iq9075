import json
from datetime import datetime,timezone
from pathlib import Path
import tempfile
import unittest
import tower_retention as retention
import atis_pipeline
import audio_tap
import sqlite3
import threading
from unittest.mock import patch

class TowerRetentionTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name);self.base=self.root/'recordings/tower';self.base.mkdir(parents=True)
        self.now=datetime(2026,10,6,tzinfo=timezone.utc).timestamp()
    def capture(self,age,status='no_activity'):
        stamp=datetime.fromtimestamp(self.now-age*86400,timezone.utc).strftime('%Y%m%dT%H%M%S.%fZ')
        p=self.base/stamp;p.mkdir()
        (p/'capture.json').write_text(json.dumps({'source':'live','kind':'tower'}))
        (p/'processed.json').write_text(json.dumps({'status':status}))
        (p/'audio-retention.json').write_text('{"status":"original"}')
        (p/'raw.wav').write_bytes(b'original raw');(p/'listen.wav').write_bytes(b'original listen')
        return p
    def test_no_activity_survives_short_term_cleanup(self):
        p=self.capture(1);before={f.name:f.read_bytes() for f in p.iterdir()}
        retention.cleanup(self.base,now=self.now)
        self.assertEqual(before,{f.name:f.read_bytes() for f in p.iterdir()})
    def test_pinned_survives_all_normal_cleanup_and_keeps_originals(self):
        p=self.capture(60);before={f.name:f.read_bytes() for f in p.iterdir()}
        target=retention.pin(self.root,p/'raw.wav')
        retention.cleanup(self.base,now=self.now+365*86400)
        atis_pipeline.retain_tower_audio(self.base,keep=0)
        retention.cleanup(target,now=self.now+365*86400)
        for name,value in before.items():
            self.assertEqual((p/name).read_bytes(),value);self.assertEqual((target/name).read_bytes(),value)
        self.assertTrue(retention.protected(target));self.assertTrue(retention.protected(p))
    def test_unpinned_eventually_expires_regardless_of_classifier(self):
        for age,status in ((30,'no_activity'),(31,'completed'),(32,'silence_removed'),(33,'failed')):
            p=self.capture(age,status);metadata=(p/'audio-retention.json').read_bytes()
            retention.cleanup(self.base,now=self.now)
            self.assertFalse((p/'raw.wav').exists());self.assertFalse((p/'listen.wav').exists())
            self.assertEqual((p/'audio-retention.json').read_bytes(),metadata)
            self.assertTrue((p/'capture.json').exists())
    def test_boundary_and_incomplete_capture(self):
        p=self.capture(30)
        retention.cleanup(self.base,now=self.now-1);self.assertTrue((p/'raw.wav').exists())
        (p/'processed.json').unlink();retention.cleanup(self.base,now=self.now+1000);self.assertTrue((p/'raw.wav').exists())
    def test_reference_flags_markers_and_symlinks_fail_closed(self):
        for age,flag in enumerate(('pinned','protected','reference','keep','reference_sample'),40):
            p=self.capture(age);(p/'capture.json').write_text(json.dumps({'source':'live','kind':'tower',flag:True}))
            retention.cleanup(self.base,now=self.now);self.assertTrue((p/'raw.wav').exists())
        p=self.capture(50);(p/'KEEP').touch();retention.cleanup(self.base,now=self.now);self.assertTrue((p/'raw.wav').exists())
    def test_protected_reference_processing_cannot_modify_or_cleanup(self):
        p=self.capture(60);target=retention.pin(self.root,p)
        before={f.name:f.read_bytes() for f in target.iterdir()}
        atis_pipeline.process(target,threading.Event())
        self.assertEqual(before,{f.name:f.read_bytes() for f in target.iterdir()})
    def test_atis_no_activity_retention_and_clip_cleanup_unchanged(self):
        p=self.root/'recordings/atis/test';p.mkdir(parents=True)
        for name in ('raw.wav','listen.wav','clip-000000.wav'):(p/name).write_bytes(b'audio')
        (p/'capture.json').write_text(json.dumps({'source':'live','kind':'atis'}))
        (p/'segmentation.json').write_text('{"status":"no_activity"}')
        # Isolate this ordinary-cleanup fixture from the independently tested shadow queue.
        with patch.object(atis_pipeline,'prepare',return_value=[]), patch('atis_shadow.prepare',side_effect=lambda source,target: [f.unlink() for f in target.glob('clip-*.wav')]), patch('atis_shadow.enqueue'), patch('atis_shadow.retention_hold',return_value=False):
            atis_pipeline.process(p,threading.Event())
        self.assertFalse((p/'raw.wav').exists());self.assertFalse((p/'listen.wav').exists())
        self.assertFalse((p/'clip-000000.wav').exists())
        self.assertEqual(json.loads((p/'audio-retention.json').read_text())['status'],'silence_removed')
    def test_fm_cleanup_explicitly_excludes_tower_and_reference_audio(self):
        p=self.capture(60);target=retention.pin(self.root,p)
        ordinary=self.root/'fm.wav';ordinary.write_bytes(b'fm')
        db=sqlite3.connect(':memory:')
        db.execute('CREATE TABLE audio_recordings (id INTEGER, file_path TEXT, source TEXT, recorded_at TEXT)')
        for i,file in enumerate((p/'raw.wav',target/'raw.wav',ordinary)):
            db.execute('INSERT INTO audio_recordings VALUES (?,?,?,?)',(i,str(file),'fm','2026'))
        audio_tap.prune_fm(db,keep=0)
        self.assertTrue((p/'raw.wav').exists());self.assertTrue((target/'raw.wav').exists())
        self.assertFalse(ordinary.exists());self.assertEqual(db.execute('SELECT count(*) FROM audio_recordings').fetchone()[0],2)
    def test_atis_scope_excluded(self):
        p=self.capture(60);atis=self.root/'recordings/atis';self.base.rename(atis)
        retention.cleanup(atis,now=self.now);self.assertTrue((atis/p.name/'raw.wav').exists())
    def test_pin_rejects_other_channels_and_missing_audio(self):
        with self.assertRaises(ValueError):retention.pin(self.root,'../atis')
        p=self.capture(1);(p/'raw.wav').unlink();(p/'listen.wav').unlink()
        with self.assertRaises(FileNotFoundError):retention.pin(self.root,p)

if __name__=='__main__':unittest.main()
