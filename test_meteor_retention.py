import copy
from datetime import datetime, timedelta, timezone
import fcntl
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch
import meteor_retention as retention
import meteor_frequency as frequency

class RetentionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.raw = self.root / 'recordings/satellite/test.cu8'
        self.raw.parent.mkdir(parents=True)
        self.raw.write_bytes(b'x' * 200)
        self.at = datetime.now(timezone.utc)
        start = self.at - timedelta(days=10)
        self.c = dict(cleanup_enabled=False, retention=dict(automatic_deletion_validated=False))
        self.r = dict(owner='meteor-auto-v1', state='decode_failed', iq=str(self.raw),
            capture=dict(status='completed', sample_rate_sps=10), captured_iq_bytes=200,
            iq_fingerprint=retention.fingerprint(self.raw),
            decode_attempts=[dict(output='nominal', returncode=0, frequency_shift_hz=0, finished_at=self.at.isoformat(),
                metrics=dict(evaluation_clean=True, classification='EMPTY/FAILED', images=[], channel_lines={'1':0}))])
        self.r['pass'] = dict(id='m24-20261001T010000Z', satellite='M2-4', record_start=start.isoformat(), record_stop=(start+timedelta(seconds=10)).isoformat(), sample_rate=10)
        for shift in (-45000, 45000):
            a=copy.deepcopy(self.r['decode_attempts'][0])
            a.update(output=str(shift), frequency_shift_hz=shift)
            self.r['decode_attempts'].append(a)
        self.r['selected_decode_output']='nominal'
        self.r['frequency_evaluation']=dict(completed=False, procedure_completed=True, finished_at=self.at.isoformat(),
            input_fingerprint=self.r['iq_fingerprint'], best_output='nominal',
            decoder_identity=frequency.decoder_identity(self.c), configuration=frequency.procedure_config(self.c),
            survey=dict(method='sampled_broadband_spectrum_v1', span_hz=60000, windows=24, candidate_carrier_offsets_hz=[45000,-45000]),
            trials=[dict(output=a['output'],shift_hz=a['frequency_shift_hz'],returncode=0) for a in self.r['decode_attempts']])
        self.path=self.root/'data/meteor-auto/passes'/self.r['pass']['id']/'pass.json'
        self.path.parent.mkdir(parents=True)
        self.save()
    def save(self): retention.atomic(self.path,self.r)
    def result(self): return retention.classify(self.r,self.c,self.at)
    def test_disabled_gates_dry_run_candidates(self):
        before=self.path.read_bytes()
        with patch.object(Path,'unlink',side_effect=AssertionError('No deletion permitted')):
            s=retention.cleanup(self.root,self.c)
        self.assertFalse(s['cleanup_enabled']); self.assertEqual(len(s['would_delete']),1)
        self.assertEqual(s['reclaimable_bytes'],200); self.assertEqual(s['deleted'],[])
        self.assertEqual(before,self.path.read_bytes()); self.assertTrue(self.raw.exists())
    def test_protected_success_even_after_crash(self):
        self.r['decode_attempts'][0]['returncode']=139
        self.r['decode_attempts'][0]['metrics'].update(images=[dict(product='MSU-MR-1',width=256,height=200,path='historical.png')])
        self.assertEqual(self.result()['disposition'],'PROTECTED'); self.assertFalse(self.result()['eligible'])
    def test_historical_success_not_selected(self):
        self.r['decode_attempts'][-1]['metrics']['images']=[dict(product='MSU-MR-1',width=256,height=200)]
        self.assertEqual(self.result()['disposition'],'PROTECTED')
    def test_recent_failed_grace(self):
        self.r['pass']['record_stop']=self.at.isoformat()
        self.r['decode_attempts'][0]['returncode']=1
        self.assertEqual(self.result()['disposition'],'GRACE')
    def test_old_failed_no_image_deletable(self):
        self.assertEqual(self.result()['disposition'],'DELETABLE'); self.assertTrue(self.result()['eligible'])
    def test_actual_decoder_error_review(self):
        self.r['decode_attempts'][0]['returncode']=1
        self.assertEqual(self.result()['disposition'],'REVIEW')
    def test_ambiguous_frequency_review(self):
        self.r['review_reason']='Unusual frequency drift needs troubleshooting'
        self.assertEqual(self.result()['disposition'],'REVIEW')
    def test_unusual_recorded_frequency_review(self):
        self.c['frequency']=137900000;self.r['capture']['frequency_hz']=137700000
        self.assertEqual(self.result()['disposition'],'REVIEW')
    def test_explicit_regression_reference(self):
        for flag in ('pinned','reference','regression','explicit_protection'):
            self.r[flag]=True
            self.assertEqual(self.result()['disposition'],'PROTECTED'); self.r.pop(flag)
    def test_imported_capture_metadata_protection(self):
        for key,value in (('reference',True),('regression',True),('source','imported_reference')):
            self.r['capture'][key]=value
            self.assertEqual(self.result()['disposition'],'PROTECTED');self.r['capture'].pop(key)
    def test_old_1024ksps_failed(self):
        self.r['capture']['sample_rate_sps']=1024000
        self.r['pass']['sample_rate']=1024000
        self.r['pass']['record_start']=(retention.instant(self.r['pass']['record_stop'])-timedelta(seconds=200/(1024000*2))).isoformat()
        self.assertEqual(self.result()['disposition'],'DELETABLE')
    def test_hypothetical_delete_keeps_metadata_db_history_images(self):
        db=self.root/'data/watchkeeper-meteor.db'
        with sqlite3.connect(str(db)) as conn:
            conn.execute('CREATE TABLE meteor_passes(pass_id TEXT,metadata TEXT)')
            conn.execute('CREATE TABLE meteor_images(pass_id TEXT,product TEXT,width INTEGER,height INTEGER,path TEXT)')
            conn.execute('INSERT INTO meteor_passes VALUES(?,?)',(self.r['pass']['id'],json.dumps(dict(history=['original'],recording_path=str(self.raw)))))
            conn.execute('INSERT INTO meteor_images VALUES(?,?,?,?,?)',(self.r['pass']['id'],'diagnostic',10,10,'keep.png'))
        image=self.path.parent/'keep.png'; image.write_bytes(b'preserved')
        state=self.result(); state.update(raw_deleted=True,raw_exists=False,deletion=dict(classification='no_signal',reason='hypothetical expired candidate'))
        self.r['retention']=state; self.save(); retention.sync_db(self.root,self.r)
        with sqlite3.connect(str(db)) as conn:
            m=json.loads(conn.execute('SELECT metadata FROM meteor_passes').fetchone()[0])
            self.assertEqual(m['history'],['original']); self.assertEqual(m['raw_iq_state'],'deleted')
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM meteor_images').fetchone()[0],1)
        self.assertEqual(image.read_bytes(),b'preserved'); self.assertTrue(self.raw.exists()); self.assertTrue(self.path.exists())
    def test_apply_interlocks(self):
        for enabled,validated in ((False,False),(True,False),(False,True)):
            c=dict(cleanup_enabled=enabled,retention=dict(automatic_deletion_validated=validated))
            with self.assertRaises(RuntimeError): retention.cleanup(self.root,c,apply=True)
        self.assertTrue(self.raw.exists())
    def test_active_states(self):
        for state in retention.ACTIVE:
            self.r['state']=state; self.assertFalse(self.result()['eligible'])
    def test_missing_metadata_review(self):
        self.r['pass'].pop('record_stop'); self.assertEqual(self.result()['disposition'],'REVIEW')
    def test_null_timestamp_metadata_review(self):
        self.r['pass']['record_stop']=None; self.assertEqual(self.result()['disposition'],'REVIEW')
    def test_manual_reference_null_timestamps_protected(self):
        self.r['pass'].update(record_start=None,record_stop=None);self.r['reference']=True
        self.assertEqual(self.result()['disposition'],'PROTECTED')
    def test_fingerprint_changed_review(self):
        self.raw.write_bytes(b'y'*200); self.assertEqual(self.result()['disposition'],'REVIEW')
    def test_no_search_review(self):
        self.r.pop('frequency_evaluation'); self.assertEqual(self.result()['disposition'],'REVIEW')
    def test_budget_exhausted_review(self):
        self.r['frequency_evaluation']['error']='budget'; self.assertEqual(self.result()['disposition'],'REVIEW')
    def test_missing_offset_trial_review(self):
        self.r['frequency_evaluation']['trials'].pop(); self.assertEqual(self.result()['disposition'],'REVIEW')
    def test_wrong_decoder_identity_review(self):
        self.r['frequency_evaluation']['decoder_identity']={'changed':'yes'}; self.assertEqual(self.result()['disposition'],'REVIEW')
    def test_changed_search_config_review(self):
        self.c['frequency_evaluation']={'span_hz':55000}; self.assertEqual(self.result()['disposition'],'REVIEW')
    def test_missing_survey_review(self):
        self.r['frequency_evaluation'].pop('survey'); self.assertEqual(self.result()['disposition'],'REVIEW')
    def test_partial_evidence_review(self):
        self.r['decode_attempts'][0]['metrics']['channel_lines']['1']=10
        self.assertEqual(self.result()['disposition'],'REVIEW')
    def test_noise_snr_nosync_without_products_deletable(self):
        self.r['decode_attempts'][0]['metrics']['classification']='SIGNAL/UNUSABLE'
        self.r['decode_attempts'][0]['metrics']['decoder_activity']=['Viterbi : NOSYNC BER : 0.4, Deframer : NOSYNC']
        self.assertEqual(self.result()['disposition'],'DELETABLE')
    def test_synchronized_signal_without_products_review(self):
        self.r['decode_attempts'][0]['metrics']['classification']='SIGNAL/UNUSABLE'
        self.r['decode_attempts'][0]['metrics']['decoder_activity']=['Viterbi : SYNC BER : 0.1, Deframer : SYNC']
        self.assertEqual(self.result()['disposition'],'REVIEW')
    def test_grace_not_reset_by_new_evaluation(self):
        self.assertTrue(self.result()['eligible'])
        self.assertEqual(retention.instant(self.result()['deadline'])-retention.instant(self.r['pass']['record_stop']),timedelta(hours=24))
    def test_zero_byte_expired_failure(self):
        self.raw.write_bytes(b''); self.r.update(iq_fingerprint=retention.fingerprint(self.raw),captured_iq_bytes=0)
        self.r['capture']['status']='failed_no_iq'
        self.assertEqual(self.result()['disposition'],'DELETABLE'); self.assertEqual(self.result()['raw_bytes'],0)
    def test_zero_byte_completed_is_review(self):
        self.raw.write_bytes(b'');self.r.update(iq_fingerprint=retention.fingerprint(self.raw),captured_iq_bytes=0)
        self.assertEqual(self.result()['disposition'],'REVIEW')
    def test_processing_lock_defers(self):
        with (self.root/'data/meteor-auto/processing.lock').open('a') as stream:
            fcntl.flock(stream,fcntl.LOCK_EX)
            with self.assertRaises(BlockingIOError): retention.cleanup(self.root,self.c)
    def test_raw_inventory_includes_legacy(self):
        legacy=self.raw.with_name('legacy.cu8'); legacy.write_bytes(b'z'*200)
        legacy.with_suffix('.json').write_text(json.dumps(dict(self.r['capture'],iq_bytes=200,record_start=self.r['pass']['record_start'],record_stop=self.r['pass']['record_stop'])))
        rows=retention.inventory_records(self.root,self.c)
        self.assertEqual(len(rows),2)
        self.assertEqual(retention.classify(rows[1][1],self.c,self.at)['disposition'],'REVIEW')
    def test_missing_legacy_raw_still_has_history(self):
        r=copy.deepcopy(self.r);r.update(owner='meteor-retention-legacy-v1',iq=str(self.raw.with_name('hypothetically-deleted.cu8')))
        r['pass']['id']='legacy-hypothetical'
        p=self.root/'data/meteor-auto/retention-review/hypothetical/pass.json'
        p.parent.mkdir(parents=True);retention.atomic(p,r)
        rows=retention.inventory_records(self.root,self.c)
        self.assertEqual(len(rows),2);self.assertEqual(rows[1][1]['pass']['id'],'legacy-hypothetical')
        self.assertFalse(retention.classify(rows[1][1],self.c,self.at)['raw_exists'])
        self.assertTrue(p.exists());self.assertTrue(self.raw.exists())
    def test_reference_manifest(self):
        (self.root/'data/meteor-auto/retention-protected.json').write_text(json.dumps({'test.cu8':'reference'}))
        r=retention.inventory_records(self.root,self.c)[0][1]
        self.assertEqual(retention.classify(r,self.c,self.at)['disposition'],'PROTECTED')
    def test_nonblocking_notice_requires_completed_stages(self):
        out=self.root/'decode'; out.mkdir()
        a=copy.deepcopy(self.r['decode_attempts'][0]); a['output']=str(out); a['metrics']['evaluation_clean']=False
        log=out/'satdump.log'
        log.write_text('(E) curl_easy_perform() failed: Could not resolve host: celestrak.org\nDemodulation finished\nDone! Goodbye')
        self.assertTrue(frequency.trial_clean(a))
        log.write_text(log.read_text()+'\n(E) Decoder frame parser failed')
        self.assertFalse(frequency.trial_clean(a))
        log.write_text('Demodulation finished'); self.assertFalse(frequency.trial_clean(a))
    def test_original_pass_reference_pin_honored_after_review(self):
        review=self.root/'data/meteor-auto/retention-review'/self.raw.stem/'pass.json'
        review.parent.mkdir(parents=True); retention.atomic(review,self.r)
        self.r['pinned']=True; self.save()
        r=retention.inventory_records(self.root,self.c)[0][1]
        self.assertEqual(retention.classify(r,self.c,self.at)['disposition'],'PROTECTED')
    def test_outside_path_review(self):
        other=self.root/'outside.cu8'; other.write_bytes(self.raw.read_bytes())
        self.r.update(iq=str(other),iq_fingerprint=retention.fingerprint(other))
        self.assertEqual(self.result()['disposition'],'REVIEW')
    def test_shared_raw_lock_blocks_hypothetical_apply(self):
        c=dict(cleanup_enabled=True,retention=dict(automatic_deletion_validated=True))
        with self.raw.open('rb') as stream, patch.object(Path,'unlink',side_effect=AssertionError('No deletion permitted')):
            fcntl.flock(stream,fcntl.LOCK_SH)
            self.assertEqual(retention.cleanup(self.root,c,apply=True)['deleted'],[])
        self.assertTrue(self.raw.exists())
    def test_open_reader_blocks_hypothetical_apply(self):
        c=dict(cleanup_enabled=True,retention=dict(automatic_deletion_validated=True))
        with patch.object(retention,'open_elsewhere',return_value=True), patch.object(Path,'unlink',side_effect=AssertionError('No deletion permitted')):
            self.assertEqual(retention.cleanup(self.root,c,apply=True)['deleted'],[])
        self.assertTrue(self.raw.exists())
    def test_low_disk_keeps_reference(self):
        self.r['pinned']=True; self.save()
        s=retention.cleanup(self.root,self.c,free_gib=5)
        self.assertEqual(s['disk_pressure'],'critical'); self.assertEqual(s['would_delete'],[])
    def test_conservative_config_minima(self):
        for k,v in (('no_signal_hours',23),('poor_hours',47),('useful_hours',167)):
            with self.assertRaises(ValueError): retention.settings(dict(retention={k:v}))
    def test_frequency_pipeline_records_completed_supported_negative(self):
        import meteor_pipeline as pipeline
        self.r['decode_attempts']=self.r['decode_attempts'][:1]; self.save()
        def decoder(c,path,frequency_shift):
            r=json.loads(path.read_text());a=copy.deepcopy(r['decode_attempts'][0])
            a.update(output='shift'+str(frequency_shift),frequency_shift_hz=frequency_shift)
            r['decode_attempts'].append(a);retention.atomic(path,r)
        survey=dict(method='sampled_broadband_spectrum_v1',span_hz=60000,windows=24,candidate_carrier_offsets_hz=[45000,-45000])
        c=dict(self.c,decode_timeout_seconds=1800)
        with patch.object(pipeline,'ROOT',self.root),patch.object(pipeline,'STATE',self.root/'data/meteor-auto'),patch.object(pipeline.meteor_store,'persist'),patch.object(retention,'sync_db'),patch.object(frequency,'survey',return_value=survey),patch.object(pipeline,'decode_once',side_effect=decoder) as decode:
            pipeline.evaluate_frequency(c,self.path)
        r=json.loads(self.path.read_text())
        self.assertEqual(decode.call_count,2); self.assertTrue(r['frequency_evaluation']['procedure_completed'])
        self.assertFalse(r['frequency_evaluation']['completed'])
        self.assertFalse(r['frequency_evaluation']['negative_result_verified'])
        self.assertEqual(retention.classify(r,c,self.at)['disposition'],'DELETABLE')
if __name__=='__main__': unittest.main()
