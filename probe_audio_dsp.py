# Inventory Linux audio/DSP interfaces without changing routing, mixer controls or firmware; save evidence locally. 2026-09-17 19:54 EEST — Thomas Vikström.
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import platform
import re
import shutil
import subprocess
import uuid

ROOT = Path(__file__).resolve().parent
PATTERN = re.compile(r'lpass|adsp|cdsp|audioreach|audio.?reach|fastrpc|hexagon|q6|qap|agm|ar-pal|libpal|snd|alsa|audio|pipewire|pulse', re.I)


def read(path, limit=16000):
    try:
        with Path(path).open('rb') as stream:
            data = stream.read(limit + 1)
        return {'text': data[:limit].decode('utf-8', errors='replace'), 'truncated': len(data) > limit}
    except OSError as error:
        return {'error': str(error)}


def command(argv, timeout=8):
    binary = shutil.which(argv[0])
    if not binary:
        return {'available': False}
    # Commands below only enumerate state; stdout is bounded before saving.
    try:
        result = subprocess.run([binary] + argv[1:], stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                timeout=timeout, env=dict(os.environ, LC_ALL='C'))
        text = result.stdout.decode('utf-8', errors='replace')
        if argv[0] == 'rpm':
            text = '\n'.join(line for line in text.splitlines() if PATTERN.search(line))
        return {'available': True, 'exit_code': result.returncode, 'text': text[:48000], 'truncated': len(text) > 48000}
    except (OSError, subprocess.TimeoutExpired) as error:
        return {'available': True, 'error': str(error)}


def scan(roots, max_entries=30000, max_matches=250):
    matches, errors, visited = [], [], 0
    capped = False
    for root in roots:
        if not Path(root).exists():
            continue
        def onerror(error):
            if len(errors) < 10:
                errors.append(str(error))
        for current, directories, files in os.walk(root, followlinks=False, onerror=onerror):
            depth = len(Path(current).relative_to(root).parts)
            if depth >= 4:
                directories[:] = []
            for name in sorted(directories + files):
                visited += 1
                if PATTERN.search(name):
                    matches.append(str(Path(current) / name))
                if visited >= max_entries or len(matches) >= max_matches:
                    capped = True
                    return {'paths': matches, 'entries_examined': visited, 'capped': capped, 'errors': errors}
    return {'paths': matches, 'entries_examined': visited, 'capped': capped, 'errors': errors}


def main():
    parser = argparse.ArgumentParser(description='Read-only audio/DSP inventory; writes only its report directory')
    parser.parse_args()
    if platform.system() != 'Linux':
        parser.error('Run this inventory on the Linux EVK')
    report = {'scope': 'Inventory only; no processing, firmware loading, recording or mixer/routing changes',
              'lpass_application_access_verified': False,
              'timestamp': datetime.now(timezone.utc).isoformat(),
              'architecture': platform.machine(), 'kernel': platform.release()}
    tools = ['aplay', 'arecord', 'amixer', 'tinymix', 'tinyplay', 'tinycap',
             'agmplay', 'agmcap', 'agmhostless', 'pal_test', 'gst-inspect-1.0',
             'pactl', 'pw-cli', 'qnn-net-run']
    report['tools'] = {name: shutil.which(name) for name in tools}
    report['files'] = {p: read(p) for p in ['/etc/os-release', '/proc/asound/cards', '/proc/asound/pcm',
                                         '/proc/asound/modules', '/etc/asound.conf']}
    modules = read('/proc/modules')
    if 'text' in modules:
        modules['text'] = '\n'.join(line for line in modules['text'].splitlines() if PATTERN.search(line))
    report['kernel_modules'] = modules
    report['commands'] = {
        'playback_devices': command(['aplay', '-l']),
        'capture_devices': command(['arecord', '-l']),
        'pcm_routes': command(['aplay', '-L']),
        'packages': command(['rpm', '-qa']),
        'audio_services': command(['systemctl', 'list-units', '--all', '--no-pager', '--plain', '*audio*', '*adsp*', '*agm*', '*pal*', '*pipewire*', '*pulse*']),
    }
    report['remote_processors'] = [
        {'path': str(p), **{name: read(p / name, 2000) for name in ('name', 'state', 'firmware')}}
        for p in sorted(Path('/sys/class/remoteproc').glob('remoteproc*'))]
    report['device_nodes'] = sorted({str(p) for pattern in ('/dev/*fastrpc*', '/dev/*adsprpc*', '/dev/*cdsprpc*', '/dev/snd/*') for p in Path('/').glob(pattern.lstrip('/'))})
    report['libraries_headers_firmware'] = scan(['/usr/include', '/usr/lib', '/lib/firmware', '/vendor/lib', '/opt'])
    report['configuration_documentation'] = scan(['/etc/agm', '/etc/pal', '/etc/audioreach', '/usr/share/alsa', '/usr/share/doc'], max_entries=12000, max_matches=100)
    # ALSA control names only: never cget/cset, mixer value writes or audio playback.
    report['mixer_control_names'] = {p.name: command(['amixer', '-c', p.name[4:], 'controls'])
                                     for p in sorted(Path('/proc/asound').glob('card[0-9]*')) if p.name[4:].isdigit()}
    run = ROOT / 'audio-dsp-probes' / (datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ-') + uuid.uuid4().hex[:8])
    run.mkdir(parents=True)
    (run / 'inventory.json').write_text(json.dumps(report, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
    lines = ['Audio DSP inventory (access is NOT yet verified)', 'Full report: ' + str(run / 'inventory.json'),
             'Installed tools: ' + ', '.join(name for name, value in report['tools'].items() if value)]
    for name in ('packages', 'playback_devices', 'capture_devices', 'audio_services'):
        lines.extend(['\n' + name + ':', json.dumps(report['commands'][name], ensure_ascii=False)])
    lines.append('\nRemote processors:')
    lines.extend(json.dumps(p, ensure_ascii=False) for p in report['remote_processors'])
    lines.append('\nDevice nodes: ' + ', '.join(report['device_nodes']))
    paths = report['libraries_headers_firmware']['paths'] + report['configuration_documentation']['paths']
    focused = [p for p in paths if re.search(r'audioreach|lpass|adsp|agm|libpal|qap|fastrpc', p, re.I)]
    lines.append('\nSelected candidate paths (bounded scan):')
    lines.extend(focused[:80])
    lines.append('\nMixer cards inspected: ' + ', '.join(report['mixer_control_names']))
    lines.append('Scan capped: ' + str(report['libraries_headers_firmware']['capped'] or report['configuration_documentation']['capped']))
    summary = '\n'.join(lines) + '\n'
    (run / 'summary.txt').write_text(summary, encoding='utf-8')
    print(summary)


if __name__ == '__main__':
    main()
