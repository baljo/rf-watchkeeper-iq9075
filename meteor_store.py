# Retain METEOR evidence and all image attempts while serving the newest version of each pass product; 2026-10-03 22:04:00 EEST, Thomas Vikström.
import json
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
import re
import sqlite3
import struct
import zlib
from pass_conditions import recorded

ROOT = Path(__file__).resolve().parent
DB = ROOT / 'data/watchkeeper-meteor.db'
PIPELINE = 'meteor_m2-x_lrpt'

def stamp():
    return datetime.now(timezone.utc).isoformat()

def png_info(path):
    """Validate complete PNG chunks, CRCs, inflate size and scanline filters."""
    data = Path(path).read_bytes()
    if len(data) > 64*1024*1024 or data[:8] != b'\x89PNG\r\n\x1a\n':
        raise ValueError('Invalid PNG')
    offset, compressed, header, ended = 8, bytearray(), None, False
    while offset + 12 <= len(data):
        size = struct.unpack('!I', data[offset:offset+4])[0]
        kind = data[offset+4:offset+8]
        payload = data[offset+8:offset+8+size]
        if offset+12+size > len(data):
            raise ValueError('Truncated PNG')
        crc = struct.unpack('!I', data[offset+8+size:offset+12+size])[0]
        if zlib.crc32(kind+payload) & 0xffffffff != crc:
            raise ValueError('PNG CRC mismatch')
        if header is None and kind != b'IHDR':
            raise ValueError('Missing PNG header')
        if kind == b'IHDR':
            if header is not None or size != 13:
                raise ValueError('Invalid PNG header')
            header = struct.unpack('!IIBBBBB', payload)
        elif kind == b'IDAT':
            compressed.extend(payload)
        elif kind == b'IEND':
            ended = size == 0 and offset+12 == len(data)
            break
        offset += size+12
    if not header or not ended:
        raise ValueError('Incomplete PNG')
    w,h,depth,color,compression,filters,interlace = header
    channels = {0:1,2:3,3:1,4:2,6:4}.get(color)
    if not channels or depth not in (8,16) or color == 3 or compression or filters or interlace or not (1 <= w <= 16000 and 1 <= h <= 16000):
        raise ValueError('Unsupported or invalid PNG layout')
    stride = 1+(w*channels*depth+7)//8
    expected = stride*h
    if expected > 128*1024*1024:
        raise ValueError('PNG too large')
    decoder = zlib.decompressobj()
    raw = decoder.decompress(bytes(compressed), expected+1)
    if len(raw) != expected or not decoder.eof or decoder.unused_data or any(raw[i] > 4 for i in range(0,len(raw),stride)):
        raise ValueError('Invalid PNG pixels')
    return w,h

def inspect_output(output, returncode=0, error=None, known_lines=None):
    output = Path(output)
    lines = {str(i):0 for i in range(1,7)}
    log = ''
    for name in ('satdump.log','decode.log'):
        p = output/name
        if p.is_file():
            with p.open('rb') as stream:
                stream.seek(max(0,p.stat().st_size-8*1024*1024))
                log += stream.read().decode('utf-8','replace')
    log = re.sub(r'\x1b\[[0-9;]*m','',log)
    # Accept both observed SatDump channel-line log layouts; 2026-10-03 21:56:00 EEST, Thomas Vikström.
    for channel,before,after in re.findall(r'Channel\s+([1-6])(?:\s+Lines\s*:\s*(\d+)|\s*:\s*(\d+)\s+lines)',log,re.I):
        lines[channel] = max(lines[channel],int(before or after))
    source = 'decoder_log'
    images=[]
    if output.is_dir():
        for p in sorted(output.rglob('*.png')):
            if p.is_symlink() or output.resolve() not in p.resolve().parents or 'MSU-MR' not in p.name and 'msu_mr' not in p.name:
                continue
            try:
                width,height=png_info(p)
            except (OSError,ValueError,zlib.error,struct.error):
                continue
            channel=re.fullmatch(r'MSU-MR-([1-6])\.png',p.name)
            if channel and not lines[channel[1]]:
                lines[channel[1]]=height
                source='decoder_log_or_native_channel_png_height'
            rank = 0 if '124' in p.name and 'corrected' in p.name else 1 if 'corrected' in p.name else 2 if 'rgb' in p.name else 3
            images.append(dict(path=str(p.resolve()),product=p.stem,width=width,height=height,rank=rank,created_at=stamp()))
    if known_lines:
        lines.update({str(k):int(v) for k,v in known_lines.items()})
        source='manual_positive_regression'
    invalid=bool(re.search(r'(invalid|unknown|not found|does not exist).*pipeline|pipeline.*(invalid|unknown|not found|does not exist)|unrecognized (argument|option)|EVK SatDump:|time limit reached',log,re.I))
    snrs=[]
    for value in re.findall(r'\bSNR\s*[:=]\s*(-?\d+(?:\.\d+)?)',log,re.I):
        snrs.append(float(value))
    activity=any(lines.values()) or bool(re.search(r'(?:deframer|viterbi).*\b(?:locked|synced)\b',log,re.I)) or any(v>0 for v in snrs)
    # Recognize substantial validated products after SIGSEGV; 2026-10-05 13:55 EEST, Thomas Vikström.
    crash = 'SIGSEGV' if returncode in (139, -11) else None
    useful = any(im['width'] >= 256 and im['height'] >= 128 and
                 lines.get(im['product'].removeprefix('MSU-MR-'), 0) >= 128
                 for im in images if re.fullmatch(r'MSU-MR-[1-6]', im['product']))
    classification = ('PARTIAL_SUCCESS' if crash and useful and not error and not invalid else
                      'EMPTY/FAILED' if error or returncode != 0 or invalid else
                      'SUCCESS' if any(lines.values()) and images else
                      'SIGNAL/UNUSABLE' if activity else 'EMPTY/FAILED')
    statuses = re.findall(r'(?:viterbi|deframer)[^\r\n]{0,160}',log,re.I)
    stages_complete = 'Demodulation finished' in log and 'Done! Goodbye' in log
    explicit_error = bool(re.search(r'\[error\]|\[critical\]|\(E\)|\(C\)|\bfatal\b|Segmentation fault', log, re.I))
    evaluation_errors = [line[-600:] for line in log.splitlines() if re.search(r'\[error\]|\[critical\]|\(E\)|\(C\)|\bfatal\b|Segmentation fault', line, re.I)][-20:]
    return dict(classification=classification,channel_lines=lines,line_count_source=source,images=images,
                evaluation_clean=returncode == 0 and not error and not invalid and not explicit_error and stages_complete,
                evaluation_errors=evaluation_errors,
                peak_snr=max(snrs) if snrs else None,decoder_activity=statuses[-10:],error=error,returncode=returncode,
                satdump_crash=crash)

@contextmanager
def connect(db=DB):
    Path(db).parent.mkdir(parents=True,exist_ok=True)
    c=sqlite3.connect(str(db),timeout=5)
    c.execute('PRAGMA foreign_keys=ON')
    c.executescript('''CREATE TABLE IF NOT EXISTS meteor_passes (
      pass_id TEXT PRIMARY KEY, satellite TEXT NOT NULL, record_start TEXT,
      status TEXT NOT NULL, processed_at TEXT NOT NULL, metadata TEXT NOT NULL);
      CREATE TABLE IF NOT EXISTS meteor_images (
      id INTEGER PRIMARY KEY, pass_id TEXT NOT NULL REFERENCES meteor_passes(pass_id),
      product TEXT NOT NULL, path TEXT NOT NULL, width INTEGER, height INTEGER,
      rank INTEGER NOT NULL, created_at TEXT NOT NULL, UNIQUE(pass_id,path));
      CREATE INDEX IF NOT EXISTS meteor_pass_time ON meteor_passes(record_start);''')
    try:
        with c:
            yield c
    finally:
        c.close()

def persist(record,attempt,db=DB):
    p=record['pass']; m=record.get('capture',{})
    result=attempt['metrics']; pid=p['id']
    metadata=dict(pass_id=pid,satellite=p['satellite'],pass_start=m.get('pass_start_10deg',p.get('start')),
      pass_stop=m.get('pass_stop_10deg',p.get('stop')),record_start=m.get('record_start',p.get('record_start')),
      peak_elevation=p.get('peak_deg'),peak_azimuth=p.get('peak_azimuth'),iq_filename=Path(record['iq']).name,
      sample_rate=m.get('sample_rate_sps',p.get('sample_rate')),frequency=m.get('frequency_hz',p.get('frequency')),
      pipeline=PIPELINE,processing_timestamp=attempt['finished_at'],raw_iq_state='retained' if Path(record['iq']).is_file() else 'missing',
      **{k:result[k] for k in ('classification','channel_lines','line_count_source','peak_snr','decoder_activity','error','returncode')})
    # Store historical provenance alongside the existing pass metadata; 2026-10-03 21:25:52 EEST, Thomas Vikström.
    recording = Path(m.get('recording_path', record['iq']))
    metadata.update(source=m.get('source', 'automatic_evk'), receiver=m.get('receiver', 'RTL-SDR'),
      capture_host=m.get('capture_host', 'Dragonwing IQ-9075 EVK'), capture_mode=m.get('capture_mode', 'automatic'),
      reference=bool(m.get('reference', False)), input_format=m.get('input_format', 'cu8'),
      start_time=metadata['record_start'], end_time=m.get('record_stop', p.get('stop')),
      center_frequency=metadata['frequency'], recording_path=str(recording), notes=m.get('notes', ''),
      processing_status=result['classification'], output_directory=attempt.get('output'), satdump_crash=result.get('satdump_crash'),
      original_sha256=m.get('original_sha256'), wav_properties=m.get('wav_properties'),
      baseband_handling=record.get('baseband_handling'), temporary_baseband=record.get('temporary_baseband'),
      import_processing=record.get('import_processing'), retention=record.get('retention'),
      pinned=record.get('pinned', False), frequency_evaluation=record.get('frequency_evaluation'),
      temporary_deleted=record.get('temporary_deleted'), raw_iq_state='retained' if recording.is_file() else 'missing')
    with connect(db) as c:
        # Keep saved geometry across decoder retries and partial metadata updates.
        existing = c.execute('SELECT metadata FROM meteor_passes WHERE pass_id=?', (pid,)).fetchone()
        conditions = json.loads(existing[0]).get('conditions', {}) if existing else {}
        conditions.update(recorded(m, p))
        metadata['conditions'] = conditions
        c.execute('INSERT INTO meteor_passes VALUES (?,?,?,?,?,?) ON CONFLICT(pass_id) DO UPDATE SET status=excluded.status,processed_at=excluded.processed_at,metadata=excluded.metadata',
          (pid,p['satellite'],metadata['record_start'],result['classification'],attempt['finished_at'],json.dumps(metadata)))
        # Keep all previous products across retries; never remove disk images.
        for im in result['images']:
            c.execute('INSERT OR IGNORE INTO meteor_images(pass_id,product,path,width,height,rank,created_at) VALUES(?,?,?,?,?,?,?)',
              (pid,im['product'],im['path'],im['width'],im['height'],im['rank'],im['created_at']))
        metadata['image_count'] = c.execute('SELECT COUNT(*) FROM meteor_images WHERE pass_id=?', (pid,)).fetchone()[0]
        c.execute('UPDATE meteor_passes SET metadata=? WHERE pass_id=?', (json.dumps(metadata), pid))

def history(db=DB):
    if not Path(db).is_file():
        return []
    c=sqlite3.connect(Path(db).resolve().as_uri()+'?mode=ro',uri=True,timeout=5)
    c.row_factory=sqlite3.Row
    try:
        passes=[]
        for row in c.execute('SELECT * FROM meteor_passes ORDER BY record_start DESC,pass_id DESC LIMIT 500'):
            p=json.loads(row['metadata'])
            # Normalize older automatic records without rewriting their evidence; 2026-10-03 21:25:52 EEST, Thomas Vikström.
            for key,value in dict(source='automatic_evk',receiver='RTL-SDR',capture_host='Dragonwing IQ-9075 EVK',capture_mode='automatic',reference=False).items():
                p.setdefault(key,value)
            # Prefer current products while retaining every earlier image row and file; 2026-10-03 22:04:00 EEST, Thomas Vikström.
            p['images']=[dict(id=i['id'],product=i['product'],width=i['width'],height=i['height'],url='/api/meteor/image/'+str(i['id'])) for i in c.execute('SELECT * FROM meteor_images WHERE pass_id=? AND id IN (SELECT MAX(id) FROM meteor_images WHERE pass_id=? GROUP BY product) ORDER BY rank,id',(row['pass_id'],row['pass_id']))]
            p['retained_image_count']=p.get('image_count',len(p['images']))
            p['image_count']=len(p['images'])
            passes.append(p)
        return passes
    finally:
        c.close()

def image_file(image_id,root=ROOT,db=DB):
    if not re.fullmatch(r'[1-9]\d{0,9}',image_id):
        raise ValueError('Invalid image ID')
    c=sqlite3.connect(Path(db).resolve().as_uri()+'?mode=ro',uri=True,timeout=5)
    try:
        row=c.execute('SELECT path FROM meteor_images WHERE id=?',(int(image_id),)).fetchone()
    finally:
        c.close()
    if not row:
        raise ValueError('Unknown image')
    path=Path(row[0]); resolved=path.resolve(strict=True)
    if path.is_symlink() or (Path(root)/'data').resolve() not in resolved.parents or resolved.suffix != '.png' or resolved.stat().st_size>64*1024*1024:
        raise ValueError('Image outside permitted products')
    png_info(resolved)
    return resolved
