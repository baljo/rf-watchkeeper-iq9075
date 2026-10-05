# Test METEOR classification, recording-rate arguments, retention interlock and image route confinement; 2026-10-03 EEST, Thomas Vikström.
import json
from pathlib import Path
import struct
import tempfile
import unittest
from unittest.mock import patch
import zlib
import meteor_store as store
import meteor_pipeline as pipeline
import satdump_evk

def png(path,w=2,h=3):
    def chunk(k,v):
        return struct.pack('!I',len(v))+k+v+struct.pack('!I',zlib.crc32(k+v)&0xffffffff)
    path.write_bytes(b'\x89PNG\r\n\x1a\n'+chunk(b'IHDR',struct.pack('!IIBBBBB',w,h,8,0,0,0,0))+chunk(b'IDAT',zlib.compress((b'\0'+b'\xff'*w)*h))+chunk(b'IEND',b''))

class Tests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)
        self.out=self.root/'data/decode';self.out.mkdir(parents=True)
    def tearDown(self): self.tmp.cleanup()
    def test_success_and_channel_height(self):
        png(self.out/'MSU-MR-1.png')
        r=store.inspect_output(self.out)
        self.assertEqual(r['classification'],'SUCCESS');self.assertEqual(r['channel_lines']['1'],3)
    def test_zero_exit_and_empty_png_fail(self):
        (self.out/'MSU-MR-1.png').write_bytes(b'not an image')
        self.assertEqual(store.inspect_output(self.out)['classification'],'EMPTY/FAILED')
    def test_signal_without_image(self):
        (self.out/'satdump.log').write_text('Channel 2: 40 lines\nSNR: 8.5\nViterbi locked')
        r=store.inspect_output(self.out)
        self.assertEqual(r['classification'],'SIGNAL/UNUSABLE');self.assertEqual(r['peak_snr'],8.5)
    def test_initializing_is_not_signal(self):
        (self.out/'satdump.log').write_text('Initializing Viterbi decoder and deframer\nSNR: 0')
        self.assertEqual(store.inspect_output(self.out)['classification'],'EMPTY/FAILED')
    def test_invalid_pipeline_even_zero_exit(self):
        png(self.out/'MSU-MR-1.png')
        (self.out/'satdump.log').write_text('Pipeline does not exist')
        self.assertEqual(store.inspect_output(self.out)['classification'],'EMPTY/FAILED')
    def test_runtime_error_and_timeout(self):
        png(self.out/'MSU-MR-1.png')
        self.assertEqual(store.inspect_output(self.out,124)['classification'],'EMPTY/FAILED')
        self.assertEqual(store.inspect_output(self.out,0,'timeout')['classification'],'EMPTY/FAILED')
    def test_corrupt_png(self):
        p=self.out/'MSU-MR-1.png';png(p);p.write_bytes(p.read_bytes()[:-12])
        self.assertEqual(store.inspect_output(self.out)['classification'],'EMPTY/FAILED')
    # Cover useful SIGSEGV output and retry suppression; 2026-10-05 13:55 EEST, Thomas Vikström.
    def test_sigsegv_useful_products(self):
        png(self.out/'MSU-MR-1.png',1568,888)
        (self.out/'satdump.log').write_text('Channel 1: 888 lines\nChannel 2: 896 lines\nChannel 4: 888 lines\nSNR: 7.069854')
        for rc in (139,-11):
            result=store.inspect_output(self.out,rc)
            self.assertEqual(result['classification'],'PARTIAL_SUCCESS')
            self.assertEqual(result['returncode'],rc)
            self.assertEqual(result['satdump_crash'],'SIGSEGV')
        self.assertEqual(store.inspect_output(self.out,1)['classification'],'EMPTY/FAILED')
        self.assertEqual(store.inspect_output(self.out,139,'timeout')['classification'],'EMPTY/FAILED')
        (self.out/'satdump.log').write_text('Pipeline does not exist')
        self.assertEqual(store.inspect_output(self.out,139)['classification'],'EMPTY/FAILED')
    def test_sigsegv_tiny_corrupt_or_low_line_products_fail(self):
        p=self.out/'MSU-MR-1.png';png(p)
        (self.out/'satdump.log').write_text('Channel 1: 888 lines')
        self.assertEqual(store.inspect_output(self.out,139)['classification'],'EMPTY/FAILED')
        png(p,1568,888)
        (self.out/'satdump.log').write_text('Channel 1: 10 lines')
        self.assertEqual(store.inspect_output(self.out,139)['classification'],'EMPTY/FAILED')
        p.write_bytes(p.read_bytes()[:-12])
        self.assertEqual(store.inspect_output(self.out,139)['classification'],'EMPTY/FAILED')
    def test_partial_decode_retained_and_not_retried(self):
        iq=self.root/'a.cu8';iq.write_bytes(b'00')
        record=self.root/'data/meteor-auto/passes/m24-20261005T014957Z/pass.json'
        record.parent.mkdir(parents=True)
        record.write_text(json.dumps(dict(owner='meteor-auto-v1',state='pending_decode',iq=str(iq),capture=dict(sample_rate_sps=1024000),captured_iq_bytes=2,
            **{'pass':dict(id='m24-20261005T014957Z',satellite='M2-4',sample_rate=1024000,record_start='2026-10-05T01:48:27+00:00')})))
        c=dict(satdump_command=['decoder'],satdump_prefix=[],satdump_extra=[],decode_timeout_seconds=30,max_decode_attempts=10,decode_retry_seconds=60)
        def run(args,**kwargs):
            png(Path(args[4])/'MSU-MR-1.png',1568,888)
            return type('Result',(),{'returncode':139})()
        with patch.object(pipeline,'ROOT',self.root),patch.object(pipeline,'STATE',self.root/'data/meteor-auto'),patch.object(pipeline,'decoder_ready',return_value=True),patch.object(pipeline.subprocess,'run',side_effect=run),patch.object(pipeline,'event'):
            pipeline.decode(c,record)
            r=json.loads(record.read_text())
            self.assertEqual(r['state'],'decoded_with_satdump_crash')
            self.assertEqual(r['decode_attempts'][0]['returncode'],139)
            with patch.object(pipeline,'records',return_value=[record]),patch.object(pipeline,'satellite_busy',return_value=None),patch.object(pipeline,'active',return_value=False),patch.object(pipeline,'decode') as decode,patch('builtins.print') as printed:
                pipeline.process(c)
                pipeline.worker_list(c,dry=True)
                decode.assert_not_called()
                printed.assert_called_with('[]')
            with self.assertRaises(RuntimeError):pipeline.worker_claim('m24-20261005T014957Z')
        db=self.root/'data/watchkeeper-meteor.db'
        history=store.history(db)[0]
        self.assertEqual(history['classification'],'PARTIAL_SUCCESS')
        self.assertEqual(history['satdump_crash'],'SIGSEGV')
        self.assertEqual(len(history['images']),1)
        self.assertTrue(store.image_file(str(history['images'][0]['id']),self.root,db).is_file())
    def test_argv_both_satellites(self):
        for sat in ('M2-3','M2-4'):
            c=dict(satdump_command=['python','satdump_evk.py'],satdump_prefix=[],satdump_pipeline='wrong',satdump_extra=['--dc_block','--satellite_number','{satellite_number}'])
            args=pipeline.decode_argv(c,dict(satellite=sat,sample_rate=256000),'a','b')
            self.assertIn('meteor_m2-x_lrpt',args);self.assertEqual(args[args.index('--samplerate')+1],'256000')
            self.assertEqual(args.count('--satellite_number'),1);self.assertEqual(args[args.index('--satellite_number')+1],sat)
    def test_wrapper_separate_options(self):
        iq=self.root/'a.cu8';iq.write_bytes(b'00')
        args=['meteor_m2-x_lrpt','baseband',str(iq),str(self.out),'--samplerate','256000','--baseband_format','cu8','--satellite_number','M2-3']
        self.assertEqual(satdump_evk.argv(args,'test')[-6:],args[-6:])
        with self.assertRaises(ValueError):satdump_evk.argv(args[:4]+['{}'],'test')
    def test_history_upsert_and_route(self):
        p=self.out/'MSU-MR-1.png';png(p)
        iq=self.root/'a.cu8';iq.write_bytes(b'00');db=self.root/'history.db'
        r=dict(iq=str(iq),pass_=dict(id='p1',satellite='M2-3',record_start='2026-09-28T19:30:42+00:00',sample_rate=256000,frequency=137900000))
        r['pass']=r.pop('pass_')
        a=dict(metrics=store.inspect_output(self.out),finished_at=store.stamp())
        store.persist(r,a,db);store.persist(r,a,db)
        passes=store.history(db);self.assertEqual(len(passes),1);self.assertEqual(len(passes[0]['images']),1)
        image=passes[0]['images'][0];self.assertNotIn('path',image)
        self.assertEqual(store.image_file(str(image['id']),self.root,db),p.resolve())
        for value in ('../a','0','999','1?path=/etc/passwd'):
            with self.assertRaises(ValueError):store.image_file(value,self.root,db)
        outside=self.root/'outside.png';png(outside)
        with store.connect(db) as c:c.execute('UPDATE meteor_images SET path=?',(str(outside),))
        with self.assertRaises(ValueError):store.image_file(str(image['id']),self.root,db)
    def test_cleanup_interlock(self):
        iq=self.root/'a.cu8';iq.write_bytes(b'00')
        with self.assertRaises(RuntimeError):pipeline.cleanup({'cleanup_enabled':True},True)
        self.assertEqual(iq.read_bytes(),b'00')
    def test_production_recording_metadata_overrides_planner(self):
        iq=self.root/'a.cu8';iq.write_bytes(b'00')
        metadata=self.root/'a.json';metadata.write_text(json.dumps(dict(satellite='M2-3',sample_rate_sps=256000,frequency_hz=137900000)))
        record=self.root/'pass.json';record.write_text(json.dumps(dict(iq=str(iq),capture_metadata=str(metadata),pass_=None,**{'pass':dict(id='p1',satellite='M2-3',sample_rate=1024000,frequency=137900000,record_start='2026-09-28T19:30:42+00:00')})))
        c=dict(satdump_command=['decoder'],satdump_prefix=[],satdump_extra=[],decode_timeout_seconds=30)
        def run(args,**kwargs):
            self.assertEqual(args[args.index('--samplerate')+1],'256000')
            png(Path(args[4])/'MSU-MR-1.png')
            return type('Result',(),{'returncode':0})()
        with patch.object(pipeline,'ROOT',self.root),patch.object(pipeline,'decoder_ready',return_value=True),patch.object(pipeline.subprocess,'run',side_effect=run),patch.object(pipeline,'event'):
            pipeline.decode(c,record)
        self.assertEqual(json.loads(record.read_text())['classification'],'SUCCESS')
        self.assertEqual(store.history(self.root/'data/watchkeeper-meteor.db')[0]['sample_rate'],256000)

if __name__=='__main__':unittest.main()
