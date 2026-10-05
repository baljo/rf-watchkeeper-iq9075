# Inventory AudioReach/PAL/AGM runtime APIs and test documented symbols without changing the EVK. 2026-09-17 20:20 EEST — Thomas Vikström.
import json
from datetime import datetime, timezone
from pathlib import Path
import platform
import re
import shutil
import subprocess
import uuid
import ctypes

ROOT = Path(__file__).resolve().parent


def run(argv, timeout=15, limit=50000):
    binary = shutil.which(argv[0])
    if not binary:
        return {'available': False}
    try:
        result = subprocess.run([binary] + argv[1:], stdout=subprocess.PIPE,
                                stderr=subprocess.STDOUT, timeout=timeout,
                                env=dict(__import__('os').environ, LC_ALL='C'))
        text = result.stdout.decode('utf-8', errors='replace')
        return {'available': True, 'exit_code': result.returncode,
                'text': text[:limit], 'truncated': len(text) > limit}
    except (OSError, subprocess.TimeoutExpired) as error:
        return {'available': True, 'error': str(error)}


def selected_symbols(path):
    result = run(['nm', '-D', '--defined-only', str(path)], timeout=20, limit=200000)
    if not result.get('available') or 'text' not in result:
        return result
    lines = []
    for line in result['text'].splitlines():
        if re.search(r'\b(gsl_|pal_|agm_|audio|stream|pcm|graph|route)', line, re.I):
            lines.append(line)
    return {'available': True, 'exit_code': result.get('exit_code'),
            'symbols': lines[:2000], 'truncated': len(lines) > 2000}


def main():
    if platform.system() != 'Linux':
        raise SystemExit('Run this read-only probe on the EVK Linux image')
    report = {'timestamp': datetime.now(timezone.utc).isoformat(),
              'scope': 'Read-only inventory; no graph, mixer, firmware, service or ACDB changes',
              'architecture': platform.machine()}
    packages = ['audioreach-conf', 'audioreach-pal', 'audioreach-pal-headers',
                'audioreach-audio-utils', 'audioreach-graphmgr', 'audioreach-graphservices',
                'audioreach-pipewire-plugin', 'fastrpc', 'fastrpc-tests']
    report['packages'] = {package: run(['rpm', '-ql', package], timeout=20, limit=100000)
                          for package in packages}
    report['tools'] = {tool: shutil.which(tool) for tool in (
        'agmcap', 'agmplay', 'agmhostless', 'agm_mixer', 'tinymix', 'tinyplay',
        'tinycap', 'pal_test', 'fastrpc_test', 'gst-inspect-1.0', 'nm', 'readelf')}
    report['tool_help'] = {tool: run([tool, '--help'], timeout=8, limit=10000)
                           for tool in ('agmcap', 'agmplay', 'agmhostless', 'fastrpc_test', 'pal_test')
                           if shutil.which(tool)}
    candidate_libs = []
    for root in ('/usr/lib', '/lib'):
        candidate_libs.extend(p for p in Path(root).glob('lib*.so*')
                              if re.search(r'(agm|pal|gsl|audio|adsprpc|audioroute)', p.name, re.I))
    report['libraries'] = {str(path): selected_symbols(path) for path in sorted(set(candidate_libs))}
    documented = {
        'libar-gsl.so': ('gsl_init', 'gsl_open', 'gsl_close', 'gsl_start', 'gsl_stop', 'gsl_read', 'gsl_write', 'gsl_get_avail_buffer_size'),
        'libgsl.so.1': ('gsl_init', 'gsl_open', 'gsl_close', 'gsl_start', 'gsl_stop', 'gsl_read', 'gsl_write'),
        'libpal.so': ('pal_init', 'pal_deinit', 'pal_stream_open', 'pal_stream_start', 'pal_stream_stop', 'pal_stream_read', 'pal_stream_write', 'pal_stream_close'),
        'libagm.so': ('agm_init', 'agm_deinit', 'agm_session_open', 'agm_session_start', 'agm_session_stop', 'agm_session_read', 'agm_session_write', 'agm_session_close'),
    }
    report['dynamic_symbols'] = {}
    for library, symbols in documented.items():
        found = []
        errors = []
        try:
            handle = ctypes.CDLL('/usr/lib/' + library)
            for symbol in symbols:
                try:
                    getattr(handle, symbol)
                    found.append(symbol)
                except AttributeError:
                    pass
        except OSError as error:
            errors.append(str(error))
        report['dynamic_symbols'][library] = {'found': found, 'missing': [s for s in symbols if s not in found], 'errors': errors}
    report['candidate_paths'] = {}
    for root in ('/usr/include', '/usr/share', '/usr/lib', '/lib', '/etc'):
        result = run(['find', root, '-maxdepth', '5', '-type', 'f',
                      '(', '-iname', '*agm*', '-o', '-iname', '*pal*', '-o', '-iname', '*gsl*',
                      '-o', '-iname', '*graph*', '-o', '-iname', '*audioreach*', '-o', '-iname', '*kvh2xml*',
                      '-o', '-iname', '*h2xml*', ')'], timeout=25, limit=100000)
        report['candidate_paths'][root] = result
    report['linker_cache'] = run(['ldconfig', '-p'], timeout=10, limit=50000)
    run_id = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ-') + uuid.uuid4().hex[:8]
    output = ROOT / 'audio-dsp-probes' / run_id
    output.mkdir(parents=True)
    (output / 'api-inventory.json').write_text(json.dumps(report, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
    print('Full API inventory: ' + str(output / 'api-inventory.json'))
    for package, result in report['packages'].items():
        print('PACKAGE {}: {}'.format(package, 'available' if result.get('available') else 'missing'))
    for path, result in report['libraries'].items():
        print('LIBRARY {}: {} selected symbols'.format(path, len(result.get('symbols', []))))
    for library, result in report['dynamic_symbols'].items():
        print('DYNAMIC {}: found={} missing={}'.format(library, ','.join(result['found']) or '-', ','.join(result['missing']) or '-'))
    for tool, path in report['tools'].items():
        print('TOOL {}: {}'.format(tool, path or 'missing'))
    print('No configuration or runtime state was changed.')


if __name__ == '__main__':
    main()
