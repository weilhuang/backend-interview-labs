"""Ordinary Python child/log fixtures; no IDE, Docker or new archive samples."""
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from run_official import capture, small_logs, snapshot_before_stop, intermediate_archives, IDE_LOG_BYTES
from collect_evidence import collect


class PreterminationTests(unittest.TestCase):
    def layout(self, root):
        (root / 'evidence').mkdir()
        (root / 'export-profile/log').mkdir(parents=True)
        return root / 'export-profile/log/idea.log'

    def test_snapshot_precedes_child_shutdown_noise_and_budget_is_shared(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            log = self.layout(root)
            child = root / 'child.py'
            child.write_text("import signal,time,sys\nfrom pathlib import Path\np=Path(sys.argv[1])\np.write_text('PROGRESS before stop\\n')\ndef stop(*_):\n p.write_text('SHUTDOWN noise\\n'*30000)\n raise SystemExit(0)\nsignal.signal(signal.SIGTERM,stop)\ntime.sleep(20)\n")
            result = capture([sys.executable, str(child), str(log)], os.environ.copy(), root,
                             root / 'evidence/export.stdout.log', root / 'evidence/export.stderr.log',
                             0.1, root, phase='export')
            self.assertTrue(result['timed_out'])
            self.assertEqual(result['pretermination_snapshot']['status'], 'PASS')
            self.assertLessEqual(result['started_at_utc'], result['pretermination_snapshot']['at_utc'])
            self.assertLessEqual(result['pretermination_snapshot']['at_utc'], result['finished_at_utc'])
            before = root / 'evidence/export-idea-pretermination.log'
            self.assertIn('PROGRESS before stop', before.read_text())
            small_logs(root, root / 'evidence')
            after = root / 'evidence/export-idea.log'
            self.assertIn('SHUTDOWN noise', after.read_text())
            self.assertLessEqual(before.stat().st_size + after.stat().st_size, IDE_LOG_BYTES)
            artifact = root.parent / (root.name + '-artifact')
            self.addCleanup(__import__('shutil').rmtree, artifact, True)
            collect(root, artifact)
            self.assertLessEqual((artifact / before.name).stat().st_size +
                                 (artifact / after.name).stat().st_size, IDE_LOG_BYTES)

    def test_normal_exit_keeps_single_original_log_budget(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            log = self.layout(root)
            log.write_bytes(b'N' * (IDE_LOG_BYTES + 10))
            result = capture([sys.executable, '-c', 'pass'], os.environ.copy(), root,
                             root / 'evidence/export.stdout.log', root / 'evidence/export.stderr.log',
                             10, root, phase='export')
            self.assertFalse(result['timed_out'])
            self.assertIsNone(result['pretermination_snapshot'])
            small_logs(root, root / 'evidence')
            self.assertEqual((root / 'evidence/export-idea.log').stat().st_size, IDE_LOG_BYTES)
            self.assertFalse((root / 'evidence/export-idea-pretermination.log').exists())

    def test_unavailable_snapshot_is_diagnostic_only(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.layout(root)
            with patch('run_official.read_regular', side_effect=OSError('unavailable')):
                result = snapshot_before_stop(root, 'export')
            self.assertEqual(result['status'], 'UNAVAILABLE')
            self.assertEqual(result['error'], 'OSError')
            self.assertFalse((root / 'evidence/export-idea-pretermination.log').exists())

    def test_intermediate_metadata_is_bounded_direct_and_never_verified(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            temporary = root / 'export-profile/tmp'
            temporary.mkdir(parents=True)
            for index in range(12):
                (temporary / f'course_archive_{index}.zip').write_text('ordinary fixture text')
            (temporary / 'nested').mkdir()
            (temporary / 'nested/course_archive_nested.zip').write_text('not listed')
            (temporary / 'unrelated.txt').write_text('ignored')
            result = intermediate_archives(root, 'export')
            self.assertEqual(result['status'], 'UNVERIFIED_INTERMEDIATE')
            self.assertEqual(result['count'], 12)
            self.assertEqual(len(result['entries']), 10)
            self.assertTrue(result['truncated'])
            self.assertFalse(result['content_read'])
            self.assertTrue(all(item['size_bytes'] == len('ordinary fixture text') for item in result['entries']))
            self.assertNotIn('course_archive_nested.zip', str(result))
            self.assertEqual(intermediate_archives(root, 'validate')['status'], 'NOT_APPLICABLE')

    def test_missing_intermediate_directory_is_diagnostic_unavailable(self):
        with tempfile.TemporaryDirectory() as directory:
            result = intermediate_archives(Path(directory), 'export')
            self.assertEqual(result['status'], 'UNAVAILABLE')
            self.assertFalse(result['content_read'])

    def test_unknown_phase_is_rejected_before_spawn(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with patch('run_official.subprocess.Popen') as process:
                with self.assertRaises(ValueError):
                    capture(['unused'], {}, root, root/'out', root/'err', 1, root, phase='other')
                process.assert_not_called()


if __name__ == '__main__':
    unittest.main()
