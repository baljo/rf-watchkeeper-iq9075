# Collect ASR process-library and log evidence without equating loaded libraries with accelerator execution. 2026-09-17 19:37 EEST — Thomas Vikström.
from pathlib import Path
import re
import subprocess
import time


def library_paths(maps):
    paths = set()
    for line in maps.splitlines():
        fields = line.split(None, 5)
        if len(fields) != 6:
            continue
        path = fields[5].removesuffix(' (deleted)') if hasattr(str, 'removesuffix') else fields[5].replace(' (deleted)', '')
        if path.startswith('/') and re.search(r'lib(?:Qnn|Qairt|whisper|dnnvad|nnvad|fft|[a-z]*dsprpc)', Path(path).name, re.I):
            paths.add(path)
    return paths


def observe(process, timeout, samples):
    deadline = time.monotonic() + timeout
    while process.poll() is None:
        try:
            maps = Path('/proc/{}/maps'.format(process.pid)).read_text(encoding='utf-8')
            samples['libraries'].update(library_paths(maps))
            samples['maps_samples'] += 1
        except OSError as error:
            samples['read_errors'].add(type(error).__name__)
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise subprocess.TimeoutExpired(process.args, timeout)
        try:
            return process.wait(timeout=min(0.01, remaining))
        except subprocess.TimeoutExpired:
            pass
    return process.returncode


def report(samples, log, return_code):
    paths = sorted(samples['libraries'])
    names = {Path(p).name for p in paths}
    warnings = sorted(set(line.strip() for line in log.splitlines()
                          if any(term in line for term in ('unsupported data type', 'Failed to set power config',
                                                          'Failed to set powerConfig', 'Failed to set RPC polling',
                                                          'Failed to set rpc polling'))))
    return {
        'method': 'Sample child process /proc/PID/maps every approximately 10 ms and inspect its runtime log',
        'mapped_libraries': paths,
        'maps_samples': samples['maps_samples'],
        'maps_read_errors': sorted(samples['read_errors']),
        'htp_library_observed': bool(names & {'libQnnHtp.so', 'libQairtHtp.so'}),
        'cpu_library_observed': 'libQnnCpu.so' in names,
        'encoder_latency_ms': [int(x) for x in re.findall(r'encoder latency:\s*(\d+) ms', log)],
        'callback_result_codes': sorted(set(re.findall(r'result code=\s*(\d+)', log))),
        'runtime_warnings': warnings,
        'backend_exit_code': return_code,
        'accelerator_verified': False,
        'interpretation': 'Mapped libraries show availability in this process, not graph placement. Timing and valid text alone do not prove HTP execution. Missing sampled libraries do not prove absence. CPU and HTP libraries can coexist for different pipeline stages.',
    }
