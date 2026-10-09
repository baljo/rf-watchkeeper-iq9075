"""Isolated CPU-only Tower MFCC/GMM baseline. Never calls VAD, ASR or retention.

Requires only numpy. Scores are negative log likelihood: larger is less typical.
Audio is read-only; generated artifacts belong in a separate evaluation directory.
"""
import argparse
import hashlib
import json
from pathlib import Path
import wave
import numpy as np

BENCHMARK = '20261007T132451.116831Z'
PARAMETERS = dict(sample_rate=16000, window_samples=16000, hop_samples=8000,
                  frame_samples=400, frame_hop_samples=160, fft_size=512,
                  mel_bands=40, low_hz=80, high_hz=3900, mfcc_coefficients=13,
                  components=4, variance_floor=0.05, seed=9075)


def read_json(path):
    try:
        return json.loads(Path(path).read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return {}


def save_json(path, obj):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + '.tmp')
    tmp.write_text(json.dumps(obj, indent=2, allow_nan=False) + '\n', encoding='utf-8')
    tmp.replace(path)


def read_audio(path):
    with wave.open(str(path), 'rb') as f:
        rate, channels, width = f.getframerate(), f.getnchannels(), f.getsampwidth()
        if width != 2 or rate not in (8000, 16000):
            raise ValueError('Expected PCM16 at 8 or 16 kHz; unsupported rates excluded')
        pcm = np.frombuffer(f.readframes(f.getnframes()), dtype='<i2').astype(float)
    if not len(pcm) or len(pcm) % channels:
        raise ValueError('Empty or malformed PCM')
    pcm = pcm.reshape(-1, channels).mean(axis=1) / 32768.0
    pcm -= pcm.mean()  # recording DC only; no per-recording gain normalization
    if rate == 8000:
        # Same reproducible linear upsampling choice as existing Tower prep.
        pcm = np.interp(np.arange(len(pcm) * 2) / 2, np.arange(len(pcm)), pcm)
    return pcm


def mel_filter():
    p = PARAMETERS
    hz_to_mel = lambda x: 2595 * np.log10(1 + np.asarray(x) / 700)
    edges = 700 * (10 ** (np.linspace(hz_to_mel(p['low_hz']), hz_to_mel(p['high_hz']),
                                      p['mel_bands'] + 2) / 2595) - 1)
    frequencies = np.fft.rfftfreq(p['fft_size'], 1 / p['sample_rate'])
    bank = []
    for a, b, c in zip(edges[:-2], edges[1:-1], edges[2:]):
        bank.append(np.maximum(0, np.minimum((frequencies-a)/(b-a), (c-frequencies)/(c-b))))
    return np.asarray(bank)


def features(pcm):
    """Full one-second windows only, 0.5-second hop, no fabricated tail padding."""
    p = PARAMETERS
    bank = mel_filter()
    k = np.arange(p['mfcc_coefficients'])[:, None]
    dct = np.cos(np.pi / p['mel_bands'] * k * (np.arange(p['mel_bands']) + 0.5))
    dct *= np.sqrt(2 / p['mel_bands'])
    dct[0] /= np.sqrt(2)
    values, starts, metrics = [], [], []
    for start in range(0, len(pcm)-p['window_samples']+1, p['hop_samples']):
        x = pcm[start:start+p['window_samples']]
        frame_starts = np.arange(0, len(x)-p['frame_samples']+1, p['frame_hop_samples'])
        frames = x[frame_starts[:, None]+np.arange(p['frame_samples'])] * np.hamming(p['frame_samples'])
        power = np.abs(np.fft.rfft(frames, n=p['fft_size'])) ** 2 / p['fft_size']
        mel = np.log(np.maximum(power @ bank.T, 1e-12))
        mfcc = mel @ dct.T
        values.append(np.r_[mfcc.mean(axis=0), mfcc.std(axis=0)])
        starts.append(start / p['sample_rate'])
        rms = float(np.sqrt(np.mean(x*x)))
        spectrum = power.mean(axis=0)[3:126]
        flatness = float(np.exp(np.log(np.maximum(spectrum, 1e-16)).mean()) / max(spectrum.mean(), 1e-16))
        metrics.append(dict(rms=rms, peak=float(np.abs(x).max()), spectral_flatness=flatness))
    return np.asarray(values).reshape(-1, 26), starts, metrics


def _log_density(z, means, variances, weights):
    delta = z[:, None, :] - means[None, :, :]
    return -0.5 * (np.log(2*np.pi*variances).sum(axis=1)[None, :] +
                   (delta*delta / variances[None, :, :]).sum(axis=2)) + np.log(weights)[None, :]


def _logsumexp(x):
    m = x.max(axis=1)
    return m + np.log(np.exp(x-m[:, None]).sum(axis=1))


def fit_model(x):
    if len(x) < 100 or not np.isfinite(x).all():
        raise ValueError('Need at least 100 finite background training windows')
    center, scale = x.mean(axis=0), np.maximum(x.std(axis=0), 0.1)
    z = (x-center)/scale
    rng = np.random.RandomState(PARAMETERS['seed'])
    means = z[rng.choice(len(z), PARAMETERS['components'], replace=False)].copy()
    variances = np.ones_like(means)
    weights = np.full(len(means), 1/len(means))
    previous = -np.inf
    for iteration in range(150):
        logp = _log_density(z, means, variances, weights)
        ll = _logsumexp(logp)
        responsibility = np.exp(logp-ll[:, None])
        counts = np.maximum(responsibility.sum(axis=0), 1e-9)
        weights = counts/counts.sum()
        means = responsibility.T @ z / counts[:, None]
        variances = np.maximum(responsibility.T @ (z*z)/counts[:, None]-means*means,
                               PARAMETERS['variance_floor'])
        if abs(ll.mean()-previous) < 1e-5:
            break
        previous = ll.mean()
    return dict(version=1, parameters=PARAMETERS, center=center.tolist(), scale=scale.tolist(),
                means=means.tolist(), variances=variances.tolist(), weights=weights.tolist(),
                em_iterations=iteration+1)


def score(x, model):
    if model.get('version') != 1 or model.get('parameters') != PARAMETERS:
        raise ValueError('Incompatible feature/model version')
    z = (x-np.asarray(model['center']))/np.asarray(model['scale'])
    return -_logsumexp(_log_density(z, np.asarray(model['means']), np.asarray(model['variances']),
                                    np.asarray(model['weights'])))


def distribution(values):
    v = np.asarray(values)
    if not len(v):
        return dict(count=0)
    return dict(count=int(len(v)), mean=float(v.mean()), std=float(v.std()),
                **{'p'+str(q):float(np.percentile(v, q)) for q in (50,90,95,99,99.5,99.9,100)})


def screening(folder, metrics):
    reasons = []
    segmentation, processed, transcript = [read_json(folder / name) for name in
                                           ('segmentation.json', 'processed.json', 'transcript.json')]
    if processed.get('status') != 'no_activity':
        reasons.append('metadata_not_no_activity')
    if segmentation.get('status') != 'no_activity' or segmentation.get('regions'):
        reasons.append('metadata_activity_or_unknown')
    if transcript.get('has_text') or transcript.get('text'):
        reasons.append('transcript_present')
    if not metrics:
        reasons.append('shorter_than_one_second')
    else:
        rms = np.array([m['rms'] for m in metrics])
        if rms.min() < 1e-6:
            reasons.append('digital_silence_or_dropout')
        if rms.max() / max(np.median(rms), 1e-12) > 2.5:
            reasons.append('energy_burst')
        if max(m['peak'] for m in metrics) > 0.95:
            reasons.append('clipping')
        if min(m['spectral_flatness'] for m in metrics) < 0.12:
            reasons.append('tonal_or_structured_audio')
    return reasons


def evaluate(root, output):
    root, output = Path(root), Path(output)
    if root.resolve() == output.resolve() or root.resolve() in output.resolve().parents and 'recordings' in output.parts:
        raise ValueError('Output must be outside originals')
    output.mkdir(parents=True, exist_ok=True)
    folders = sorted((root/'recordings/tower').glob('*'))
    folders += sorted((root/'asr-reference-corpus').glob('*TOWER*'))
    held_out_hashes = {hashlib.sha256((f/'raw.wav').read_bytes()).hexdigest() for f in folders
                       if BENCHMARK in f.name and (f/'raw.wav').is_file() and not (f/'raw.wav').is_symlink()}
    if not held_out_hashes:
        raise ValueError('Required held-out benchmark audio is unavailable')
    entries, cache, seen = [], {}, {}
    for folder in folders:
        if not folder.is_dir() or folder.is_symlink():
            continue
        path = folder/'raw.wav'
        entry = dict(id=folder.name, relative_path=folder.relative_to(root).as_posix(),
                     role='excluded', reasons=[])
        entries.append(entry)
        if not path.is_file() or path.is_symlink():
            entry['reasons'] = ['missing_original_audio']; continue
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        entry['sha256'] = digest
        if folder.name == BENCHMARK:
            entry.update(role='positive_held_out', reasons=['human_confirmed_weak_voice_never_background'])
        elif digest in held_out_hashes:
            entry.update(role='excluded', reasons=['benchmark_content_quarantined'])
        if digest in seen:
            if folder.name == BENCHMARK:
                entry['duplicate_of'] = seen[digest]
            else:
                entry.update(role='excluded', reasons=['duplicate_audio'], duplicate_of=seen[digest]); continue
        seen[digest] = folder.name
        try:
            pcm = read_audio(path)
            x, starts, metrics = features(pcm)
            entry.update(duration_seconds=len(pcm)/16000, windows=len(x),
                         audio_metrics=dict(median_rms=float(np.median([m['rms'] for m in metrics])) if metrics else 0,
                                            min_flatness=min((m['spectral_flatness'] for m in metrics), default=0)))
            cache[folder.name] = (x, starts, metrics)
            if entry['role'] != 'positive_held_out' and digest not in held_out_hashes:
                entry['reasons'] = screening(folder, metrics)
                if not entry['reasons']:
                    entry['role'] = 'background_candidate'
        except (ValueError, wave.Error, OSError, EOFError) as error:
            entry.update(role='excluded', reasons=['invalid_audio:'+type(error).__name__])
    candidates = [e for e in entries if e['role']=='background_candidate']
    if len(candidates) < 10:
        raise ValueError('Insufficient screened recordings')
    # Independent robust recording-level outlier screen, without benchmark input.
    vectors = np.array([np.median(cache[e['id']][0],axis=0) for e in candidates])
    med = np.median(vectors, axis=0)
    mad = np.maximum(1.4826*np.median(np.abs(vectors-med), axis=0), 0.1)
    for entry, v in zip(candidates, vectors):
        if np.max(np.abs((v-med)/mad)) > 8:
            entry.update(role='excluded', reasons=['robust_spectral_outlier'])
        else:
            bucket = int(entry['sha256'][:8],16) % 10
            entry['role'] = 'background_train' if bucket<6 else ('background_calibration' if bucket<8 else 'background_test')
    parts = {role:np.concatenate([cache[e['id']][0] for e in entries if e['role']==role])
             for role in ('background_train','background_calibration','background_test')}
    model = fit_model(parts['background_train'])
    calibration = score(parts['background_calibration'], model)
    model['shadow_threshold'] = float(np.percentile(calibration,99.5))
    model['training_hashes'] = sorted(e['sha256'] for e in entries if e['role']=='background_train')
    assert not held_out_hashes.intersection(model['training_hashes'])
    save_json(output/'model.json', model)
    threshold = model['shadow_threshold']
    rows, summaries = [], []
    for entry in entries:
        if entry['id'] not in cache or entry['reasons']==['duplicate_audio']:
            continue
        x, starts, metrics = cache[entry['id']]
        if not len(x): continue
        values = score(x, model)
        for start, value, metric in zip(starts, values, metrics):
            rows.append(dict(id=entry['id'], role=entry['role'], start_seconds=start,
                             end_seconds=start+1, anomaly_score=float(value),
                             shadow_exceeds_threshold=bool(value>threshold), **metric))
        summaries.append(dict(id=entry['id'], role=entry['role'], scores=distribution(values),
                              above_threshold_windows=int((values>threshold).sum()),
                              above_threshold_fraction=float((values>threshold).mean()),
                              top_windows=[dict(start_seconds=starts[i],end_seconds=starts[i]+1,score=float(values[i]))
                                           for i in np.argsort(values)[-10:][::-1]]))
    with (output/'window-scores.jsonl').open('w',encoding='utf-8') as f:
        for row in rows: f.write(json.dumps(row,allow_nan=False)+'\n')
    report = dict(parameters=PARAMETERS, score_definition='negative_log_likelihood_of_standardized_26d_MFCC_summary',
                  dataset={role:sum(e['role']==role for e in entries) for role in sorted({e['role'] for e in entries})},
                  distributions={role:distribution(score(x,model)) for role,x in parts.items()},
                  shadow_threshold=threshold, threshold_source='background_calibration_p99.5_only',
                  summaries=summaries, benchmark=next(s for s in summaries if s['id']==BENCHMARK),
                  limitations=['Candidates are machine-screened, not human-certified normal',
                               'Weak voice time boundaries have no human annotation',
                               'Local MFCC aggregation and score scale are not bit-identical to Edge Impulse',
                               'Single positive capture cannot establish general speech sensitivity'])
    save_json(output/'dataset-manifest.json',dict(benchmark_id=BENCHMARK,benchmark_hashes=sorted(held_out_hashes),
                                                entries=entries,parameters=PARAMETERS))
    save_json(output/'report.json',report)
    return report


def score_file(path, model):
    x, starts, _ = features(read_audio(path))
    values = score(x,model)
    return dict(mode='shadow_only', affects_retention=False, affects_transcription=False,
                model_version=model['version'], input_sha256=hashlib.sha256(Path(path).read_bytes()).hexdigest(),
                summary=distribution(values), threshold=model['shadow_threshold'],
                windows=[dict(start_seconds=s,end_seconds=s+1,anomaly_score=float(v),
                              shadow_exceeds_threshold=bool(v>model['shadow_threshold'])) for s,v in zip(starts,values)])


if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root',required=True)
    parser.add_argument('--output',required=True)
    args=parser.parse_args()
    report=evaluate(args.root,args.output)
    print(json.dumps({k:report[k] for k in ('dataset','distributions','shadow_threshold','benchmark')},indent=2))
