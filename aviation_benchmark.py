# Evaluate synthetic aviation-English recordings against references while preserving raw ASR events. 2026-09-17 19:48 EEST — Thomas Vikström.
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import signal
import subprocess
import sys
import uuid

ROOT = Path(__file__).resolve().parent
DIGITS = dict(zip('zero one two three four five six seven eight nine'.split(), '0123456789'))
DIGITS.update(niner='9', fife='5', tree='3')


def tokens(text):
    # Only documented spelling/format equivalents: never guess corrections to numbers.
    text = re.sub(r'(?<=\d)\.(?=\d)', ' decimal ', text.lower())
    result = []
    for word in re.findall(r'[a-z]+|\d+', text):
        word = DIGITS.get(word, word)
        result.extend(list(word) if word.isdigit() else [word])
    return result


def distance(left, right):
    row = list(range(len(right) + 1))
    for i, a in enumerate(left, 1):
        nxt = [i]
        for j, b in enumerate(right, 1):
            nxt.append(min(row[j] + 1, nxt[-1] + 1, row[j-1] + (a != b)))
        row = nxt
    return row[-1]


def contains_phrase(haystack, needle):
    for i in range(len(haystack) - len(needle) + 1):
        end = i + len(needle)
        if haystack[i:end] != needle:
            continue
        if needle[0].isdigit() and i and haystack[i-1].isdigit():
            continue
        if needle[-1].isdigit() and end < len(haystack) and haystack[end].isdigit():
            continue
        return True
    return False


def assess(case, text):
    reference, actual = tokens(case['reference']), tokens(text)
    edits = distance(reference, actual)
    checks = [{'phrase': p, 'matched': contains_phrase(actual, tokens(p))} for p in case['critical_phrases']]
    return {'reference': case['reference'], 'transcription': text,
            'normalized_token_errors': edits, 'reference_tokens': len(reference),
            'normalized_token_error_rate': edits / len(reference),
            'critical_checks': checks, 'all_critical_phrases_matched': all(c['matched'] for c in checks)}


def invoke(command, stdout_path, stderr_path):
    with stdout_path.open('wb') as out, stderr_path.open('wb') as err:
        with subprocess.Popen(command, stdout=out, stderr=err, start_new_session=(os.name == 'posix')) as process:
            try:
                return process.wait(timeout=220)
            except BaseException:
                if os.name == 'posix':
                    try:
                        os.killpg(process.pid, signal.SIGKILL)
                    except ProcessLookupError:
                        pass
                else:
                    process.kill()
                process.wait()
                raise


def main():
    parser = argparse.ArgumentParser(description='Offline synthetic speech evaluation; no SDR required')
    parser.add_argument('--repeat', type=int, default=2)
    args = parser.parse_args()
    if not 1 <= args.repeat <= 10:
        parser.error('--repeat must be 1–10')
    fixture = ROOT / 'aviation-fixtures'
    manifest = json.loads((fixture / 'manifest.json').read_text(encoding='utf-8'))
    # Validate all recordings before starting inference.
    for case in manifest['cases']:
        path = (fixture / case['file']).resolve()
        if path.parent != fixture.resolve() or hashlib.sha256(path.read_bytes()).hexdigest() != case['sha256']:
            raise ValueError('Fixture path/hash mismatch: ' + case['id'])
    run_id = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ-') + uuid.uuid4().hex[:8]
    output = ROOT / 'aviation-runs' / run_id
    output.mkdir(parents=True)
    report = {'run_id': run_id, 'input_kind': 'synthetic_clean_English',
              'purpose': 'Development benchmark, not real-radio or operational validation',
              'scoring': 'Lowercase words; ignore punctuation; digit words/digits and niner/fife/tree equivalents. No inferred correction or general number expansion. Critical phrase matches are a screening metric, not full semantic validation.',
              'fixture_manifest': manifest, 'iterations': args.repeat, 'results': []}
    try:
        for case in manifest['cases']:
            for iteration in range(1, args.repeat + 1):
                stem = '{}-{}'.format(case['id'], iteration)
                out, err = output / (stem + '.jsonl'), output / (stem + '.log')
                command = [sys.executable, str(ROOT / 'asr_offline.py'), str(fixture / case['file']),
                           '--language', 'en', '--job-id', 'aviation-synthetic-test']
                entry = {'case': case['id'], 'iteration': iteration, 'stdout': str(out), 'diagnostics': str(err)}
                try:
                    code = invoke(command, out, err)
                    events = [json.loads(line) for line in out.read_text(encoding='utf-8').splitlines() if line.strip()]
                    transcriptions = [e for e in events if e.get('event_type') == 'transcription']
                    if code or len(transcriptions) != 1:
                        raise RuntimeError('ASR failed or did not emit one transcription; inspect ' + str(err))
                    event = transcriptions[0]
                    entry.update(assess(case, event['text']))
                    entry.update(status='evaluated', event=event)
                    print('{} run {}: {} critical phrases; token error rate {:.1%}'.format(case['id'], iteration,
                          'PASS' if entry['all_critical_phrases_matched'] else 'REVIEW', entry['normalized_token_error_rate']))
                    print('  Heard: ' + event['text'])
                    for check in entry['critical_checks']:
                        if not check['matched']:
                            print('  Check: ' + check['phrase'])
                except (OSError, ValueError, RuntimeError, subprocess.TimeoutExpired) as error:
                    entry.update(status='failed', error=str(error))
                    print(str(error))
                report['results'].append(entry)
        report['repeat_text_consistent'] = {
            case['id']: (len([r for r in report['results'] if r['case'] == case['id'] and r['status'] == 'evaluated']) == args.repeat
                         and len({tuple(tokens(r['transcription'])) for r in report['results'] if r['case'] == case['id'] and r['status'] == 'evaluated'}) == 1)
            for case in manifest['cases']}
        report['status'] = 'completed' if all(r['status'] == 'evaluated' for r in report['results']) else 'completed_with_failures'
        return 0 if report['status'] == 'completed' else 1
    finally:
        (output / 'report.json').write_text(json.dumps(report, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
        print('Report: ' + str(output / 'report.json'))


if __name__ == '__main__':
    sys.exit(main())
