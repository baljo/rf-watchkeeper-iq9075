# Prepare a short FM speech clip as filtered 16 kHz mono PCM for ASR, preserving the original. 2026-09-17 19:00 EEST — Thomas Vikström.
import argparse
from array import array
import math
from pathlib import Path
import sys
import wave


def downsample(samples):
    # 97-tap Blackman-windowed low-pass FIR: remove high frequencies before decimation.
    half = 48
    cutoff = 6500 / 48000
    weights = []
    for i in range(97):
        x = i - half
        sinc = 2 * cutoff if x == 0 else math.sin(2 * math.pi * cutoff * x) / (math.pi * x)
        weights.append(sinc * (0.42 - 0.5 * math.cos(2 * math.pi * i / 96) + 0.08 * math.cos(4 * math.pi * i / 96)))
    total = sum(weights)
    weights = [v / total for v in weights]
    padded = [0] * half + list(samples) + [0] * half
    return array('h', (max(-32768, min(32767, round(sum(padded[i+j] * w for j, w in enumerate(weights)))))
                       for i in range(0, len(samples), 3)))


def prepare(source, destination, start=0, seconds=20):
    if not math.isfinite(start) or start < 0 or not math.isfinite(seconds) or not 0 < seconds <= 30:
        raise ValueError('Start must be nonnegative; duration must be 0–30 seconds')
    with wave.open(str(source), 'rb') as wav:
        rate = wav.getframerate()
        if (wav.getnchannels(), wav.getsampwidth(), wav.getcomptype()) != (1, 2, 'NONE') or rate not in (16000, 48000):
            raise ValueError('Expected mono PCM16 WAV at 16 or 48 kHz')
        offset = int(start * rate)
        if offset >= wav.getnframes():
            raise ValueError('Start is beyond end of recording')
        wav.setpos(offset)
        count = min(int(seconds * rate), wav.getnframes() - offset)
        data = wav.readframes(count)
        if len(data) != count * 2:
            raise ValueError('Truncated WAV')
    samples = array('h')
    samples.frombytes(data)
    if sys.byteorder != 'little':
        samples.byteswap()
    if rate == 48000:
        samples = downsample(samples)
    if not samples:
        raise ValueError('Empty clip')
    if sys.byteorder != 'little':
        samples.byteswap()
    with destination.open('xb') as stream:
        with wave.open(stream, 'wb') as wav:
            wav.setparams((1, 2, 16000, 0, 'NONE', 'not compressed'))
            wav.writeframes(samples.tobytes())
    print('ASR clip: {} ({:.2f} seconds)'.format(destination, len(samples) / 16000))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Prepare a speech segment without overwriting recordings')
    parser.add_argument('source', type=Path)
    parser.add_argument('destination', type=Path)
    parser.add_argument('--start', type=float, default=0)
    parser.add_argument('--seconds', type=float, default=20)
    args = parser.parse_args()
    try:
        prepare(args.source, args.destination, args.start, args.seconds)
    except (OSError, ValueError, wave.Error) as error:
        parser.exit(1, str(error) + '\n')
