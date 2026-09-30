"""Real small Python process trees and mocks; no Java, Gradle, or Docker."""
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import process_runner as runner


class ProcessRunnerTests(unittest.TestCase):
    def test_success_keeps_log_and_exit_status(self):
        with tempfile.TemporaryDirectory() as folder:
            log = Path(folder) / 'run.log'
            code = runner.run_logged([sys.executable, '-c', 'print("output preserved"); raise SystemExit(7)'],
                                     log=log, timeout=30)
            self.assertEqual(7, code)
            self.assertIn('output preserved', log.read_text())

    def test_cleanup_kills_group_before_reaping_leader(self):
        events = []
        process = Mock(pid=54321)
        process.wait.side_effect = lambda: events.append('reap')
        with patch.object(runner.os, 'killpg', side_effect=lambda pid, sig: events.append(sig)), \
             patch.object(runner.os, 'waitid', side_effect=lambda *args: events.append('observe-unreaped') or object()) as observe:
            runner._terminate_group(process, 15)
        self.assertEqual([signal.SIGTERM, 'observe-unreaped', signal.SIGKILL, 'reap'], events)
        self.assertTrue(observe.call_args.args[2] & os.WNOWAIT)

    def test_timeout_kills_term_ignoring_child_after_leader_exits(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            pid_file = root / 'child.pid'
            child = ('import os,signal,time; from pathlib import Path; '
                     'signal.signal(signal.SIGTERM,signal.SIG_IGN); '
                     f'Path({str(pid_file)!r}).write_text(str(os.getpid())); '
                     'time.sleep(60)')
            leader = ('import subprocess,sys,time; '
                      f'subprocess.Popen([sys.executable,"-c",{child!r}]); '
                      'print("leader started",flush=True); time.sleep(60)')
            try:
                with self.assertRaises(subprocess.TimeoutExpired):
                    runner.run_logged([sys.executable, '-c', leader], log=root / 'run.log', timeout=16)
                self.assertTrue(pid_file.exists(), 'child fixture did not start')
                pid = int(pid_file.read_text())
                stopped = False
                for _ in range(40):
                    stat = Path(f'/proc/{pid}/stat')
                    if not stat.exists() or stat.read_text().split()[2] in ('Z', 'X'):
                        stopped = True
                        break
                    time.sleep(0.05)
                self.assertTrue(stopped, 'child remained live after group cleanup')
                self.assertIn('leader started', (root / 'run.log').read_text())
            finally:
                # Exact PID created by this test only; never global process matching.
                if pid_file.exists():
                    try:
                        os.kill(int(pid_file.read_text()), signal.SIGKILL)
                    except ProcessLookupError:
                        pass

    def test_second_interrupt_during_grace_still_kills_and_reaps(self):
        process = Mock(pid=54321)
        with patch.object(runner.os, 'killpg') as kill, \
             patch.object(runner, '_wait_unreaped', side_effect=KeyboardInterrupt):
            with self.assertRaises(KeyboardInterrupt):
                runner._terminate_group(process, 15)
        self.assertEqual([(54321, signal.SIGTERM), (54321, signal.SIGKILL)],
                         [call.args for call in kill.call_args_list])
        process.wait.assert_called_once_with()

    def test_keyboard_interrupt_cleans_group_without_wait_reaping_race(self):
        import _thread
        import threading
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            pid_file = root / 'child.pid'
            child = ('import os,signal,time; from pathlib import Path; '
                     'signal.signal(signal.SIGTERM,signal.SIG_IGN); '
                     f'Path({str(pid_file)!r}).write_text(str(os.getpid())); time.sleep(60)')
            leader = ('import subprocess,sys,time; '
                      f'subprocess.Popen([sys.executable,"-c",{child!r}]); time.sleep(60)')
            timer = threading.Timer(0.5, _thread.interrupt_main)
            try:
                timer.start()
                with self.assertRaises(KeyboardInterrupt):
                    runner.run_logged([sys.executable, '-c', leader], log=root / 'run.log', timeout=30)
                self.assertTrue(pid_file.exists())
                pid = int(pid_file.read_text())
                for _ in range(40):
                    stat = Path(f'/proc/{pid}/stat')
                    if not stat.exists() or stat.read_text().split()[2] in ('Z', 'X'):
                        break
                    time.sleep(0.05)
                else:
                    self.fail('TERM-ignoring child survived KeyboardInterrupt cleanup')
            finally:
                timer.cancel()
                if pid_file.exists():
                    try:
                        os.kill(int(pid_file.read_text()), signal.SIGKILL)
                    except ProcessLookupError:
                        pass

    def test_budget_must_reserve_cleanup(self):
        with tempfile.TemporaryDirectory() as folder, patch.object(runner.subprocess, 'Popen') as popen:
            with self.assertRaises(ValueError):
                runner.run_logged(['never-start'], log=Path(folder) / 'log', timeout=15)
            popen.assert_not_called()

    def test_missing_waitid_runtime_clis_fail_before_any_output_or_fixture(self):
        import academy_gate
        import distributed_integration_audit
        import placeholder_audit
        with tempfile.TemporaryDirectory() as folder, patch.dict(runner.os.__dict__):
            del runner.os.__dict__['waitid']
            root = Path(folder)
            calls = [
                (academy_gate.main, ['roundtrip']),
                (distributed_integration_audit.main, ['--execute']),
                (placeholder_audit.main, ['--course', 'java-foundations', '--junit-console', '/unused.jar']),
            ]
            with self.assertRaisesRegex(OSError, 'macOS use Python 3.13'):
                runner.check_support()
            for index, (main, prefix) in enumerate(calls):
                work, report = root / str(index), root / (str(index) + '.json')
                with self.subTest(main=main.__module__), patch.object(runner.subprocess, 'Popen') as popen:
                    self.assertEqual(1, main(prefix + ['--work-dir', str(work), '--report', str(report)]))
                    self.assertFalse(work.exists())
                    self.assertFalse(report.exists())
                    popen.assert_not_called()


if __name__ == '__main__':
    unittest.main()
