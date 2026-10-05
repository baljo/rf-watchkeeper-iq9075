# Verify METEOR persistence, reboot guards and capture recovery without touching RF or rebooting; 2026-10-04 22:20 EEST, Thomas Vikström.
import ast
from datetime import datetime, timedelta, timezone
import io
import json
from pathlib import Path
import subprocess
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch, Mock

import meteor_recovery as recovery
import meteor_pipeline as pipeline
import rf_health


class RecoveryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        (self.root / 'data').mkdir()
        self.health_patch = patch.object(rf_health, 'DB', self.root / 'health-test.db')
        self.health_patch.start()
        self.health_root_patch = patch.object(rf_health, 'ROOT', self.root)
        self.health_root_patch.start()
        self.stamp = datetime.now(timezone.utc)
        self.path = self.root / 'pass.json'
        self.metadata = self.root / 'capture.json'
        self.iq = self.root / 'capture.cu8'
        self.value = dict(state='reserved', reboot_count=0, boot_id='before',
                          record_stop=(self.stamp + timedelta(minutes=10)).isoformat(),
                          metadata=str(self.metadata), iq=str(self.iq), managed_record=None, argv=['fake-recorder'])
        recovery.save(self.path, self.value)
        self.patches = [patch.object(recovery, 'now', return_value=self.stamp),
                        patch.object(recovery, 'boot_id', return_value='before'),
                        patch.object(recovery.subprocess, 'run', return_value=SimpleNamespace(returncode=0)),
                        patch.object(recovery.subprocess, 'check_output', return_value='yes'),
                        patch.object(recovery, 'other_satellite', return_value=None)]
        self.mocks = [p.start() for p in self.patches]

    def tearDown(self):
        for p in reversed(self.patches):
            p.stop()
        self.health_patch.stop()
        self.health_root_patch.stop()
        self.temp.cleanup()

    def read(self):
        return json.loads(self.path.read_text())

    def reboot_state(self):
        self.value.update(state='reboot_requested', reboot_count=1, requested_at=self.stamp.isoformat())
        recovery.save(self.path, self.value)

    def test_persistence_precedes_reboot(self):
        sequence = []
        def install(path):
            sequence.append('persistent_units')
            return 'fake-unit'
        def run(argv, **kwargs):
            if argv[0] == '/bin/sh':
                self.assertEqual(self.read()['reboot_count'], 1)
                self.assertEqual(self.read()['state'], 'reboot_requested')
                sequence.append('reboot')
            else:
                sequence.append(argv[1])
            return SimpleNamespace(returncode=0)
        self.mocks[2].side_effect = run
        with patch.object(recovery, 'install_timer', side_effect=install):
            self.assertTrue(recovery.request_reboot(self.path))
        self.assertEqual(sequence, ['persistent_units', 'enable', 'is-enabled', 'reboot'])

    def test_one_reboot_only(self):
        self.reboot_state()
        with patch.object(recovery, 'install_timer') as install:
            self.assertFalse(recovery.request_reboot(self.path))
            install.assert_not_called()
        self.mocks[2].assert_not_called()

    def test_concurrent_reboot_request_is_refused(self):
        with self.path.with_suffix('.reboot.lock').open('a') as stream:
            recovery.fcntl.flock(stream, recovery.fcntl.LOCK_EX | recovery.fcntl.LOCK_NB)
            self.assertFalse(recovery.request_reboot(self.path))
        self.mocks[2].assert_not_called()

    def test_short_window_refuses_reboot(self):
        self.value['record_stop'] = (self.stamp + timedelta(seconds=100)).isoformat()
        recovery.save(self.path, self.value)
        with patch.object(recovery, 'install_timer') as install:
            self.assertFalse(recovery.request_reboot(self.path))
            install.assert_not_called()

    def test_install_failure_never_reboots(self):
        with patch.object(recovery, 'install_timer', side_effect=RuntimeError('verify failed')):
            with self.assertRaises(RuntimeError):
                recovery.request_reboot(self.path)
        self.mocks[2].assert_not_called()
        self.assertEqual(self.read()['reboot_count'], 0)

    def test_enable_failure_never_reboots(self):
        def run(argv, **kwargs):
            self.assertNotEqual(argv[0], '/bin/sh')
            if argv[1] == 'enable':
                raise subprocess.CalledProcessError(1, argv)
            return SimpleNamespace(returncode=0)
        self.mocks[2].side_effect = run
        with patch.object(recovery, 'install_timer', return_value='fake-unit'):
            with self.assertRaises(subprocess.CalledProcessError):
                recovery.request_reboot(self.path)
        self.assertEqual(self.read()['state'], 'failed')

    def test_reboot_rejected_releases_reservation(self):
        def run(argv, **kwargs):
            return SimpleNamespace(returncode=1 if argv[0] == '/bin/sh' else 0)
        self.mocks[2].side_effect = run
        with patch.object(recovery, 'install_timer', return_value='fake-unit'):
            self.assertFalse(recovery.request_reboot(self.path))
        self.assertFalse(recovery.pending(self.path))

    def test_current_boot_does_not_duplicate_capture(self):
        self.reboot_state()
        recovery.resume(self.path)
        self.mocks[2].assert_not_called()

    def test_reboot_not_occurred_is_bounded(self):
        self.reboot_state()
        self.value['requested_at'] = (self.stamp - timedelta(seconds=121)).isoformat()
        recovery.save(self.path, self.value)
        recovery.resume(self.path)
        self.assertEqual(self.read()['state'], 'failed')

    def test_expired_window_fails_without_recorder(self):
        self.reboot_state()
        self.value['record_stop'] = (self.stamp - timedelta(seconds=1)).isoformat()
        recovery.save(self.path, self.value)
        self.mocks[1].return_value = 'after'
        recovery.resume(self.path)
        self.assertEqual(self.read()['state'], 'failed')
        self.assertFalse(any(c.args[0] == ['fake-recorder'] for c in self.mocks[2].call_args_list))

    def test_unsynchronized_clock_defers(self):
        self.reboot_state()
        self.mocks[1].return_value = 'after'
        self.mocks[3].return_value = 'no'
        recovery.resume(self.path)
        self.assertTrue(recovery.pending(self.path))
        self.mocks[2].assert_not_called()

    def test_conflicting_satellite_is_preserved(self):
        self.reboot_state()
        self.mocks[1].return_value = 'after'
        self.mocks[4].return_value = 'meteor-other.service'
        recovery.resume(self.path)
        self.assertEqual(self.read()['state'], 'failed')
        for call in self.mocks[2].call_args_list:
            self.assertNotEqual(call.args[0], ['systemctl', 'start', pipeline.SCHEDULER])

    def test_resume_success_keeps_original_argv(self):
        self.reboot_state()
        self.mocks[1].return_value = 'after'
        self.iq.write_bytes(b'\x80' * 100)
        recovery.save(self.metadata, dict(status='completed', actual_start=self.stamp.isoformat(),
                      actual_stop=(self.stamp + timedelta(seconds=1)).isoformat(), sample_rate_sps=50))
        recovery.resume(self.path)
        self.assertEqual(self.read()['state'], 'completed')
        self.assertEqual(self.mocks[2].call_args_list[0].args[0], self.value['argv'])

    def test_resume_zero_iq_fails(self):
        self.reboot_state()
        self.mocks[1].return_value = 'after'
        recovery.save(self.metadata, dict(status='failed_iq_preflight'))
        recovery.resume(self.path)
        self.assertEqual(self.read()['state'], 'failed')
        self.assertEqual(self.read()['reboot_count'], 1)

    def test_resume_timeout_is_terminal(self):
        self.reboot_state()
        self.mocks[1].return_value = 'after'
        recovery.save(self.metadata, dict(status='reboot_recovery_pending'))
        def run(argv, **kwargs):
            if argv == ['fake-recorder']:
                raise subprocess.TimeoutExpired(argv, 1)
            if argv[1] == 'is-active':
                return SimpleNamespace(returncode=1)
            return SimpleNamespace(returncode=0)
        self.mocks[2].side_effect = run
        with patch.object(recovery, 'release_v4') as release:
            recovery.resume(self.path)
        release.assert_called_once_with('V4MAIN01')
        self.assertEqual(self.read()['state'], 'failed')
        self.assertTrue(any(c.args[0] == ['systemctl', 'start', pipeline.SCHEDULER] for c in self.mocks[2].call_args_list))

    def test_second_interruption_never_recaptures(self):
        self.reboot_state()
        self.value['state'] = 'resuming'
        recovery.save(self.path, self.value)
        self.mocks[1].return_value = 'third-boot'
        recovery.resume(self.path)
        self.assertEqual(self.read()['state'], 'failed')
        self.assertFalse(any(c.args[0] == ['fake-recorder'] for c in self.mocks[2].call_args_list))

    def test_generated_units_live_on_disk_and_validate(self):
        with patch.object(recovery, 'UNITS', self.root):
            name = recovery.install_timer(self.path)
        text = (self.root / (name + '.service')).read_text()
        timer = (self.root / (name + '.timer')).read_text()
        self.assertIn('meteor_recovery.py resume ' + str(self.path), text)
        self.assertIn('OnBootSec=20s', timer)
        self.assertIn('WantedBy=timers.target', timer)
        self.assertEqual(self.mocks[2].call_args_list[0].args[0][0], 'systemd-analyze')

    def test_managed_claim_survives_dispatch(self):
        p = dict(id='test', satellite='M2-4', start=self.stamp.isoformat(), status='claimed')
        data = dict(generated_at=self.stamp.isoformat(), passes=[p])
        with patch.object(pipeline, 'STATE', self.root), patch.object(pipeline, 'event'), \
             patch.object(pipeline, 'synchronized'), patch.object(pipeline, 'lock'), \
             patch.object(pipeline, 'plans', return_value=data), patch.object(pipeline, 'active', return_value=False), \
             patch.object(recovery, 'pending', return_value=True), patch.object(pipeline, 'save'):
            pipeline.dispatch(dict(enabled=True))
        self.assertEqual(p['status'], 'claimed')

    def test_boot_recover_does_not_restart_scheduler_for_pending(self):
        r = dict(owner='meteor-auto-v1', state='reboot_recovery_pending',
                 **{'pass': dict(satellite='M2-4', start=self.stamp.isoformat())})
        with patch.object(pipeline, 'records', return_value=[self.path]), patch.object(pipeline, 'read', return_value=r), \
             patch.object(recovery, 'pending', return_value=True), patch.object(pipeline, 'command') as command:
            pipeline.recover()
            command.assert_not_called()

    def test_real_iq_preflight_rejects_zero_bytes_three_times(self):
        source = ast.parse((Path(__file__).parent / 'satellite_capture.py').read_text())
        functions = [n for n in source.body if isinstance(n, (ast.Import, ast.ImportFrom, ast.FunctionDef))]
        namespace = dict(RTL_SDR='/fake/rtl_sdr', record_stop=self.stamp + timedelta(minutes=5))
        exec(compile(ast.Module(body=functions, type_ignores=[]), 'satellite_capture.py', 'exec'), namespace)
        fake = Mock()
        fake.__enter__ = Mock(return_value=fake)
        fake.__exit__ = Mock(return_value=False)
        fake.communicate.return_value = (b'', b'Reading samples in async mode...')
        fake.returncode = 0
        with patch.object(subprocess, 'Popen', return_value=fake) as spawn, patch('time.sleep'):
            result = namespace['iq_preflight'](SimpleNamespace(device='V4MAIN01', frequency=137900000, sample_rate=256000, gain=49.6))
        self.assertFalse(result['success'])
        self.assertEqual(result['attempt_count'], 3)
        self.assertEqual(result['byte_count'], 0)
        self.assertEqual(spawn.call_args.args[0][2:10], ['V4MAIN01', '-f', '137900000', '-s', '256000', '-g', '49.6', '-n'])

    def test_terminal_timer_does_not_rerun(self):
        self.value['state'] = 'completed'
        recovery.save(self.path, self.value)
        recovery.resume(self.path)
        self.assertEqual(self.mocks[2].call_args_list[0].args[0][1], 'disable')

    def execute_recorder(self, reboot):
        source = ast.parse((Path(__file__).parent / 'satellite_capture.py').read_text())
        mocked = {'device_visible', 'iq_preflight', 'scheduler_start', 'scheduler_stop', 'wait_until'}
        source.body = [n for n in source.body if not (isinstance(n, ast.FunctionDef) and n.name in mocked)]
        for n in source.body:
            if isinstance(n, ast.Assign) and any(isinstance(v, ast.Name) and v.id == 'OUTDIR' for v in n.targets):
                n.value = ast.Name(id='test_outdir', ctx=ast.Load())
        ast.fix_missing_locations(source)
        start, stop = (self.stamp + timedelta(minutes=1)).isoformat(), (self.stamp + timedelta(minutes=10)).isoformat()
        restored, stopped = Mock(), Mock()
        namespace = dict(test_outdir=self.root / 'recordings', scheduler_start=restored, scheduler_stop=stopped,
                         device_visible=Mock(return_value=(True, 'V4MAIN01')), iq_preflight=Mock(return_value=dict(success=False)),
                         wait_until=Mock())
        with patch('sys.argv', ['satellite_capture.py', '--satellite', 'M2-4', '--start', start, '--stop', stop]), \
             patch.object(recovery, 'STATE', self.root / 'state'), patch.object(recovery, 'release_v4') as release, \
             patch.object(recovery, 'request_reboot', return_value=reboot) as request, patch('time.sleep'):
            with self.assertRaises(SystemExit) as exit_status:
                exec(compile(source, 'satellite_capture.py', 'exec'), namespace)
        stopped.assert_called_once()
        release.assert_called_once_with('V4MAIN01')
        request.assert_called_once()
        return exit_status.exception.code, restored

    def test_full_recorder_retains_reservation_after_reboot_request(self):
        code, restored = self.execute_recorder(True)
        self.assertEqual(code, 75)
        restored.assert_not_called()
        metadata = json.loads(next((self.root / 'recordings').glob('*.json')).read_text())
        self.assertEqual(metadata['status'], 'reboot_recovery_pending')
        self.assertEqual(metadata['sample_rate_sps'], 256000)

    def test_full_recorder_restores_scheduler_after_definitive_failure(self):
        code, restored = self.execute_recorder(False)
        self.assertEqual(code, 1)
        restored.assert_called_once()

    def test_cleanup_targets_only_detected_v4_owners(self):
        with patch.object(recovery, 'v4_owners', side_effect=[[(123, ['rtl_fm', '-d', 'V4MAIN01'])], []]), \
             patch.object(recovery.os, 'kill') as kill, patch('time.sleep'):
            recovery.release_v4('V4MAIN01')
        kill.assert_called_once_with(123, recovery.signal.SIGTERM)

    def test_cleanup_escalates_only_when_v4_owner_remains(self):
        owner = [(123, ['AIS-catcher', '-d', 'V4MAIN01'])]
        with patch.object(recovery, 'v4_owners', side_effect=[owner, owner, []]), \
             patch.object(recovery.os, 'kill') as kill, patch('time.sleep'):
            recovery.release_v4('V4MAIN01')
        self.assertEqual([c.args[1] for c in kill.call_args_list], [recovery.signal.SIGTERM, recovery.signal.SIGKILL])

    def test_dispatch_idle_logs_once_per_plan(self):
        data = dict(generated_at=self.stamp.isoformat(), passes=[])
        with patch.object(pipeline, 'STATE', self.root), patch.object(pipeline, 'synchronized'), \
             patch.object(pipeline, 'lock'), patch.object(pipeline, 'plans', return_value=data), \
             patch.object(pipeline, 'active', return_value=False), patch.object(pipeline, 'event') as event:
            pipeline.dispatch(dict(enabled=True))
            pipeline.dispatch(dict(enabled=True))
        event.assert_called_once()

    def test_managed_capture_preserves_claim_after_reboot_request(self):
        p = dict(id='test-pass', satellite='M2-4', start=(self.stamp + timedelta(minutes=1)).isoformat(),
                 stop=(self.stamp + timedelta(minutes=10)).isoformat(), record_start=self.stamp.isoformat(),
                 record_stop=(self.stamp + timedelta(minutes=10)).isoformat(), status='claimed',
                 frequency=137900000, sample_rate=256000, gain=49.6, device='V4MAIN01',
                 pre_margin=90, post_margin=90, preflight_seconds=120)
        with patch.object(pipeline, 'ROOT', self.root), patch.object(pipeline, 'STATE', self.root / 'auto'), \
             patch.object(pipeline, 'now', return_value=self.stamp), patch.object(pipeline, 'lock'), \
             patch.object(pipeline, 'synchronized'), patch.object(pipeline, 'plans', return_value=dict(passes=[p])), \
             patch.object(pipeline, 'satellite_busy', return_value=None), patch.object(pipeline, 'reservations', return_value=[]), \
             patch.object(pipeline, 'active', return_value=True), patch.object(pipeline, 'run_capture', return_value=75), \
             patch.object(recovery, 'pending', return_value=True), patch.object(pipeline, 'update_pass') as update, \
             patch.object(pipeline, 'event'):
            pipeline.capture(dict(enabled=True, max_lateness_seconds=30, min_free_gib=0))
        update.assert_not_called()
        saved = json.loads((self.root / 'auto/passes/test-pass/pass.json').read_text())
        self.assertEqual(saved['state'], 'reboot_recovery_pending')
        self.assertIn('--recovery-record', saved['capture_command'])


if __name__ == '__main__':
    unittest.main()
