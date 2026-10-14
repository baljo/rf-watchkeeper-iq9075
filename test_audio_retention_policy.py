import json
import os
from pathlib import Path
import tempfile
import unittest
from datetime import datetime,timezone
from unittest.mock import patch
import tower_retention as r

class AudioPolicyTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name);self.now=datetime(2026,10,14,tzinfo=timezone.utc).timestamp()
    def capture(self,kind,age,**metadata):
        stamp=datetime.fromtimestamp(self.now-age*86400,timezone.utc).strftime('%Y%m%dT%H%M%S.%fZ')
        folder=self.root/'recordings'/kind/stamp;folder.mkdir(parents=True)
        (folder/'capture.json').write_text(json.dumps(dict(kind=kind,source='live',**metadata)))
        (folder/'raw.wav').write_bytes(b'audio');(folder/'listen.wav').write_bytes(b'listen')
        return folder
    def expire(self,p,apply=True,now=None):
        with patch.object(r,'active_paths',return_value=[]):return r.expire(p.parent,now=self.now if now is None else now,apply=apply)
    def test_original_timestamp_boundary_mtime_and_pending_review(self):
        for kind,days in [('tower',14),('atis',7)]:
            p=self.capture(kind,days,manual_review_required=True)
            os.utime(str(p/'raw.wav'),(self.now,self.now))
            self.assertEqual(self.expire(p,now=self.now-1)['deleted'],0)
            self.assertEqual(self.expire(p)['deleted'],2)
            self.assertTrue((p/'capture.json').exists())
    def test_terminal_failure_and_no_processed_file_expire(self):
        for kind in ('tower','atis'):
            p=self.capture(kind,20)
            metadata={'transcript.json':b'{"text":"kept"}','processed.json':b'{"status":"failed"}', 'review.json':b'{"label":"pending"}','tower-classification.json':b'{"status":"uncertain"}'}
            for name,data in metadata.items():(p/name).write_bytes(data)
            self.assertEqual(self.expire(p)['deleted'],2)
            for name,data in metadata.items():self.assertEqual((p/name).read_bytes(),data)
        p=self.capture('tower',21);self.assertEqual(self.expire(p)['deleted'],2)
    def test_reference_pins_hold_indefinitely_but_validation_does_not(self):
        for i,flag in enumerate(('pinned','reference','permanent_reference','protected')):
            p=self.capture('atis',30+i,**{flag:True});self.assertEqual(self.expire(p)['deleted'],0)
        p=self.capture('atis',40);(p/'atis-validation-hold.json').write_text('{"until":9999999999}')
        self.assertEqual(self.expire(p)['deleted'],2)
    def test_lock_only_protects_while_processing_alive(self):
        p=self.capture('tower',30)
        with r.folder_lock(p):self.assertEqual(self.expire(p)['protected'],1)
        self.assertEqual(self.expire(p)['deleted'],2)
    def test_open_reader_and_inspection_error_fail_closed(self):
        p=self.capture('tower',30)
        with patch.object(r,'active_paths',return_value=[str(p/'raw.wav')]):
            self.assertEqual(r.expire(p.parent,now=self.now,apply=True)['deleted'],0)
        with patch.object(r,'active_paths',side_effect=PermissionError()):
            result=r.expire(p.parent,now=self.now,apply=True)
            self.assertEqual(result['errors'],1);self.assertTrue((p/'raw.wav').exists())
    def test_malformed_metadata_symlink_and_dry_run(self):
        p=self.capture('atis',30);before=(p/'capture.json').read_bytes()
        self.assertEqual(self.expire(p,apply=False)['eligible'],2);self.assertTrue((p/'raw.wav').exists())
        (p/'capture.json').write_text('{');self.assertEqual(self.expire(p)['errors'],1)
        (p/'capture.json').write_text('[]');self.assertEqual(self.expire(p)['errors'],1)
        (p/'capture.json').write_bytes(before);outside=self.root/'outside.wav';outside.write_bytes(b'keep')
        (p/'listen.wav').unlink();(p/'listen.wav').symlink_to(outside)
        self.assertEqual(self.expire(p)['deleted'],0);self.assertEqual(outside.read_bytes(),b'keep')

if __name__=='__main__':unittest.main()
