import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch
from audio_workflow import AudioWorkflow


class CatalogCacheTests(unittest.TestCase):
    def test_progress_polls_cache_and_expire_without_sharing_mutable_rows(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            workflow = AudioWorkflow(root, root / 'events', root / 'config')
            workflow._scan_catalog = Mock(return_value={'a': {'ready': True}})
            with patch('audio_workflow.time.monotonic', return_value=100):
                workflow.catalog()['a']['ready'] = False
                self.assertTrue(workflow.catalog()['a']['ready'])
                self.assertEqual(workflow._scan_catalog.call_count, 1)
            with patch('audio_workflow.time.monotonic', return_value=131):
                workflow.catalog()
                self.assertEqual(workflow._scan_catalog.call_count, 2)

    def test_deleted_recording_is_rejected_even_with_cached_selection(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            workflow = AudioWorkflow(root, root / 'events', root / 'config')
            workflow._scan_catalog = Mock(side_effect=[{'a': {'ready': True}}, {}])
            workflow.catalog()
            with self.assertRaises(ValueError):
                workflow.recording('a')


if __name__ == '__main__':
    unittest.main()
