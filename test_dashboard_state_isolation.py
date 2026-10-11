import subprocess
import unittest
from unittest.mock import patch
import dashboard


class StateIsolationTests(unittest.TestCase):
    def test_paths_and_output_are_preserved(self):
        with patch('dashboard.subprocess.run') as run:
            run.return_value.stdout = b'{"dashboard":"online"}'
            result = dashboard.isolated_snapshot('events', 'status', 'asr', 'db', 'sensor')
            self.assertEqual(result, b'{"dashboard":"online"}')
            command = run.call_args.args[0]
            self.assertIn('--snapshot-only', command)
            for flag, value in [('--log', 'events'), ('--status', 'status'),
                                ('--transcription-log', 'asr'), ('--db', 'db'),
                                ('--sensor-status', 'sensor')]:
                self.assertEqual(command[command.index(flag) + 1], value)
            self.assertEqual(run.call_args.kwargs['timeout'], 12)

    def test_failure_releases_worker_slot(self):
        with patch('dashboard.subprocess.run', side_effect=subprocess.TimeoutExpired('state', 12)):
            for _ in range(3):
                with self.assertRaises(subprocess.TimeoutExpired):
                    dashboard.isolated_snapshot('events', 'status', None, 'db', None)


if __name__ == '__main__':
    unittest.main()
