"""Cumulative human-label validation. Saved evidence only; no inference or decisions."""
import json
import hashlib
import statistics
from pathlib import Path
from datetime import datetime, timezone

LABELS = ('confirmed_voice','probable_voice','no_voice','carrier_or_squelch','interference','unclear')
VOICE = LABELS[:2]
NONVOICE = LABELS[2:5]

def read(path):
    return json.loads(path.read_text())

def persistence(windows, threshold):
    count = run = longest = 0
    intervals = []
    previous = None
    for w in sorted(windows, key=lambda w:w['start_seconds']):
        start = w['start_seconds']; end = w.get('end_seconds',start+1)
        above = w.get('anomaly_score',w.get('score')) > threshold
        if above:
            count += 1
            run = run+1 if previous is not None and abs(start-previous-0.5)<1e-6 else 1
            longest = max(longest,run)
            if intervals and start <= intervals[-1][1]: intervals[-1][1] = max(end,intervals[-1][1])
            else: intervals.append([start,end])
            previous = start
        else: run=0; previous=None
    return dict(anomalous_windows=count,longest_run_windows=longest,
                anomalous_union_seconds=sum(b-a for a,b in intervals),
                longest_run_span_seconds=1+0.5*(longest-1) if longest else 0,
                anomalous_fraction=count/len(windows) if windows else 0)

def rules(row):
    peak=row['peak_score']; t=row['threshold']; p=row.get('persistence')
    n=p['anomalous_windows'] if p else None; run=p['longest_run_windows'] if p else None
    acoustic=row.get('available_acoustic_features',{})
    return {'current_screen':peak>t,'peak_gt_55':peak>55,
            'run_ge_2':run>=2 if p else None,'count_ge_4':n>=4 if p else None,
            'union_ge_2s':p['anomalous_union_seconds']>=2 if p else None,
            'peak55_and_run2':peak>55 and run>=2 if p else None,
            'peak55_or_run2':peak>55 or run>=2 if p else None,
            'screen_and_count4':peak>t and n>=4 if p else None,
            'peak55_or_count4':peak>55 or n>=4 if p else None,
            'median_gt_screen':row.get('median_score',0)>t,
            'rms_median_gt_0_0004':acoustic['rms']>0.0004 if 'rms' in acoustic else None,
            'flatness_median_lt_0_9':acoustic['spectral_flatness']<0.9 if 'spectral_flatness' in acoustic else None}

def snapshot(root, persist=True):
    # Serialize report publication; read labels after obtaining the lock.
    import fcntl
    base=Path(root)/'evaluation/tower-anomaly/cumulative-validation'
    base.mkdir(parents=True,exist_ok=True)
    with (base/'.report.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX)
        return _snapshot(root,persist)

def _snapshot(root, persist=True):
    root=Path(root); base=root/'evaluation/tower-anomaly'
    reviews=[read(p) for p in sorted((base/'human-review').glob('*.json')) if not p.is_symlink()]
    shadows={p.stem:read(p) for p in sorted((base/'shadow').glob('*.json')) if not p.is_symlink()}
    old={r['capture_id']:r for r in read(base/'reviewed-validation-20261007/window-evidence.json')} if (base/'reviewed-validation-20261007/window-evidence.json').exists() else {}
    original={}
    import csv
    feature_path=base/'reviewed-validation-20261007/recording-features.csv'
    saved_features={}
    if feature_path.exists():
        with feature_path.open() as f: saved_features={r['capture_id']:r for r in csv.DictReader(f)}
    source=base/'window-scores.jsonl'
    if source.exists():
        for line in source.read_text().splitlines():
            w=json.loads(line); original.setdefault(w['id'],[]).append(w)
    def enrich(row):
        row=dict(row); cid=row['capture_id']; shadow=shadows.get(cid,{})
        windows=shadow.get('windows') or old.get(cid,{}).get('windows') or original.get(cid)
        expected=shadow.get('summary',{}).get('count')
        complete=bool(windows) and (expected is None or len(windows)==expected)
        if complete:
            peak=max(w.get('anomaly_score',w.get('score')) for w in windows)
            complete=abs(peak-row['peak_score'])<1e-6
        row['persistence']=persistence(windows,row['threshold']) if complete else None
        row['window_evidence_status']='complete' if complete else 'missing_or_inconsistent'
        row['input_sha256']=shadow.get('input_sha256',old.get(cid,{}).get('input_sha256'))
        acoustic=original.get(cid,[])
        row['available_acoustic_features']={k:statistics.median(w[k] for w in acoustic if k in w) for k in ('rms','spectral_flatness') if any(k in w for w in acoustic)}
        saved=saved_features.get(cid)
        if saved and abs(float(saved['peak'])-row['peak_score'])<1e-6:
            for name,column in [('rms','rms_median'),('spectral_flatness','flatness_median')]:
                row['available_acoustic_features'].setdefault(name,float(saved[column]))
        row['shadow_rules']=rules(row)
        return row
    rows=[enrich(r) for r in reviews if r.get('peak_score') is not None]
    unscored=[r for r in reviews if r.get('peak_score') is None]
    counts={label:sum(r['human_review_label']==label for r in rows+unscored) for label in LABELS}
    binary=[r for r in rows if r['human_review_label'] in VOICE+NONVOICE]
    metrics={}
    for name in rules(dict(peak_score=0,threshold=0,median_score=0)):
        evaluated=[r for r in binary if r['shadow_rules'][name] is not None]
        voice=[r for r in evaluated if r['human_review_label'] in VOICE]
        nv=[r for r in evaluated if r['human_review_label'] in NONVOICE]
        misses=[r['capture_id'] for r in voice if not r['shadow_rules'][name]]
        tp=len(voice)-len(misses); fp=sum(r['shadow_rules'][name] for r in nv)
        metrics[name]=dict(tp=tp,fn=len(misses),fp=fp,tn=len(nv)-fp,
            recall=tp/len(voice) if voice else None,precision=tp/(tp+fp) if tp+fp else None,
            non_voice_fpr=fp/len(nv) if nv else None,false_negatives=misses,
            unknown_ids=[r['capture_id'] for r in binary if r['shadow_rules'][name] is None])
    groups={}
    for group,labels in [('voice',VOICE),('non_voice',NONVOICE)]:
        pp=[r['persistence'] for r in rows if r['human_review_label'] in labels and r['persistence']]
        groups[group]={k:dict(min=min(p[k] for p in pp),median=statistics.median(p[k] for p in pp),max=max(p[k] for p in pp),n=len(pp)) for k in pp[0]} if pp else {}
    queue=[]
    reviewed={r['capture_id'] for r in rows}
    for cid,s in shadows.items():
        if cid in reviewed or not (root/'recordings/tower'/cid/'raw.wav').is_file(): continue
        r=enrich(dict(capture_id=cid,peak_score=s['summary']['p100'],median_score=s['summary'].get('p50',0),threshold=s['threshold']))
        p=r['persistence']; reasons=[]; priority=0
        if abs(r['peak_score']-55)<=10: reasons.append('borderline score near 55'); priority+=4
        if abs(r['peak_score']-r['threshold'])<=5: reasons.append('screening-boundary audit'); priority+=3
        if p and (r['peak_score']>55)!=(p['longest_run_windows']>=2): reasons.append('score/persistence disagreement'); priority+=6
        if p and p['longest_run_windows']>=2 and r['peak_score']<=55: reasons.append('possible low-score voice'); priority+=5
        if p and r['peak_score']>r['threshold'] and p['longest_run_windows']<=1: reasons.append('isolated anomaly: inspect carrier/squelch/noise'); priority+=2
        if p and (p['anomalous_fraction']>0.8 or p['anomalous_windows']>=4 and p['longest_run_windows']<=2): reasons.append('unusual sustained or fragmented pattern'); priority+=4
        if not reasons: reasons=['below-threshold control' if r['peak_score']<=r['threshold'] else 'additional high-score control']
        queue.append(dict(r,priority=priority,reasons=reasons,audio_url='/api/tower/audio?recording='+cid))
    # Include controls alongside informative strata; never remove ordinary history.
    queue.sort(key=lambda r:(-r['priority'],r['capture_id']))
    selected=queue[:24]+[r for r in queue if r['priority']==0][:6]
    confirmed=[r for r in rows if r['human_review_label']=='confirmed_voice']
    lowest=min(confirmed,key=lambda r:r['peak_score']) if confirmed else None
    triggers=[]
    if len(rows)>=50: triggers.append('50 reviewed recordings reached: formal analysis due')
    for row in rows:
        if row.get('future_asr_benchmark'): triggers.append('Human-confirmed clearer transmission protected; future ASR benchmark: '+row['capture_id'])
    for name,m in metrics.items():
        weak=[cid for cid in m['false_negatives'] if any(r['capture_id']==cid and r['human_review_label']=='confirmed_voice' and r['peak_score']<=75 for r in rows)]
        if weak: triggers.append(name+' misses confirmed weak voice: '+', '.join(weak))
    result=dict(generated_at=datetime.now(timezone.utc).isoformat(),shadow_only=True,total_reviewed=len(reviews),label_counts=counts,
        label_digest=hashlib.sha256(json.dumps(reviews,sort_keys=True).encode()).hexdigest(),rules=metrics,
        lowest_scoring_confirmed_voice=lowest,persistence_characteristics=groups,formal_analysis_triggers=triggers,
        reviewed_recordings=rows+unscored,review_queue=selected,available_unreviewed=len(queue),
        limitations=['Selected reviewed set, not production accuracy.','One-second overlapping windows at 0.5-second hops are correlated.','Missing complete windows produce unknown persistence decisions, never rejection.','Acoustic flatness/RMS remain exploratory; no validated carrier detector.','Clarity and permanent benchmark protection require human assessment; anomaly score alone cannot establish intelligibility.'])
    if persist:
        out=base/'cumulative-validation';out.mkdir(exist_ok=True)
        def write(path,data):
            import os,tempfile
            fd,tmp=tempfile.mkstemp(dir=path.parent,prefix='.validation-')
            with os.fdopen(fd,'w') as f:f.write(data)
            Path(tmp).replace(path)
        write(out/'current.json',json.dumps(result,indent=2)+'\n')
        lines=['# Current Tower cumulative validation','',result['generated_at'],'','Shadow/review only. Production threshold and all production behavior unchanged. Tower ASR is out of scope.','',f'Total reviewed: {len(rows)}. Labels: {counts}.','','| Rule | TP | FN | FP | TN | Recall | Precision | Non-voice FPR |','|---|---:|---:|---:|---:|---:|---:|---:|']
        for name,m in metrics.items():
            fmt=lambda v:'unknown' if v is None else f'{100*v:.1f}%'
            lines.append(f"| {name} | {m['tp']} | {m['fn']} | {m['fp']} | {m['tn']} | {fmt(m['recall'])} | {fmt(m['precision'])} | {fmt(m['non_voice_fpr'])} |")
        lines+=['', 'Lowest confirmed voice: '+(f"{lowest['capture_id']} peak {lowest['peak_score']:.6f}" if lowest else 'none'),'', '## Persistence characteristics','',json.dumps(groups,indent=2),'','## False negatives and analysis triggers','',json.dumps({n:m['false_negatives'] for n,m in metrics.items()},indent=2),'',*triggers,'','## Informative next reviews','']
        lines += [f"- {r['capture_id']}: peak {r['peak_score']:.4f}; {'; '.join(r['reasons'])}" for r in selected]
        lines+=['',*result['limitations'],'','Rule definitions: current_screen uses strict peak > saved unchanged threshold; peak_gt_55 uses strict >55. run_ge_2 requires adjacent above-screen windows with 0.5-second spacing; count_ge_4 requires four above-screen windows. union_ge_2s uses the merged anomalous window intervals, not count times one second. AND/OR combinations use these same predicates. Median-score, median RMS >0.0004 (normalized PCM), and median spectral flatness <0.9 are exploratory low-cost checks; missing acoustic evidence is unknown. No fitting or hyperparameter search.','', 'All labels are read from human-review/*.json; re-review uses the latest human label. Current JSON preserves full label snapshots, per-rule decisions, unknown evidence IDs and review priorities. No shadow rule influences retention or ASR. Stronger score is not evidence of clearer speech. No new threshold is recommended.']
        write(root/'docs/tower-cumulative-validation.md','\n'.join(lines)+'\n')
    return result

if __name__=='__main__':
    import sys
    r=snapshot(sys.argv[1]);print(json.dumps({k:r[k] for k in ('total_reviewed','label_counts','rules','formal_analysis_triggers','available_unreviewed')},indent=2))
