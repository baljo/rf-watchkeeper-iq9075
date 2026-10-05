# Run bounded METEOR decoding with an optional import-only profile that avoids historical map reprojection crashes; 2026-10-03 21:54:00 EEST, Thomas Vikström.
import json
import fcntl
import os
from pathlib import Path
import signal
import subprocess
import sys
import time
import uuid

ROOT = Path('/root/rf-watchkeeper')
IMAGE = 'rf-watchkeeper-satdump:1.2.2-arm64'


def argv(arguments, name):
    if len(arguments) < 4 or arguments[1] != 'baseband':
        raise ValueError('Expected pipeline baseband input-IQ output-directory options')
    if arguments[0] != 'meteor_m2-x_lrpt':
        raise ValueError('Unsupported METEOR pipeline')
    options = arguments[4:]
    # Scope the projection workaround to explicit importer calls; 2026-10-03 21:54:00 EEST, Thomas Vikström.
    profile_requested = '--import-no-projection' in options
    if options.count('--import-no-projection') > 1:
        raise ValueError('Duplicate import profile flag')
    options = [option for option in options if option != '--import-no-projection']
    mounts = []
    if profile_requested:
        profile = ROOT / 'data/satellite-import-satdump.json'
        if not profile.is_file() or profile.is_symlink():
            raise ValueError('Missing controlled import SatDump profile')
        mounts = ['--mount', 'type=bind,source={},target=/usr/share/satdump/satdump_cfg.json,readonly'.format(profile)]
    for flag in ('--samplerate', '--baseband_format', '--satellite_number'):
        if options.count(flag) != 1 or options.index(flag)+1 >= len(options):
            raise ValueError('Required separate CLI option: ' + flag)
    if options[options.index('--baseband_format')+1] != 'cu8' or options[options.index('--satellite_number')+1] not in ('M2-3','M2-4'):
        raise ValueError('Invalid recording format or satellite')
    rate = int(options[options.index('--samplerate')+1])
    if not 1 <= rate <= 10000000 or any(s.lstrip().startswith('{') for s in options):
        raise ValueError('Invalid sample rate or JSON options')
    iq = Path(arguments[2]).resolve(strict=True)
    output = Path(arguments[3]).resolve(strict=True)
    if not iq.is_file() or not output.is_dir() or ',' in str(iq) or ',' in str(output):
        raise ValueError('Invalid input/output mount path')
    return ['docker', 'run', '--rm', '--name', name, '--network', 'none', '--cpus', '2',
            '--memory', '4g', '--pids-limit', '256', '--read-only', '--cap-drop', 'ALL',
            '--security-opt', 'no-new-privileges', '--tmpfs', '/tmp:rw,size=256m',
            '--mount', 'type=bind,source={},target=/input.cu8,readonly'.format(iq),
            '--mount', 'type=bind,source={},target=/output'.format(output),
            ] + mounts + [IMAGE, arguments[0], 'baseband', '/input.cu8', '/output'] + options


def main(arguments):
    manifest = json.loads((ROOT / 'data/meteor-native-runtime.json').read_text())
    actual = subprocess.check_output(['docker', 'image', 'inspect', IMAGE, '--format', '{{.Id}}'], text=True, timeout=20).strip()
    if actual != manifest['image_id']:
        raise RuntimeError('SatDump image identity changed; review the runtime before decoding')
    c = json.loads((ROOT / 'meteor-config.json').read_text())
    limit = max(1, c['decode_timeout_seconds'] - 30)
    name = 'rf-watchkeeper-meteor-decode-' + uuid.uuid4().hex
    invocation = argv(arguments, name)
    # Cooperative shared raw lock covers Docker's delayed mount/open as well.
    raw_guard = Path(arguments[2]).open('rb')
    fcntl.flock(raw_guard, fcntl.LOCK_SH | fcntl.LOCK_NB)
    interrupted = [False]
    for sig in (signal.SIGTERM, signal.SIGINT):
        signal.signal(sig, lambda *_: interrupted.__setitem__(0, True))
    child = None
    try:
        child = subprocess.Popen(invocation)
        deadline = time.monotonic() + limit
        while child.poll() is None:
            if interrupted[0] or time.monotonic() >= deadline:
                print('SatDump decoder interrupted or time limit reached; preserving IQ', file=sys.stderr, flush=True)
                return 124
            time.sleep(0.5)
        return child.returncode
    finally:
        # Docker containers are outside the caller's systemd cgroup. Explicitly remove this UUID-owned instance.
        subprocess.run(['docker', 'rm', '-f', name], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=15, check=False)
        if child and child.poll() is None:
            child.terminate()
            try:
                child.wait(timeout=5)
            except subprocess.TimeoutExpired:
                child.kill()
                child.wait(timeout=5)
        raw_guard.close()


if __name__ == '__main__':
    try:
        raise SystemExit(main(sys.argv[1:]))
    except Exception as exc:
        print('EVK SatDump: ' + str(exc), file=sys.stderr)
        raise SystemExit(1)
