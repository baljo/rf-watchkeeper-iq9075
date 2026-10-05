"""Conservative PCM activity segmentation and auditable aviation spelling.

Energy is a speech candidate gate, not a classifier of speech versus RF noise.
Continuous/noisy audio is retained for ASR; numbers are never inferred.
"""
import math
import re


def activity_regions(samples, rate):
    frame = rate // 50  # 20 ms
    energies = []
    for start in range(0, len(samples), frame):
        values = samples[start:start + frame]
        mean = sum(values) / len(values)
        energies.append(math.sqrt(sum((v - mean) ** 2 for v in values) / len(values)))
    if not energies:
        return [], {'status': 'no_activity', 'method': 'energy-candidate-v1'}
    floor = sorted(energies)[int((len(energies) - 1) * .2)]
    threshold = max(40.0, floor * 2.5)
    active = [e >= threshold for e in energies]
    uncertain = max(energies) >= 40 and not any(active)
    if uncertain:
        active = [e >= 40 for e in energies]
    groups = []
    start = last = None
    count = 0
    for i, yes in enumerate(active + [False] * 61):
        if yes:
            if start is None:
                start, count = i, 0
            last = i
            count += 1
        elif start is not None and i - last > 60:
            if count >= 12:  # reject isolated clicks shorter than 240 ms
                groups.append((max(0, (start - 10) * frame),
                               min(len(samples), (last + 11) * frame)))
            start = last = None
    merged = []
    for start, end in groups:
        if merged and start <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(end, merged[-1][1]))
        else:
            merged.append((start, end))
    # Bounded, non-overlapping chunks; pad short inputs at the decoder boundary.
    regions = [(s, min(s + 28 * rate, end)) for start, end in merged
               for s in range(start, end, 28 * rate)]
    return regions, {'status': 'continuous_or_noise' if uncertain else
                     ('activity_detected' if regions else 'no_activity'),
                     'method': 'energy-candidate-v1', 'frame_ms': 20,
                     'pause_ms': 1200, 'padding_ms': 200,
                     'noise_floor_rms': round(floor, 3),
                     'threshold_rms': round(threshold, 3),
                     'regions': [{'start_seconds': s / rate, 'end_seconds': e / rate}
                                 for s, e in regions],
                     'note': 'Energy candidates may include RF noise; absence is not an RF health failure.'}


def normalize(text):
    """Spelling only. Preserve uncertain numbers, callsigns and station names."""
    changes = []
    value = text
    for pattern, replacement in [(r'\bQ\s+N\s+H\b', 'QNH'),
                                  (r'\bI\s+L\s+S\b', 'ILS'),
                                  (r'\bA\s+T\s+I\s+S\b', 'ATIS'),
                                  (r'\bniner\b', 'nine'),
                                  (r'\bfife\b', 'five')]:
        def replace(match):
            changes.append({'source': match.group(), 'replacement': replacement})
            return replacement
        value = re.sub(pattern, replace, value, flags=re.I)
    return {'text': value, 'changes': changes, 'status': 'spelling_only',
            'numeric_values_verified': False}
