# Analyze retained FID31 packet, observation and value-change cadence; 2026-10-05 19:46 EEST, Thomas Vikström.
import json, collections, statistics, datetime, calendar, hashlib
from pathlib import Path
UTC=datetime.timezone.utc
src=Path('work/ais-type8-raw.jsonl')
rows=[json.loads(x) for x in src.read_text(encoding='utf-8-sig').splitlines()]
rows=[x for x in rows if x.get('type')==8 and x.get('dac')==1 and x.get('fid')==31]
def observation(r):
    rx=datetime.datetime.fromtimestamp(r['rxuxtime'],UTC)
    candidates=[]
    for offset in [-1,0,1]:
        m=rx.year*12+rx.month-1+offset; y,mo=divmod(m,12)
        try: candidates.append(datetime.datetime(y,mo+1,r['day'],r['hour'],r['minute'],tzinfo=UTC))
        except ValueError: pass
    return min(candidates,key=lambda x:abs((rx-x).total_seconds())).timestamp() if candidates else None
def stats(a):
    a=sorted(a)
    if not a:return None
    def q(p):
        k=(len(a)-1)*p;i=int(k);return a[i]+(a[min(i+1,len(a)-1)]-a[i])*(k-i)
    return dict(n=len(a),median=statistics.median(a),p10=q(.1),p90=q(.9),min=min(a),max=max(a),modes=collections.Counter(round(x,2) for x in a).most_common(8))
def deltas(a):return [b-a for a,b in zip(a,a[1:])]
groups=collections.defaultdict(list)
for r in rows:groups[(r['mmsi'],r['lat'],r['lon'])].append(r)
out=dict(source=str(src),sha256=hashlib.sha256(src.read_bytes()).hexdigest(),packets=len(rows),stations=[])
fields=['wspeed','wgust','wdir','airtemp','humidity','pressure','waterlevel','visibility','watertemp','water_temp']
for key,rr in sorted(groups.items()):
    rr.sort(key=lambda r:r['rxuxtime']); obs=collections.defaultdict(list)
    for r in rr:
        t=observation(r)
        if t is not None:obs[t].append(r)
    tt=sorted(obs); conflicts=[]; variables=[]
    for f in fields:
        values=[]
        for t in tt:
            vv={round(r[f],4) for r in obs[t] if f in r}
            if len(vv)>1:conflicts.append(dict(time=t,field=f,values=sorted(vv)))
            if len(vv)==1:values.append((t,next(iter(vv))))
        changes=[values[i][0] for i in range(1,len(values)) if values[i][1]!=values[i-1][1]]
        variables.append(dict(field=f,samples=len(values),distinct_values=len(set(v for t,v in values)),changes=len(changes),change_interval=stats(deltas(changes)),sample_interval=stats(deltas([t for t,v in values])),transition_intervals=stats([values[i][0]-values[i-1][0] for i in range(1,len(values)) if values[i][1]!=values[i-1][1]])))
    out['stations'].append(dict(mmsi=key[0],lat=key[1],lon=key[2],packets=len(rr),start=rr[0]['rxtime'],end=rr[-1]['rxtime'],packet_interval=stats(deltas([r['rxuxtime'] for r in rr])),short_packet_interval=stats([x for x in deltas([r['rxuxtime'] for r in rr]) if x<=300]),unique_observations=len(tt),observation_interval=stats(deltas(tt)),repeated_packets=sum(len(v)-1 for v in obs.values()),repeat_multiplicity=collections.Counter(len(v) for v in obs.values()),latency=stats([r['rxuxtime']-observation(r) for r in rr]),conflicts=conflicts,variables=variables))
Path('outputs/hydro-cadence-results.json').write_text(json.dumps(out,ensure_ascii=False,indent=2),encoding='utf-8')
for s in out['stations']:
    print('\nSTATION',s['lat'],s['lon'],'packets',s['packets'],'unique',s['unique_observations'],'repeats',s['repeated_packets'],'conflicts',len(s['conflicts']))
    for k in ['packet_interval','short_packet_interval','observation_interval','latency']:print(k,s[k])
    for v in s['variables']:
        if v['samples']:print(v)
