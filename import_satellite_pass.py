# Import PCM8 RF64/WAV IQ with per-pass tuning and safe historical color-product processing through the shared decoder; 2026-10-03 21:54:00 EEST, Thomas Vikström.
import argparse
from datetime import datetime
import hashlib
import json
import os
from pathlib import Path
import shutil
import struct
import sys
import tempfile
from zoneinfo import ZoneInfo

import meteor_pipeline as pipeline
import meteor_store as store

ROOT = Path(__file__).resolve().parent
IMPORTS = ROOT / 'imports/satellite'
PRESETS = {
    '12-21-00_137665000Hz.wav': ('M2-3', '2026-09-20T12:21:00+03:00', '2026-09-20T12:38:00+03:00', 137665000),
    '15-04-00_138116000Hz.wav': ('M2-4', '2026-09-20T15:04:00+03:00', '2026-09-20T15:21:00+03:00', 138116000),
}


def inspect_wav(path):
    """Walk bounded RIFF chunks, resolving RF64 ds64 sizes without loading IQ."""
    path = Path(path)
    size = path.stat().st_size
    chunks, fmt, data, ds64 = [], None, None, None
    with path.open('rb') as f:
        head = f.read(12)
        if len(head) != 12:
            raise ValueError('Truncated container header')
        container, riff32, wave = struct.unpack('<4sI4s', head)
        if container not in (b'RIFF', b'RF64') or wave != b'WAVE':
            raise ValueError('Expected RIFF/WAVE or RF64/WAVE')
        if container == b'RF64' and riff32 != 0xffffffff:
            raise ValueError('RF64 requires the RIFF size sentinel')
        limit = size if container == b'RF64' else riff32 + 8
        if limit != size:
            raise ValueError('Container length differs from file length')
        offset = 12
        table = {}
        while offset < limit:
            if len(chunks) >= 4096 or offset + 8 > limit:
                raise ValueError('Invalid or excessive chunks')
            f.seek(offset)
            kind, count = struct.unpack('<4sI', f.read(8))
            payload = offset + 8
            if kind == b'ds64':
                if container != b'RF64' or ds64 is not None or count < 28 or count > 1024*1024:
                    raise ValueError('Invalid ds64')
                raw = f.read(count)
                if len(raw) != count:
                    raise ValueError('Truncated ds64')
                riff64, data64, samples64, entries = struct.unpack('<QQQI', raw[:28])
                if count != 28 + entries*12 or riff64 + 8 != size:
                    raise ValueError('Invalid ds64 table or file size')
                ds64 = dict(riff_size=riff64, data_size=data64, sample_count=samples64)
                for pos in range(28, count, 12):
                    key, value = struct.unpack('<4sQ', raw[pos:pos+12])
                    table.setdefault(key, []).append(value)
            elif count == 0xffffffff:
                if ds64 is None:
                    raise ValueError('Size sentinel before ds64')
                if kind == b'data':
                    count = ds64['data_size']
                elif table.get(kind):
                    count = table[kind].pop(0)
                else:
                    raise ValueError('Unresolved RF64 chunk size')
            if payload + count + (count % 2) > limit:
                raise ValueError('Chunk exceeds container bounds')
            chunks.append(dict(kind=kind.decode('ascii', 'replace'), offset=offset, size=count))
            if kind == b'fmt ':
                if fmt is not None or not 16 <= count <= 4096:
                    raise ValueError('Invalid fmt chunk')
                f.seek(payload)
                raw = f.read(count)
                code, channels, rate, byte_rate, align, bits = struct.unpack('<HHIIHH', raw[:16])
                mask = None
                if code == 0xfffe:
                    if count < 40 or struct.unpack('<H', raw[16:18])[0] < 22:
                        raise ValueError('Invalid extensible PCM')
                    valid, mask = struct.unpack('<HI', raw[18:24])
                    if valid != 8 or raw[24:40] != bytes.fromhex('0100000000001000800000aa00389b71'):
                        raise ValueError('Only PCM8 extensible IQ is supported')
                elif code != 1:
                    raise ValueError('Only integer PCM is supported')
                if channels != 2 or bits != 8 or align != 2 or byte_rate != rate*2 or not 1 <= rate <= 10000000:
                    raise ValueError('Expected two interleaved unsigned PCM8 channels and consistent sample rate')
                fmt = dict(sample_rate=rate, bit_depth=bits, channel_count=channels, block_align=align,
                           byte_rate=byte_rate, audio_format=code, channel_mask=mask)
            elif kind == b'data':
                if data is not None or not count or count % 2:
                    raise ValueError('Expected one nonempty, frame-aligned IQ data chunk')
                data = dict(data_offset=payload, data_size=count)
            offset = payload + count + count % 2
    if fmt is None or data is None or container == b'RF64' and ds64 is None:
        raise ValueError('Missing fmt, data or ds64')
    frames = data['data_size']//2
    if ds64 and (ds64['data_size'] != data['data_size'] or ds64['sample_count'] not in (0, frames)):
        raise ValueError('ds64 data/sample count mismatch')
    expected = ['fmt ', 'data'] if container == b'RIFF' else ['ds64', 'fmt ', 'data']
    direct = ([c['kind'] for c in chunks] == expected and
              next(c['size'] for c in chunks if c['kind'] == 'fmt ') == 16 and
              data['data_offset'] == (44 if container == b'RIFF' else 80) and
              data['data_offset'] + data['data_size'] == size and
              (container != b'RF64' or chunks[0]['size'] == 28))
    return dict(container=container.decode(), file_size=size, **fmt, **data, duration_seconds=frames/fmt['sample_rate'],
                complex_samples=frames, layout='interleaved I,Q (SDR# convention; not encoded by WAV)',
                direct_satdump_compatible=direct, chunks=chunks, ds64=ds64)


def digest(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for block in iter(lambda: f.read(4*1024*1024), b''):
            h.update(block)
    return h.hexdigest()


def extract(path, header, destination):
    """Copy the data chunk verbatim; no DSP, quantization, or resampling."""
    h = hashlib.sha256()
    with Path(path).open('rb') as src, Path(destination).open('xb') as out:
        src.seek(header['data_offset'])
        remaining = header['data_size']
        while remaining:
            block = src.read(min(4*1024*1024, remaining))
            if not block:
                raise ValueError('IQ payload truncated during extraction')
            out.write(block)
            h.update(block)
            remaining -= len(block)
        out.flush()
        os.fsync(out.fileno())
    if digest(destination) != h.hexdigest():
        raise ValueError('Extracted payload checksum mismatch')
    return h.hexdigest()


def timestamp(value):
    d = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if d.tzinfo is None:
        d = d.replace(tzinfo=ZoneInfo('Europe/Helsinki'))
    return d.isoformat()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__ or 'Import historical SDR# PCM8 IQ; original WAV is retained.')
    parser.add_argument('recording', type=Path)
    parser.add_argument('--canonical', action='store_true', help='Use supplied September 20 Airspy metadata by filename')
    parser.add_argument('--inspect-only', action='store_true')
    parser.add_argument('--satellite', choices=('M2-3', 'M2-4'))
    parser.add_argument('--start-time')
    parser.add_argument('--end-time')
    parser.add_argument('--center-frequency', type=int)
    parser.add_argument('--sample-rate', type=int, help='Expected rate; actual header rate is always used')
    # Tune imported wideband recordings inside SatDump without rewriting samples; 2026-10-03 21:47:00 EEST, Thomas Vikström.
    tuning = parser.add_mutually_exclusive_group()
    tuning.add_argument('--signal-frequency', type=int, help='RF frequency to decode; canonical recordings default to 137900000 Hz')
    tuning.add_argument('--frequency-shift', type=int, help='Explicit signed SatDump frequency translation in Hz')
    parser.add_argument('--source', default='imported_airspy')
    parser.add_argument('--receiver', default='Airspy')
    parser.add_argument('--capture-host', default='Dell')
    parser.add_argument('--capture-mode', default='outdoor')
    parser.add_argument('--notes', default='Known-good outdoor Airspy reception; SDR# IQ recording.')
    parser.add_argument('--reference', action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument('--iq-order', choices=('IQ',), default='IQ', help='SDR# I then Q; no channel swap')
    parser.add_argument('--retry', action='store_true', help='Add a new attempt, preserving all existing output')
    args = parser.parse_args(argv)
    path = args.recording.resolve(strict=True)
    if args.recording.is_symlink() or not path.is_file():
        raise ValueError('Recording must be a regular file')
    header = inspect_wav(path)
    print(json.dumps(header, indent=2), flush=True)
    if args.inspect_only:
        return 0
    if args.canonical:
        if path.name not in PRESETS:
            raise ValueError('Unknown canonical filename')
        args.satellite, args.start_time, args.end_time, args.center_frequency = PRESETS[path.name]
        args.sample_rate = 1024000
    if not all((args.satellite, args.start_time, args.end_time, args.center_frequency)):
        raise ValueError('Provide satellite, start/end time and center frequency, or --canonical')
    start, end = timestamp(args.start_time), timestamp(args.end_time)
    if pipeline.dt(end) <= pipeline.dt(start) or args.center_frequency <= 0:
        raise ValueError('Invalid capture interval or frequency')
    if args.sample_rate and args.sample_rate != header['sample_rate']:
        raise ValueError('Header sample rate differs from expected metadata')
    c = pipeline.config(ROOT/'meteor-config.json')
    signal_frequency = args.signal_frequency or (137900000 if args.canonical else args.center_frequency)
    shift = args.frequency_shift if args.frequency_shift is not None else args.center_frequency-signal_frequency
    if abs(shift) >= header['sample_rate']/2:
        raise ValueError('Requested signal lies outside the recording bandwidth')
    c = dict(c, satdump_extra=list(c.get('satdump_extra', []))+['--freq_shift', str(shift), '--import-no-projection'])
    with pipeline.lock('processing'):
        if pipeline.satellite_busy() or pipeline.active(pipeline.CAPTURE_SERVICE):
            raise RuntimeError('Satellite capture is active; retry when idle')
        if not pipeline.decoder_ready(c):
            raise RuntimeError('Configured SatDump runtime is unavailable')
        before = pipeline.fingerprint(path)
        original_sha = digest(path)
        if pipeline.fingerprint(path) != before:
            raise RuntimeError('Original changed during validation')
        pid = 'import-' + args.satellite.lower().replace('-', '') + '-' + pipeline.dt(start).strftime('%Y%m%dT%H%M%SZ') + '-' + original_sha[:12]
        folder = ROOT/'data/satellite-imports'/pid
        folder.mkdir(parents=True, exist_ok=True)
        record_path = folder/'pass.json'
        capture = dict(satellite=args.satellite, record_start=start, record_stop=end, pass_start_10deg=start, pass_stop_10deg=end,
                       sample_rate_sps=header['sample_rate'], frequency_hz=args.center_frequency,
                       source=args.source, receiver=args.receiver, capture_host=args.capture_host, capture_mode=args.capture_mode,
                       reference=args.reference, input_format='SDR# '+header['container']+' PCM8 IQ', notes=args.notes,
                       recording_path=str(path), original_sha256=original_sha, wav_properties=header, iq_order=args.iq_order,
                       timing_basis='user-supplied recording interval; exact sample duration in wav_properties')
        if record_path.exists():
            r = pipeline.read(record_path)
            if r['capture'] != capture:
                raise ValueError('Metadata differs from existing import; refusing overwrite')
            if r.get('classification') == 'SUCCESS' and not args.retry:
                print(json.dumps(dict(pass_id=pid, status='already imported', record=str(record_path))))
                return 0
            if not args.retry:
                raise ValueError('Existing incomplete/failed import; use --retry to create a new attempt')
        else:
            r = dict(owner='satellite-import-v1', schema_version=1, iq=str(path), capture=capture,
                     state='pending_decode', **{'pass': dict(id=pid, satellite=args.satellite, start=start, stop=end,
                                                            record_start=start, sample_rate=header['sample_rate'], frequency=args.center_frequency)})
            pipeline.save(record_path, r)
        temp_dir = None
        try:
            r['import_processing'] = dict(signal_frequency=signal_frequency if args.frequency_shift is None else args.center_frequency-shift,
                                          frequency_shift_hz=shift, tuning_basis='explicit option or canonical 137.9 MHz LRPT; verified by spectrum',
                                          profile='satellite-import-satdump.json', map_projection=False,
                                          projection_note='Optional maps/geographic underlays disabled for historical imports after SatDump 1.2.2 timestamp-filter crashes; channel/color/geometric correction retained')
            if header['direct_satdump_compatible']:
                iq = path
                r['baseband_handling'] = 'direct WAV/RF64 with cu8; validated fixed header layout'
            else:
                reserve = max(2*1024**3, int(c['min_free_gib']*1024**3))
                if shutil.disk_usage(folder).free < header['data_size'] + reserve:
                    raise RuntimeError('Insufficient disk space for lossless extraction and configured reserve')
                temp_dir = Path(tempfile.mkdtemp(prefix='iq-', dir=folder))
                iq = temp_dir/'payload.cu8'
                r['baseband_handling'] = 'verbatim data chunk extraction; no resampling or requantization'
                r['temporary_baseband'] = str(iq)
                pipeline.save(record_path, r)
                r['payload_sha256'] = extract(path, header, iq)
            r['iq'] = str(iq)
            pipeline.save(record_path, r)
            if pipeline.fingerprint(path) != before:
                raise RuntimeError('Original changed before decoding')
            pipeline.decode(c, record_path)
            r = pipeline.read(record_path)
            if pipeline.fingerprint(path) != before or digest(path) != original_sha:
                raise RuntimeError('Original recording changed during processing')
            r['original_verified_unchanged'] = True
            if r['classification'] == 'SUCCESS' and temp_dir:
                # Delete only this attempt's owned, verified temporary payload, after persisted success.
                iq.unlink()
                temp_dir.rmdir()
                r['temporary_deleted'] = str(iq)
                r['temporary_baseband'] = None
            r['iq'] = str(path)
            pipeline.save(record_path, r)
            store.persist(r, r['decode_attempts'][-1])
            print(json.dumps(dict(pass_id=pid, record=str(record_path), classification=r['classification'],
                                  command=r['decode_attempts'][-1]['command'], images=r['decode_attempts'][-1]['products'],
                                  temporary_deleted=r.get('temporary_deleted')), indent=2))
            return 0 if r['classification'] == 'SUCCESS' else 2
        except BaseException:
            r = pipeline.read(record_path)
            r['import_error'] = 'Import interrupted or failed; original and partial output retained'
            pipeline.save(record_path, r)
            raise


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except (OSError, ValueError, RuntimeError) as exc:
        print('Satellite import: '+str(exc), file=sys.stderr)
        raise SystemExit(1)
