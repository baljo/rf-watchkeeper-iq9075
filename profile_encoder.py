# Profile the existing Whisper encoder explicitly on QNN HTP using synthetic input, separately from ASR. 2026-09-17 19:44 EEST — Thomas Vikström.
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import uuid

ROOT = Path(__file__).resolve().parent


def save(path, data):
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')


def run_logged(command, path):
    with path.open('wb') as stream:
        with subprocess.Popen(command, stdout=stream, stderr=subprocess.STDOUT) as process:
            try:
                return process.wait(timeout=180)
            except BaseException:
                process.kill()
                process.wait()
                raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--prepare-only', action='store_true', help='Create input and plan; do not run QNN')
    args = parser.parse_args()
    model = ROOT / 'asr_native/model/encoder_model_htp.bin'
    run = None
    report = {'experiment': 'independent_whisper_encoder_htp_profile',
              'input_kind': 'synthetic_zero_tensor', 'whole_asr_pipeline_verified': False,
              'status': 'preparing'}
    try:
        # Bind the fixture size to the exact context already inspected in VoiceAI logs.
        manifest = json.loads((ROOT / 'asr_native/manifest.json').read_text(encoding='utf-8'))
        actual_hash = hashlib.sha256(model.read_bytes()).hexdigest()
        expected_hash = manifest['files']['asr_native/model/encoder_model_htp.bin']
        if actual_hash != expected_hash:
            raise ValueError('Encoder differs from the inspected bundle; recheck its input tensor before profiling')
        runner = shutil.which('qnn-net-run')
        viewer = shutil.which('qnn-profile-viewer')
        backend = Path('/usr/lib/libQnnHtp.so')
        if not args.prepare_only and (not runner or not viewer or not backend.is_file()):
            raise ValueError('Run on the EVK with qnn-net-run, qnn-profile-viewer and libQnnHtp.so installed')
        run_id = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ-') + uuid.uuid4().hex[:8]
        run = ROOT / 'htp-profile-runs' / run_id
        run.mkdir(parents=True)
        tensor = run / 'input_features.raw'
        # Observed input_features buffer is 480000 bytes in this exact encoder.
        # This is a graph-execution fixture, not mel features derived from audio.
        tensor.write_bytes(bytes(480000))
        inputs = run / 'inputs.txt'
        if any(c.isspace() for c in str(tensor)):
            raise ValueError('Use a project path without whitespace for this QNN input-list test')
        inputs.write_text(str(tensor) + '\n', encoding='utf-8')
        command = [runner or 'qnn-net-run', '--backend', str(backend),
                   '--retrieve_context', str(model), '--input_list', str(inputs),
                   '--output_dir', str(run / 'output'), '--use_native_input_files',
                   '--use_native_output_files', '--profiling_level', 'detailed',
                   '--num_inferences', '3', '--keep_num_outputs', '1',
                   '--perf_profile', 'system_settings', '--log_level', 'info']
        report.update(run_id=run_id, model_sha256=actual_hash, input_bytes=480000,
                      backend=str(backend), command=command,
                      note='Independent encoder test. Profile must be reviewed for execution evidence; no transcription or live events are produced.')
        save(run / 'request.json', report)
        if args.prepare_only:
            report['status'] = 'prepared_not_executed'
            return 0
        code = run_logged(command, run / 'qnn-net-run.log')
        report['qnn_exit_code'] = code
        if code:
            raise RuntimeError('qnn-net-run failed; inspect qnn-net-run.log')
        profiles = sorted((run / 'output').rglob('*profil*.log'))
        if not profiles:
            raise RuntimeError('No profiling log found; inspect qnn-net-run.log and output directory')
        report['profiles'] = []
        for index, profile in enumerate(profiles):
            text_path = run / ('profile-{}.txt'.format(index))
            csv_path = run / ('profile-{}.csv'.format(index))
            code = run_logged([viewer, '--input_log', str(profile), '--output', str(csv_path)], text_path)
            report['profiles'].append({'binary': str(profile), 'text': str(text_path), 'csv': str(csv_path), 'viewer_exit_code': code})
            if code:
                raise RuntimeError('Profile viewer failed; inspect ' + str(text_path))
        report['status'] = 'executed_profile_ready_for_review'
        for item in report['profiles']:
            print('Profile excerpt: ' + item['text'])
            lines = Path(item['text']).read_text(encoding='utf-8', errors='replace').splitlines()
            print('\n'.join(lines[:100]))
            if len(lines) > 100:
                print('(Full profile preserved in the file above.)')
        return 0
    except (OSError, ValueError, KeyError, RuntimeError, subprocess.TimeoutExpired) as error:
        report.update(status='failed', error=str(error))
        return 1
    finally:
        if run:
            save(run / 'report.json', report)
            print('Report: ' + str(run / 'report.json'))
        print(json.dumps(report, indent=2, ensure_ascii=False))


if __name__ == '__main__':
    sys.exit(main())
