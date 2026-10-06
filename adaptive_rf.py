"""Deterministic RF selection and streaming AM energy hold; no ASR dependency."""
import array
import math


def choose(jobs, now, last, available):
    """ATIS > Tower > bounded AIS. Cadence is measured between starts."""
    periodic = [j for j in jobs if j.get('atis_recording') or j.get('tower_recording')]
    for flag in ('atis_recording', 'tower_recording'):
        for job in periodic:
            if job.get(flag) and available(job) and now >= last(job) + job['interval_seconds']:
                return dict(job)
    filler = next((j for j in jobs if j['mode'] == 'ais'), None)
    if filler is None:
        return None
    seconds = min(45, filler['dwell_seconds'])
    for job in periodic:
        if available(job):
            seconds = min(seconds, max(0, last(job) + job['interval_seconds'] - now))
    return dict(filler, dwell_seconds=max(.1, seconds))


class TowerHold:
    """Conservative DC-free PCM energy gate, shared with downstream energy scale.

    Activity must persist for 240 ms; short clicks do not extend the probe.
    Continuous energy is conservatively retained to the hard limit. This is
    transmission-candidate detection, not a claim of intelligible speech.
    """
    def __init__(self, rate, job):
        self.frame = rate // 50
        self.rate = rate
        self.threshold = job.get('activity_rms', 40)
        self.probe = job['dwell_seconds']
        self.quiet = job.get('quiet_seconds', 10)
        self.maximum = job.get('max_listen_seconds', 75)
        self.pending = array.array('h')
        self.samples = 0
        self.run = 0
        self.last_activity = None
        self.triggered = False
        self.peak_rms = 0

    def feed(self, block):
        values = array.array('h'); values.frombytes(block)
        self.pending.extend(values)
        while len(self.pending) >= self.frame:
            values = self.pending[:self.frame]; del self.pending[:self.frame]
            mean = sum(values) / len(values)
            rms = math.sqrt(sum((v-mean)**2 for v in values) / len(values))
            self.peak_rms = max(self.peak_rms, rms)
            self.samples += self.frame
            self.run = self.run + 1 if rms >= self.threshold else 0
            if self.run >= 12:
                self.triggered = True
                self.last_activity = self.samples / self.rate

    def duration(self):
        return min(self.maximum, max(self.probe, (self.last_activity or 0) + self.quiet))

    def report(self):
        return dict(method='dc-free-pcm-energy-v1', threshold_rms=self.threshold,
                    confirmation_ms=240, triggered=self.triggered,
                    last_activity_seconds=self.last_activity, peak_rms=round(self.peak_rms, 3),
                    quiet_seconds=self.quiet, max_listen_seconds=self.maximum)
