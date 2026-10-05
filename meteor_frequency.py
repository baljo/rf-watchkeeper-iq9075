"""Bounded broad-band IQ survey; a negative spectrum is never deletion evidence."""
from pathlib import Path

def decoder_identity(c):
    """Bind retention evidence to the supported wrapper and immutable image identity."""
    import hashlib
    paths = [Path(p) for p in c.get('satdump_command', []) if Path(p).is_file() and p.endswith('.py')]
    wrapper = next(iter(paths), None)
    runtime = wrapper.parent / 'data/meteor-native-runtime.json' if wrapper else None
    return {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths + ([runtime] if runtime and runtime.is_file() else [])}

def procedure_config(c):
    return dict(pipeline=c.get('satdump_pipeline', 'meteor_m2-x_lrpt'), extra=c.get('satdump_extra', []),
                frequency_evaluation=dict(dict(span_hz=60000, windows=24, max_candidates=2, budget_seconds=300), **c.get('frequency_evaluation', {})))

def trial_clean(a):
    """Nonblocking unused SDR-plugin/TLE-network notices do not invalidate file decoding.

    All unknown error lines, invalid arguments, missing stage markers, crashes and
    timeouts still block retention. The strict original evaluation_clean is preserved.
    """
    import re
    m = a.get('metrics', {})
    if a.get('returncode') != 0 or a.get('error') or m.get('error') or not a.get('finished_at'):
        return False
    if m.get('evaluation_clean') is True:
        return True
    logpath = Path(a.get('output', '')) / 'satdump.log'
    if not logpath.is_file():
        return False
    log = re.sub(r'\x1b\[[0-9;]*m', '', logpath.read_text(errors='replace'))
    if 'Demodulation finished' not in log or 'Done! Goodbye' not in log:
        return False
    if re.search(r'(invalid|unknown|not found|does not exist).*pipeline|unrecognized (argument|option)|EVK SatDump:|time limit reached', log, re.I):
        return False
    errors = [line for line in log.splitlines() if re.search(r'\[error\]|\[critical\]|\(E\)|\(C\)|\bfatal\b|Segmentation fault', line, re.I)]
    def nonblocking(line):
        return bool(re.search(r'Error loading /usr/lib/satdump/plugins/lib(?:bladerf|limesdr|plutosdr|usrp)_sdr_support\.so! Error : lib[^ ]+: cannot open shared object file:', line)
                    or 'curl_easy_perform() failed: Could not resolve host: celestrak.org' in line
                    or 'Error updating TLEs. Not updated.' in line)
    return all(nonblocking(line) for line in errors)

def procedure_complete(r, c):
    """Validate every configured shifted trial, without claiming exhaustive coverage."""
    e = r.get('frequency_evaluation', {})
    if e.get('error') or e.get('input_fingerprint') != r.get('iq_fingerprint') or not e.get('finished_at'):
        return False
    if e.get('decoder_identity') != decoder_identity(c) or e.get('configuration') != procedure_config(c):
        return False
    if not e.get('procedure_completed'):
        return False
    survey = e.get('survey', {})
    configured = procedure_config(c)['frequency_evaluation']
    if survey.get('method') != 'sampled_broadband_spectrum_v1' or survey.get('span_hz') != configured['span_hz'] or survey.get('windows') != configured['windows'] or len(survey.get('candidate_carrier_offsets_hz', [])) != configured['max_candidates']:
        return False
    wanted = {0} | {-x for x in e.get('survey', {}).get('candidate_carrier_offsets_hz', [])}
    trials = e.get('trials', [])
    attempts = {a.get('output'): a for a in r.get('decode_attempts', [])}
    if not trials or {t.get('shift_hz') for t in trials} != wanted:
        return False
    return all(t.get('output') in attempts and trial_clean(attempts[t['output']]) and
               attempts[t['output']].get('frequency_shift_hz', 0) == t.get('shift_hz') for t in trials)

def survey(iq, rate, span_hz=60000, windows=24, max_candidates=2):
    import numpy as np
    if not 0 < span_hz <= min(60000, rate / 2 - 54000):
        raise ValueError('Frequency span would put the 108 kHz LRPT band outside captured IQ')
    path = Path(iq)
    count = path.stat().st_size // 2
    n = 16384
    if count < n or path.stat().st_size % 2:
        raise ValueError('IQ too short or invalid for spectrum survey')
    frequencies = np.fft.fftshift(np.fft.fftfreq(n, 1 / rate))
    centers = np.arange(-span_hz, span_hz + 1, 2500, dtype=float)
    evidence = []
    with path.open('rb') as stream:
        for start in np.linspace(0, count - n, windows).astype(int):
            stream.seek(int(start) * 2)
            raw = np.frombuffer(stream.read(n * 2), dtype=np.uint8).astype(np.float32).reshape(-1, 2)
            z = (raw[:, 0] - 127.5) + 1j * (raw[:, 1] - 127.5)
            z -= z.mean()
            power = abs(np.fft.fftshift(np.fft.fft(z * np.hanning(n)))) ** 2
            # Suppress narrow interferers; fit power over the expected wide LRPT band.
            power = np.minimum(power, np.quantile(power, .97))
            scores = [float(power[abs(frequencies - center) <= 48000].sum()) for center in centers]
            evidence.append(dict(sample_start=int(start), center_hz=int(centers[int(np.argmax(scores))]), scores=scores))
    ranked = np.argsort(np.asarray([w['scores'] for w in evidence]).mean(axis=0))[::-1]
    offsets = []
    for index in ranked:
        center = int(centers[index])
        if abs(center) < 7500 or any(abs(center - v) < 15000 for v in offsets):
            continue
        offsets.append(center)
        if len(offsets) >= max_candidates:
            break
    return dict(method='sampled_broadband_spectrum_v1', span_hz=span_hz,
                windows=windows, fft_samples=n, candidate_carrier_offsets_hz=offsets,
                windows_evidence=[{k:v for k,v in w.items() if k != 'scores'} for w in evidence],
                negative_result_verified=False,
                limitation='Sparse spectrum survey ranks candidates; interference/weak signals may be missed. Zero images remain unverified.')

def useful(metrics, minimum=128):
    import re
    return any(re.fullmatch(r'MSU-MR-[1-6]', im.get('product', '')) and im['width'] >= 256 and im['height'] >= minimum
               and metrics.get('channel_lines', {}).get(im['product'][-1], 0) >= minimum
               for im in metrics.get('images', []))

def rank(attempt):
    m = attempt.get('metrics', {})
    return (useful(m), attempt.get('returncode') == 0 and not attempt.get('error'),
            max(m.get('channel_lines', {}).values(), default=0), len(m.get('images', [])), m.get('peak_snr') or 0)
