"""普通 Python fixture 与静态约束回归；本测试绝不启动 Java、IDE、GUI 或 Docker。"""
import ast
import json
import os
from pathlib import Path
import signal
import struct
import sys
import tempfile
import time
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import startup_diagnostic as diag


class StartupDiagnosticTests(unittest.TestCase):
    def test_only_nonexistent_archive_and_nonacceptance_flags(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            command = diag.diagnostic_command(root / 'idea', root)
            self.assertEqual(command[1], 'validateCourse')
            self.assertEqual(command[command.index('--tests') + 1], 'false')
            self.assertEqual(command[command.index('--links') + 1], 'false')
            self.assertFalse((root / 'intentionally-missing-diagnostic-course.zip').exists())
            self.assertNotIn('createCourse', command)

    def test_existing_input_target_report_and_dangling_link_are_rejected(self):
        for name in ('intentionally-missing-diagnostic-course.zip', 'diagnostic-target',
                     'never-an-acceptance-report.json'):
            with self.subTest(name=name), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                (root / name).write_text('普通 fixture')
                with self.assertRaises(ValueError):
                    diag.diagnostic_command(root / 'idea', root)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'intentionally-missing-diagnostic-course.zip').symlink_to(root / '不存在')
            with self.assertRaises(ValueError):
                diag.diagnostic_command(root / 'idea', root)

    def test_root_must_be_new_nofollow_disjoint_child(self):
        with tempfile.TemporaryDirectory() as directory:
            temp = Path(directory)
            source = temp / 'source'
            source.mkdir()
            self.assertEqual(diag.checked_root(temp / 'probe', temp, [source]), temp / 'probe')
            for root in (temp, source, source / 'probe'):
                with self.subTest(root=root), self.assertRaises(ValueError):
                    diag.checked_root(root, temp, [source])
            linked = temp / 'linked'
            linked.symlink_to(source, target_is_directory=True)
            with self.assertRaises(OSError):
                diag.checked_root(linked / 'probe', temp, [])

    def test_expected_input_error_is_never_acceptance_or_zero_exit(self):
        missing = Path('/fixture/missing.zip')
        marker = 'Failed to create course object from `' + str(missing) + '` archive'
        self.assertEqual(diag.classify(1, False, [marker], missing, False, False),
                         'EXPECTED_INPUT_ERROR_NOT_ACCEPTANCE')
        for code, timeout, text, report, present in (
                (0, False, marker, False, False), (1, False, 'IDEA 帮助', False, False),
                (1, False, marker, True, False), (1, False, marker, False, True),
                (-15, False, marker, False, False), (1, True, marker, False, False)):
            result = diag.classify(code, timeout, [text], missing, report, present)
            self.assertNotEqual(result, 'EXPECTED_INPUT_ERROR_NOT_ACCEPTANCE')
        self.assertEqual(diag.OUTCOMES['EXPECTED_INPUT_ERROR_NOT_ACCEPTANCE'], 20)
        self.assertTrue(all(code != 0 for code in diag.OUTCOMES.values()))

    def test_stat_parsing_and_identity_changes(self):
        # 字段3–22；comm 内含空格与右括号也不能移位。
        values = ['S', '10', '20', '20'] + ['0'] * 15 + ['123456']
        identity = diag.parse_stat('21 (native launcher) helper) ' + ' '.join(values))
        self.assertEqual(identity['start'], 123456)
        self.assertEqual(identity['ppid'], 10)
        before = {'pid': 21, 'start': 123456, 'uid': 1000, 'session': 20, 'pgrp': 20}
        for key in before:
            altered = {**before, key: before[key] + 1}
            self.assertFalse(diag.same_owner(before, altered))
        self.assertTrue(diag.same_owner(before, dict(before)))

    def test_no_signal_when_pidfd_exited_or_identity_changed(self):
        identity = {'pid': 21, 'start': 123, 'uid': os.getuid(), 'session': 21, 'pgrp': 21}
        handle = diag.OwnedPid(identity, 991)
        with patch.object(diag.select, 'select', return_value=([991], [], [])), \
             patch.object(diag.signal, 'pidfd_send_signal') as send:
            handle.send(signal.SIGTERM, time.monotonic() + 3)
            send.assert_not_called()
        with patch.object(diag.select, 'select', return_value=([], [], [])), \
             patch.object(diag, 'proc_identity', return_value={**identity, 'start': 124}), \
             patch.object(diag.signal, 'pidfd_send_signal') as send:
            with self.assertRaises(ValueError):
                handle.send(signal.SIGTERM, time.monotonic() + 3)
            send.assert_not_called()

    def test_signal_uses_verified_pidfd_not_numeric_pid(self):
        identity = {'pid': 21, 'start': 123, 'uid': os.getuid(), 'session': 21, 'pgrp': 21}
        handle = diag.OwnedPid(identity, 991)
        with patch.object(diag.select, 'select', return_value=([], [], [])), \
             patch.object(diag, 'proc_identity', return_value=identity), \
             patch.object(diag.signal, 'pidfd_send_signal') as send:
            handle.send(signal.SIGTERM, time.monotonic() + 3)
            send.assert_called_once_with(991, signal.SIGTERM)

    def test_thread_dump_requires_fixed_direct_idea_jvm(self):
        idea = Path('/fixture/idea')
        child = Mock()
        child.handles = [Mock()]
        child.handles[0].current.return_value = {'pid': 42}
        with patch.object(diag.os, 'readlink', return_value=str(idea / 'bin/idea')), \
             patch.object(diag, 'read_regular', side_effect=[b'idea\0validateCourse\0',
                          b'map ' + str(idea / 'jbr/lib/server/libjvm.so').encode() + b'\n']):
            self.assertEqual(diag.checked_jvm(child, idea, time.monotonic() + 3), 42)
        child.proc.poll.assert_not_called()
        child.proc.wait.assert_not_called()
        for executable, command, maps in (
                ('/external/java', b'idea\0validateCourse\0', b''),
                (str(idea / 'bin/idea'), b'idea\0createCourse\0', b''),
                (str(idea / 'bin/idea'), b'idea\0validateCourse\0', b'foreign/libjvm.so\n')):
            with self.subTest(executable=executable, command=command), \
                 patch.object(diag.os, 'readlink', return_value=executable), \
                 patch.object(diag, 'read_regular', side_effect=[command, maps]), self.assertRaises(ValueError):
                diag.checked_jvm(child, idea, time.monotonic() + 3)

    def test_direct_python_child_has_owned_pidfd_and_can_be_stopped(self):
        # 唯一真实进程 fixture 是标准 Python sleep；没有进程压力/耗尽/攻击样例。
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            child = diag.Child([sys.executable, '-c', 'import time; time.sleep(10)'],
                               {'PATH': os.environ.get('PATH', '')}, root, root / 'out', root / 'err')
            try:
                self.assertTrue(child.alive())
                child.discover(time.monotonic() + 3)
                self.assertEqual(len(child.handles), 1)
                self.assertEqual(child.stop(time.monotonic() + 3), [])
                self.assertFalse(child.alive())
                self.assertEqual(child.proc.returncode, -signal.SIGTERM)
            finally:
                child.stop(time.monotonic() + 2)
                child.close()

    def test_xauthority_is_private_ephemeral_binary_not_summary(self):
        data = diag.xauthority_bytes()
        self.assertEqual(struct.unpack('!H', data[:2])[0], 65535)
        offset = 2
        fields = []
        for _ in range(4):
            size = struct.unpack('!H', data[offset:offset + 2])[0]
            offset += 2
            fields.append(data[offset:offset + size])
            offset += size
        self.assertEqual(fields[:3], [b'', b'', b'MIT-MAGIC-COOKIE-1'])
        self.assertEqual(len(fields[3]), 16)
        self.assertEqual(offset, len(data))
        with tempfile.TemporaryDirectory() as directory:
            probe = diag.Probe(Path(directory), {}, 180)
            self.assertNotIn(fields[3].hex(), json.dumps(probe.summary))

    def test_budget_and_fixed_nonacceptance_summary(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with patch.object(diag.time, 'monotonic', return_value=100):
                probe = diag.Probe(root, {}, 180)
            self.assertEqual(probe.deadline, 280)
            self.assertEqual(probe.cutoff, 265)
            self.assertEqual(probe.cleanup_deadline, 277)
            self.assertEqual(probe.summary['budget_kind'], 'COOPERATIVE_TARGET_NOT_HARD_REALTIME')
            self.assertEqual(probe.summary['workflow_step_timeout_seconds'], 240)
            self.assertFalse(probe.summary['filesystem_sandbox'])
            self.assertFalse(probe.summary['acceptance_pass'])
            self.assertFalse(probe.summary['release_allowed'])
            self.assertEqual(probe.summary['native_tests'], 'NOT_RUN')
            self.assertFalse(probe.summary['full_process_tree_exit_verified'])
            with patch.object(diag.time, 'monotonic', return_value=265), self.assertRaises(TimeoutError):
                probe.tick()
            with patch.object(diag.subprocess, 'Popen') as spawn:
                for seconds in (119, 181, 2700):
                    with self.assertRaises(ValueError):
                        diag.execute(Mock(seconds=seconds))
                spawn.assert_not_called()

    def test_tick_checks_again_after_discovery_consumes_budget(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            clock = [0]
            with patch.object(diag.time, 'monotonic', side_effect=lambda: clock[0]):
                probe = diag.Probe(root, {}, 180)
                child = Mock()
                child.discover.side_effect = lambda deadline: clock.__setitem__(0, 181)
                probe.children = [child]
                with self.assertRaises(TimeoutError):
                    probe.tick()
                child.discover.assert_called_once_with(165)

    def test_expired_stop_never_discovers_or_sends_signals(self):
        child = object.__new__(diag.Child)
        child.handles = [Mock()]
        child.discover = Mock()
        with patch.object(diag.time, 'monotonic', return_value=181):
            errors = child.stop(180)
        self.assertTrue(errors)
        child.discover.assert_not_called()
        child.handles[0].send.assert_not_called()

    def test_signal_refuses_deadline_crossed_during_identity_read(self):
        handle = diag.OwnedPid({'pid': 42}, 999)
        with patch.object(diag.time, 'monotonic', side_effect=[179, 181]), \
             patch.object(handle, 'current', return_value={'pid': 42}), \
             patch.object(diag.signal, 'pidfd_send_signal') as send:
            with self.assertRaises(TimeoutError):
                handle.send(signal.SIGTERM, 180)
            send.assert_not_called()

    def test_user_home_tmpdir_and_java_helpers_are_explicitly_directed(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            profile = root / 'diagnostic-profile'
            profile.mkdir()
            (profile / 'tmp').mkdir()
            options = profile / 'idea.vmoptions'
            options.write_text('-Xmx1536m\n-Duser.home=/old-fixture-home\n')
            original = {'HOME': '/old', 'TMPDIR': '/shared', 'DISPLAY': ':55', 'XAUTHORITY': '/outside'}
            with patch.object(diag, 'cli_environment', return_value=(original, profile)):
                env = diag.isolated_environment(root / 'idea', root / 'plugins', root)
            self.assertEqual(env['HOME'], str(root / 'home'))
            self.assertEqual(env['TMPDIR'], str(profile / 'tmp'))
            self.assertNotIn('DISPLAY', env)
            self.assertNotIn('XAUTHORITY', env)
            self.assertEqual(options.read_text().count('-Duser.home='), 1)
            self.assertIn('-Duser.home=' + str(root / 'home'), options.read_text())
            self.assertNotIn('/old-fixture-home', options.read_text())
            source = Path(diag.__file__).read_text()
            self.assertIn("'-J-Duser.home='", source)
            self.assertIn("'-J-Djava.io.tmpdir='", source)
            self.assertIn("'-Djava.io.tmpdir=' + self.env['TMPDIR']", source)

    def test_personal_or_self_hosted_runner_rejected_before_toolchain_reads(self):
        for env in ({}, {'GITHUB_ACTIONS': 'true', 'RUNNER_ENVIRONMENT': 'self-hosted'}):
            with patch.dict(diag.os.environ, env, clear=True), \
                 patch.object(diag, 'read_regular') as read, self.assertRaises(ValueError):
                diag.preflight(Path('/idea'), Path('/plugins'), Path('/root'))
            read.assert_not_called()

    def test_missing_jcmd_or_titles_is_honestly_reported_without_fallback(self):
        source = Path(diag.__file__).read_text()
        self.assertIn("'jcmd': jcmd if jcmd.is_file()", source)
        self.assertIn("'UNAVAILABLE_TOOL_MISSING'", source)
        self.assertNotIn("shutil.which('jcmd')", source)
        self.assertNotIn('SIGQUIT', source)
        self.assertNotIn('jstack', source)

    def test_no_external_inspection_input_or_security_bypass(self):
        source = Path(diag.__file__).read_text()
        tree = ast.parse(source)
        calls = [node.func.attr for node in ast.walk(tree) if isinstance(node, ast.Call)
                 and isinstance(node.func, ast.Attribute)]
        self.assertNotIn('kill', calls)
        self.assertNotIn('killpg', calls)
        self.assertNotIn('rglob', calls)
        self.assertNotIn("/ 'environ'", source)
        for forbidden in ('-Djava.awt.headless', 'jb.consents', 'eua.enabled', 'trust.all',
                          'VM.system_properties', 'VM.command_line', 'GC.heap_dump', "'-ac'"):
            self.assertNotIn(forbidden, source)
        helper = Path(diag.__file__).with_name('probes') / 'StartupScreen.java'
        java = helper.read_text()
        self.assertIn('createScreenCapture', java)
        for forbidden in ('mousePress', 'mouseMove', 'keyPress', 'Runtime.getRuntime', 'ProcessBuilder'):
            self.assertNotIn(forbidden, java)

    def test_workflow_is_disjoint_and_only_uploads_one_day_diagnostics(self):
        import yaml
        root = Path(__file__).resolve().parents[3]
        workflow = yaml.safe_load((root / '.github/workflows/academy-startup-diagnostic.yml').read_text())
        events = workflow.get('on', workflow.get(True))
        self.assertEqual(events['push']['branches'], ['academy-diagnostic/startup-probe'])
        self.assertEqual(set(events), {'push', 'workflow_dispatch'})
        self.assertEqual(workflow['permissions'], {'contents': 'read'})
        self.assertEqual(len(workflow['jobs']), 1)
        job = next(iter(workflow['jobs'].values()))
        steps = job['steps']
        self.assertEqual(job['timeout-minutes'], 18)
        self.assertGreaterEqual(job['timeout-minutes'], sum(step['timeout-minutes'] for step in steps) + 1)
        commands = '\n'.join(step.get('run', '') for step in steps)
        for forbidden in ('run_official.py', 'createCourse', 'release_gate.py', 'run_environment.py',
                          'check_source_ci.py', 'apt-get', 'npm ', 'docker '):
            self.assertNotIn(forbidden, commands)
        self.assertIn('--seconds 180', commands)
        upload = steps[-1]
        self.assertEqual(upload['with']['retention-days'], 1)
        self.assertTrue(upload['with']['path'].endswith('/evidence/'))
        self.assertNotIn('continue-on-error', str(steps))


if __name__ == '__main__':
    unittest.main()
