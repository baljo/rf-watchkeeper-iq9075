# Test RF64 bounds, lossless IQ extraction, shared decode integration and imported pass provenance with isolated fixtures; 2026-10-03 21:25:52 EEST, Thomas Vikström.
from contextlib import contextmanager
from pathlib import Path
import json
import struct
import tempfile
import unittest
from unittest.mock import patch
import zlib

import import_satellite_pass as imp
import meteor_store as store


def chunk(kind, payload):
    return kind + struct.pack('<I', len(payload)) + payload + (b'\0' if len(payload)%2 else b'')


def wav(payload, rf64=True, extra=False, bits=8, channels=2):
    fmt = chunk(b'fmt ', struct.pack('<HHIIHH', 1, channels, 1024000, 2048000, 2, bits))
    junk = chunk(b'JUNK', b'abc') if extra else b''
    data = b'data' + struct.pack('<I', 0xffffffff if rf64 else len(payload)) + payload
    body = fmt + junk + data
    if rf64:
        body = chunk(b'ds64', struct.pack('<QQQI', len(body)+40, len(payload), len(payload)//2, 0)) + body
    return (b'RF64' if rf64 else b'RIFF') + struct.pack('<I', 0xffffffff if rf64 else len(body)+4) + b'WAVE' + body


def png(path):
    def c(kind, data):
        return struct.pack('!I', len(data))+kind+data+struct.pack('!I', zlib.crc32(kind+data)&0xffffffff)
    path.write_bytes(b'\x89PNG\r\n\x1a\n'+c(b'IHDR',struct.pack('!IIBBBBB',2,2,8,0,0,0,0))+c(b'IDAT',zlib.compress(b'\0\x01\x02'*2))+c(b'IEND',b''))


class ImportTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.input = self.root/'12-21-00_137665000Hz.wav'
        self.payload = bytes(range(256))*32

    def tearDown(self):
        self.temp.cleanup()

    def test_canonical_rf64_direct(self):
        self.input.write_bytes(wav(self.payload))
        h = imp.inspect_wav(self.input)
        self.assertTrue(h['direct_satdump_compatible'])
        self.assertEqual((h['container'], h['data_offset'], h['sample_rate'], h['bit_depth'], h['channel_count']), ('RF64',80,1024000,8,2))
        self.assertEqual(h['data_size'], len(self.payload))

    def test_riff_direct(self):
        self.input.write_bytes(wav(self.payload, rf64=False))
        self.assertTrue(imp.inspect_wav(self.input)['direct_satdump_compatible'])

    def test_extra_odd_chunk_extract_exact(self):
        self.input.write_bytes(wav(self.payload, extra=True))
        original = self.input.read_bytes()
        h = imp.inspect_wav(self.input)
        self.assertFalse(h['direct_satdump_compatible'])
        output = self.root/'payload.cu8'
        self.assertEqual(imp.extract(self.input,h,output), imp.digest(output))
        self.assertEqual(output.read_bytes(), self.payload)
        self.assertEqual(self.input.read_bytes(), original)

    def test_invalid_headers(self):
        variants = [wav(self.payload, bits=16), wav(self.payload, channels=1), wav(self.payload)[:-1],
                    b'nope'+wav(self.payload)[4:]]
        for raw in variants:
            self.input.write_bytes(raw)
            with self.assertRaises(ValueError): imp.inspect_wav(self.input)

    def test_bad_ds64(self):
        raw = bytearray(wav(self.payload))
        struct.pack_into('<Q',raw,28,len(self.payload)+2)
        self.input.write_bytes(raw)
        with self.assertRaises(ValueError): imp.inspect_wav(self.input)

    def test_fmt_extension_disables_direct(self):
        fmt = chunk(b'fmt ',struct.pack('<HHIIHHH',1,2,1024000,2048000,2,8,0))
        body = fmt+chunk(b'data',self.payload)
        self.input.write_bytes(b'RIFF'+struct.pack('<I',len(body)+4)+b'WAVE'+body)
        self.assertFalse(imp.inspect_wav(self.input)['direct_satdump_compatible'])

    def workflow(self, success):
        self.input.write_bytes(wav(self.payload,extra=True))
        original = imp.digest(self.input)
        db = self.root/'data/watchkeeper-meteor.db'
        @contextmanager
        def unlocked(name): yield
        def decode(config,path):
            # Confirm canonical center-frequency correction stays local to the import; 2026-10-03 21:47:00 EEST, Thomas Vikström.
            self.assertEqual(config['satdump_extra'],['--freq_shift','-235000','--import-no-projection'])
            r = imp.pipeline.read(path)
            self.assertEqual(Path(r['iq']).read_bytes(), self.payload)
            out = Path(path).parent/'decode-1'
            out.mkdir()
            if success: png(out/'MSU-MR-1.png')
            metrics = store.inspect_output(out)
            a = dict(output=str(out),finished_at=store.stamp(),command=['shared-path'],metrics=metrics,products=[i['path'] for i in metrics['images']])
            r.update(decode_attempts=[a],classification=a['metrics']['classification'])
            imp.pipeline.save(path,r)
            store.persist(r,a,db)
        original_persist = store.persist
        with patch.object(imp,'ROOT',self.root), patch.object(imp.pipeline,'config',return_value={'min_free_gib':1}), \
             patch.object(imp.pipeline,'lock',unlocked), patch.object(imp.pipeline,'satellite_busy',return_value=None), \
             patch.object(imp.pipeline,'active',return_value=False), patch.object(imp.pipeline,'decoder_ready',return_value=True), \
             patch.object(imp.pipeline,'decode',decode), patch.object(imp.store,'persist',side_effect=lambda r,a,*unused: original_persist(r,a,db)):
            self.assertEqual(imp.main([str(self.input),'--canonical']), 0 if success else 2)
        self.assertEqual(imp.digest(self.input),original)
        h = store.history(db)[0]
        self.assertEqual((h['source'],h['receiver'],h['capture_host'],h['reference']),('imported_airspy','Airspy','Dell',True))
        self.assertEqual(h['recording_path'],str(self.input))
        self.assertEqual(h['sample_rate'],1024000)
        self.assertEqual(h['image_count'], 1 if success else 0)
        r = json.loads(next((self.root/'data/satellite-imports').glob('*/pass.json')).read_text())
        if success:
            self.assertFalse(Path(r['temporary_deleted']).exists())
        else:
            self.assertEqual(Path(r['temporary_baseband']).read_bytes(),self.payload)

    def test_success_deletes_only_temporary_iq(self): self.workflow(True)
    def test_failure_retains_temporary_iq(self): self.workflow(False)

    # Verify the projection workaround cannot affect unflagged automatic calls; 2026-10-03 21:56:00 EEST, Thomas Vikström.
    def test_profile_is_explicit_and_controlled(self):
        import satdump_evk
        self.input.write_bytes(wav(self.payload))
        output=self.root/'output'
        output.mkdir()
        args=['meteor_m2-x_lrpt','baseband',str(self.input),str(output),'--samplerate','1024000','--baseband_format','cu8','--satellite_number','M2-3']
        with patch.object(satdump_evk,'ROOT',self.root):
            automatic=satdump_evk.argv(args,'fixture')
            self.assertFalse(any('satdump_cfg.json' in x for x in automatic))
            with self.assertRaises(ValueError): satdump_evk.argv(args+['--import-no-projection'],'fixture')
            (self.root/'data').mkdir()
            (self.root/'data/satellite-import-satdump.json').write_text('{}')
            imported=satdump_evk.argv(args+['--import-no-projection'],'fixture')
            self.assertTrue(any('target=/usr/share/satdump/satdump_cfg.json,readonly' in x for x in imported))
            self.assertNotIn('--import-no-projection',imported)

    def test_observed_channel_log_layout(self):
        output=self.root/'output'
        output.mkdir()
        png(output/'MSU-MR-1.png')
        (output/'satdump.log').write_text('MSU-MR Channel 1 Lines  : 1328\nChannel 2: 1320 lines\n')
        metrics=store.inspect_output(output)
        self.assertEqual(metrics['channel_lines']['1'],1328)
        self.assertEqual(metrics['channel_lines']['2'],1320)
        self.assertEqual(metrics['line_count_source'],'decoder_log')

    # Earlier attempt imagery must remain stored when history selects the latest product; 2026-10-03 22:04:00 EEST, Thomas Vikström.
    def test_history_latest_product_preserves_previous(self):
        db=self.root/'history.db'
        record=dict(iq=str(self.input),capture={},**{'pass':dict(id='retry-pass',satellite='M2-3')})
        for number in (1,2):
            output=self.root/('decode-'+str(number))
            output.mkdir()
            png(output/'MSU-MR-1.png')
            store.persist(record,dict(metrics=store.inspect_output(output),output=str(output),finished_at=store.stamp()),db)
        history=store.history(db)[0]
        self.assertEqual(history['image_count'],1)
        self.assertEqual(history['retained_image_count'],2)
        self.assertEqual(history['images'][0]['id'],2)
        with store.connect(db) as c: self.assertEqual(c.execute('SELECT COUNT(*) FROM meteor_images').fetchone()[0],2)
        self.assertTrue((self.root/'decode-1/MSU-MR-1.png').exists())


if __name__ == '__main__': unittest.main()
