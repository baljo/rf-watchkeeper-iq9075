# Independently check FID31 payload timestamps and unavailable fields against IMO bit widths; 2026-10-05 19:50 EEST, Thomas Vikström.
import json,collections
from pathlib import Path
r=[json.loads(x) for x in Path('work/ais-type8-raw.jsonl').read_text(encoding='utf-8-sig').splitlines()]
r=[x for x in r if x.get('dac')==1 and x.get('fid')==31]
layout=[('type',6),('repeat',2),('mmsi',30),('spare',2),('iai',16),('lon',25),('lat',24),('accuracy',1),('day',5),('hour',5),('minute',6),('wspeed',7),('wgust',7),('wdir',9),('gust_dir',9),('airtemp',11),('humidity',7),('dewpoint',10),('pressure',9),('pressure_trend',2),('visibility',8),('waterlevel',12),('waterlevel_trend',2),('current_speed',8),('current_dir',9),('current2_speed',8),('current2_dir',9),('current2_depth',5),('current3_speed',8),('current3_dir',9),('current3_depth',5),('waveheight',8),('waveperiod',6),('wavedir',9),('swellheight',8),('swellperiod',6),('swelldir',9),('seastate',4),('watertemp',10),('precipitation',3),('salinity',9),('ice',2),('spare2',10)]
hist=collections.defaultdict(collections.Counter); mismatch=0
for x in r:
    payload=''.join(n.split(',')[5] for n in x['nmea'])
    bits=''
    for ch in payload:
        v=ord(ch)-48
        if v>40:v-=8
        bits+=format(v,'06b')
    offset=0;d={}
    for name,width in layout:
        d[name]=int(bits[offset:offset+width],2);offset+=width
    mismatch+=any(d[k]!=x[k] for k in ['type','repeat','mmsi','day','hour','minute','wspeed','wgust','wdir','humidity'] if k in x)
    for k in ['gust_dir','dewpoint','pressure_trend','waterlevel_trend','current_speed','current_dir','current2_speed','current3_speed','waveheight','waveperiod','wavedir','swellheight','seastate','watertemp','precipitation','salinity','ice']:hist[k].update([d[k]])
out={'checked_packets':len(r),'decoded_field_mismatches':mismatch,'payload_field_histograms':dict(hist)}
Path('outputs/hydro-payload-audit.json').write_text(json.dumps(out,indent=2),encoding='utf-8')
print(json.dumps(out,indent=2))

