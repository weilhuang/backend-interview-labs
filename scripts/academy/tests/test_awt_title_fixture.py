"""Mocked AWT/X11 fixtures and harmless Python child cleanup; no Java or Xvfb."""
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import unittest
from contextlib import ExitStack
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import awt_title_fixture as fixture
import modal_window
from display_diagnostic import encode


def runtime():
    return {'idea_version': fixture.IDEA_VERSION, 'idea_build': fixture.IDEA_BUILD,
            'idea_archive_sha256': fixture.IDEA_ARCHIVE_SHA256,
            'java_runtime_version': fixture.RUNTIME_VERSION,
            'hashes': {key: 'a' * 64 for key in fixture.HASH_NAMES}}


def cases():
    hashes = (*fixture.MODERN_HASHES, 'b' * 64, 'c' * 64, None)
    encodings = ('UTF8_STRING', 'UTF8_STRING', 'STRING', 'COMPOUND_TEXT', None)
    return [{'case': name, 'status': 'REJECTED' if i == 4 else 'PASS',
             'title_sha256': hashes[i], 'title_encoding': encodings[i]}
            for i, name in enumerate(fixture.CASE_NAMES)]


def report():
    from test_awt_modal_fixture import modal_cases
    return {'schema': fixture.SCHEMA, 'status': 'PASS', 'kind': fixture.KIND, 'cases': cases(),
            'modal_cases': modal_cases(),
            'cleanup': {'jvm': 'REAPED', 'xvfb': 'REAPED'}, 'error': None, 'diagnosis': None,
            'exit_codes': {'jvm': -15, 'xvfb': -15}, 'precheck_failure': None,
            'runtime': runtime(), 'run_id': '123', 'run_attempt': '2', 'tested_sha': 'd' * 40,
            'elapsed_milliseconds': 123}


class TypedReport(unittest.TestCase):
    def test_pass_is_closed_detached_and_bounded(self):
        value = report()
        projected = fixture.report_document(value)
        self.assertEqual(projected, value)
        self.assertLessEqual(len(encode(projected)), 8192)
        value['runtime']['hashes']['java_sha256'] = 'e' * 64
        value['cases'][0]['title_sha256'] = 'e' * 64
        self.assertNotEqual(projected, value)

    def test_all_cases_live_runtime_and_both_reaps_required(self):
        changes = ({'cases': cases()[:-1]}, {'runtime': None}, {'error': 'CANCELLED'},
                   {'cleanup': {'jvm': 'NOT_STARTED', 'xvfb': 'REAPED'}},
                   {'runtime': {**runtime(), 'java_runtime_version': None}})
        for update in changes:
            with self.subTest(update=update), self.assertRaises(ValueError):
                fixture.report_document({**report(), **update})

    def test_rejects_private_values_unknown_fields_and_wrong_types(self):
        changes = ({'schema': True}, {'elapsed_milliseconds': True}, {'elapsed_milliseconds': 60001},
                   {'run_id': {'private': 'value'}}, {'run_attempt': '0'}, {'tested_sha': 'x' * 40},
                   {'status': ['PASS']}, {'kind': ['private']}, {'error': {'message': 'private'}},
                   {'environment': {'private': 'value'}}, {'cleanup': {'jvm': 'REAPED', 'xvfb': 'REAPED', 'pid': 1}},
                   {'runtime': {**runtime(), 'binary_path': '/private/path'}},
                   {'runtime': {**runtime(), 'java_runtime_version': 'PRIVATE_RUNTIME'}},
                   {'runtime': {**runtime(), 'hashes': {**runtime()['hashes'], 'java_sha256': {'private': 'value'}}}},
                   {'exit_codes': {'jvm': True, 'xvfb': 0}},
                   {'exit_codes': {'jvm': None, 'xvfb': 0}},
                   {'exit_codes': {'jvm': -129, 'xvfb': 0}},
                   {'exit_codes': {'jvm': 256, 'xvfb': 0}},
                   {'exit_codes': {'jvm': {'message': 'private'}, 'xvfb': 0}},
                   {'diagnosis': {'message': 'PRIVATE_TITLE'}},
                   {'cases': [{'case': 'PRIVATE_TITLE', 'status': 'PASS', 'title_sha256': 'a' * 64}]})
        for update in changes:
            with self.subTest(update=update), self.assertRaises(ValueError):
                fixture.report_document({**report(), **update})

    def test_case_order_modern_hashes_and_legacy_identity_enforced(self):
        wrong = cases()
        wrong[2]['title_sha256'] = fixture.MODERN_HASHES[0]
        for value in (list(reversed(cases())), cases() * 2, wrong,
                      [{**cases()[0], 'title_sha256': 'a' * 64}],
                      [{**cases()[0], 'status': 'REJECTED'}]):
            with self.subTest(value=value), self.assertRaises(ValueError):
                fixture.report_document({**report(), 'cases': value})

    def test_precheck_failure_has_no_false_runtime_or_cases(self):
        value = {**report(), 'status': 'FAIL', 'cases': [], 'modal_cases': [], 'runtime': None,
                 'cleanup': {'jvm': 'NOT_STARTED', 'xvfb': 'NOT_STARTED'},
                 'exit_codes': {'jvm': None, 'xvfb': None}, 'error': 'PRECHECK_UNAVAILABLE',
                 'precheck_failure': {'step': 'PRODUCT_READ', 'reason': 'MISSING',
                     'exception_class': 'FileNotFoundError', 'facts': {}}}
        self.assertEqual(fixture.report_document(value), value)
        with self.assertRaises(ValueError):
            fixture.report_document({**value, 'cases': cases()[:1]})

    def test_cleanup_failure_cannot_masquerade_as_other_error(self):
        value = {**report(), 'status': 'FAIL', 'cleanup': {'jvm': 'UNVERIFIED', 'xvfb': 'REAPED'},
                 'error': 'CLEANUP_UNVERIFIED'}
        self.assertEqual(fixture.report_document(value), value)
        with self.assertRaises(ValueError):
            fixture.report_document({**value, 'error': 'CANCELLED'})

    def test_typed_diagnosis_never_serializes_exception_text(self):
        value = {**report(), 'status': 'FAIL', 'error': 'PROBE_FAILED', 'cases': [], 'modal_cases': [],
                 'diagnosis': modal_window.failure_from_exception(ValueError('PRIVATE_TITLE_OR_PATH'))}
        self.assertNotIn(b'PRIVATE_TITLE_OR_PATH', encode(fixture.report_document(value)))


class RuntimeIdentity(unittest.TestCase):
    def create_tree(self, folder):
        root = folder / 'toolchain'
        for relative, raw in {
                'idea/product-info.json': json.dumps({'version': fixture.IDEA_VERSION, 'buildNumber': fixture.IDEA_BUILD}).encode(),
                'idea/jbr/release': b'JAVA_VERSION="25.0.4"\n',
                'idea/jbr/bin/java': b'fixture-java-no-execution',
                'idea/jbr/lib/server/libjvm.so': b'fixture-jvm',
                'idea/jbr/lib/libawt_xawt.so': b'fixture-awt'}.items():
            path = root / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(raw)
        (root / 'idea/jbr/bin/java').chmod(0o700)
        return root

    def test_pinned_identity_hashes_without_claiming_live_verification(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = self.create_tree(Path(tmp))
            with patch.dict(os.environ, {'RUNNER_TEMP': tmp, 'TOOLCHAIN_DIR': str(root)}):
                java, identity = fixture._runtime_identity(root)
            self.assertEqual(java, root / 'idea/jbr/bin/java')
            self.assertIsNone(identity['java_runtime_version'])
            self.assertEqual(set(identity['hashes']), set(fixture.HASH_NAMES))
            self.assertNotIn(str(root), json.dumps(identity))

    def test_rejects_other_toolchain_bad_product_and_unexpected_release(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = self.create_tree(Path(tmp))
            with patch.dict(os.environ, {'RUNNER_TEMP': tmp, 'TOOLCHAIN_DIR': str(root)}):
                with self.assertRaises(ValueError):
                    fixture._runtime_identity(Path(tmp))
                (root / 'idea/product-info.json').write_text('{"version":"other","buildNumber":"other"}')
                with self.assertRaises(ValueError):
                    fixture._runtime_identity(root)
                (root / 'idea/product-info.json').write_text(json.dumps({'version': fixture.IDEA_VERSION, 'buildNumber': fixture.IDEA_BUILD}))
                (root / 'idea/jbr/release').write_bytes(b'JAVA_VERSION="99"\n')
                with self.assertRaises(ValueError):
                    fixture._runtime_identity(root)

    def test_bounded_hash_rejects_symlink_and_oversize(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'file'
            path.write_bytes(b'12345')
            with self.assertRaises(ValueError):
                fixture._hash_file(path, 4)
            link = Path(tmp) / 'link'
            link.symlink_to(path)
            with self.assertRaises(OSError):
                fixture._hash_file(link, 10)


class NativeFunction:
    def __init__(self, body):
        self.body = body
    def __call__(self, *args):
        return self.body(*args)


class FakeX11:
    def __init__(self, display, deadline):
        self.connection, self.x = 1, self
        self.deleted, self.destroyed, self.read = [], [], []
        self.legacy_missing = False
        self.duplicates = False
        self.synthetic_accepts = False
        self.metadata_format, self.metadata_items, self.metadata_bytes, self.metadata_code = 8, 0, 32, 0
        self.metadata_type = None
        self.XDeleteProperty = NativeFunction(lambda connection, window, atom: self.deleted.append(window) or 1)
        self.XCreateSimpleWindow = NativeFunction(lambda *args: 300)
        self.XChangeProperty = NativeFunction(lambda *args: 1)
        self.XDestroyWindow = NativeFunction(lambda connection, window: self.destroyed.append(window) or 1)
        self.XInternAtom = NativeFunction(lambda *args: 1)
        self.XGetWindowProperty = NativeFunction(self.metadata)
        self.XFree = NativeFunction(lambda *args: 1)
    def __enter__(self):
        return self
    def __exit__(self, *args):
        pass
    def sync(self):
        pass
    def _title_type_atoms(self):
        return {b'STRING': 11, b'UTF8_STRING': 12, b'COMPOUND_TEXT': 13}
    def metadata(self, connection, window, atom, offset, length, delete, expected,
                 actual, fmt, count, remaining, data):
        assert length == 0 and not delete and window in self.deleted
        actual._obj.value = self.metadata_type if self.metadata_type is not None else (11 if window == 101 else 13)
        fmt._obj.value, count._obj.value = self.metadata_format, self.metadata_items
        remaining._obj.value = self.metadata_bytes
        return self.metadata_code
    def root(self):
        return 10
    def tree(self, root, cap):
        assert cap == modal_window.MAX_ROOT_CHILDREN
        return 10, 0, [101, 102, 999]
    def property(self, window, *args):
        return 1234 if window != 999 else 9999
    def title(self, window):
        self.read.append(window)
        if window == 300:
            if self.synthetic_accepts:
                return 'a' * 64
            raise modal_window.ProofError(call_site='X_PROPERTY_TYPE', facts={'property_name': 2, 'actual_type': 1, 'type_matches': 0})
        if window in self.deleted:
            return None if self.legacy_missing else ('b' if window == 101 else 'c') * 64
        return fixture.MODERN_HASHES[0 if window == 101 or self.duplicates else 1]
    def attributes(self, window, root):
        return {'pid': self.property(window), 'title_sha256': self.title(window), 'map_state': 2, 'window_class': 1}


class ProbeFixtures(unittest.TestCase):
    def run_probe(self, **changes):
        x = FakeX11(fixture.DISPLAY, 1)
        for key, value in changes.items():
            setattr(x, key, value)
        with patch.dict(os.environ, {'DISPLAY': fixture.DISPLAY}), patch.object(modal_window, '_X11', return_value=x):
            result = fixture._probe(1234)
        return x, result

    def test_calls_production_selector_and_mutates_only_exact_child_titles(self):
        x, result = self.run_probe()
        self.assertEqual(result['status'], 'PASS')
        self.assertEqual(result['cases'], cases())
        self.assertEqual(x.deleted, [101, 102])
        self.assertEqual(x.destroyed, [300])
        self.assertNotIn(999, x.read)

    def test_duplicate_title_ownership_fails_before_mutation(self):
        x, result = self.run_probe(duplicates=True)
        self.assertEqual(result['status'], 'FAIL')
        self.assertEqual(x.deleted, [])
        self.assertEqual(result['cases'], [])

    def test_missing_genuine_legacy_title_is_not_passed(self):
        x, result = self.run_probe(legacy_missing=True)
        self.assertEqual(result['status'], 'FAIL')
        self.assertEqual(len(result['cases']), 2)
        self.assertEqual(x.deleted, [101])

    def test_wrong_type_must_be_rejected_and_synthetic_window_destroyed(self):
        x, result = self.run_probe(synthetic_accepts=True)
        self.assertEqual(result['status'], 'FAIL')
        self.assertEqual(len(result['cases']), 4)
        self.assertEqual(x.destroyed, [300])

    def test_legacy_encoding_comes_from_bounded_metadata_not_caption(self):
        x, result = self.run_probe(metadata_type=12)
        self.assertEqual(result['status'], 'PASS')
        self.assertEqual([case['title_encoding'] for case in result['cases'][2:4]], ['UTF8_STRING', 'UTF8_STRING'])

    def test_bad_legacy_metadata_is_not_accepted(self):
        for change in ({'metadata_type': 999}, {'metadata_format': 32}, {'metadata_items': 1},
                       {'metadata_bytes': 0}, {'metadata_bytes': 1025}, {'metadata_code': 1}):
            with self.subTest(change=change):
                x, result = self.run_probe(**change)
                self.assertEqual(result['status'], 'FAIL')
                self.assertEqual(len(result['cases']), 2)


class Child:
    def __init__(self, pid):
        self.pid, self.returncode = pid, None
        self.stdin, self.stdout, self.stderr = None, None, None
        self.wait_calls = []
    def poll(self):
        return self.returncode
    def wait(self, timeout):
        self.wait_calls.append(timeout)
        self.returncode = -15
        return self.returncode
    def terminate(self):
        pass
    def kill(self):
        pass


class CoordinatorLifecycle(unittest.TestCase):
    def execute(self, *, failure=None, ready_failure=None, pidfd_failure=False, cleanup_failure=False,
                expired_budget=False, probe_results=None):
        from test_awt_modal_fixture import modal_response
        server, jvm = Child(101), Child(102)
        result = {'schema': 1, 'status': 'PASS', 'cases': cases(), 'diagnosis': None}
        if probe_results is None:
            probe_results = [subprocess.CompletedProcess([], 0, encode(result)),
                             *(subprocess.CompletedProcess([], 0, encode(modal_response(action, jvm.pid)))
                               for action in fixture.MODAL_ACTIONS)]
        identity = runtime()
        identity['java_runtime_version'] = None
        with tempfile.TemporaryDirectory() as tmp, ExitStack() as stack:
            output = Path(tmp) / 'report.json'
            env = {'GITHUB_RUN_ID': '123', 'GITHUB_RUN_ATTEMPT': '2', 'GITHUB_SHA': 'd' * 40}
            stack.enter_context(patch.dict(os.environ, env))
            stack.enter_context(patch.object(fixture, '_runtime_identity', return_value=(Path('/verified/idea/jbr/bin/java'), identity)))
            stack.enter_context(patch.object(fixture, 'BINARY', Mock(is_file=lambda: True, is_symlink=lambda: False)))
            stack.enter_context(patch.object(fixture, '_wait_xvfb'))
            stack.enter_context(patch.object(fixture, '_ready', side_effect=ready_failure))
            popen = stack.enter_context(patch.object(fixture.subprocess, 'Popen', side_effect=[server, jvm]))
            run = stack.enter_context(patch.object(fixture.subprocess, 'run',
                                                   side_effect=failure if failure is not None else probe_results))
            stack.enter_context(patch.object(fixture.os, 'pidfd_open', side_effect=OSError('private') if pidfd_failure else [201, 202]))
            stack.enter_context(patch.object(fixture.os, 'close'))
            sends = stack.enter_context(patch.object(fixture.signal, 'pidfd_send_signal'))
            stack.enter_context(patch.object(fixture.signal, 'alarm'))
            stack.enter_context(patch.object(fixture.signal, 'signal'))
            if expired_budget:
                stack.enter_context(patch.object(fixture, '_remaining', side_effect=TimeoutError('private budget')))
                stack.enter_context(patch.object(fixture.time, 'monotonic', side_effect=[0, 41, 41]))
            if cleanup_failure:
                jvm.wait = Mock(side_effect=OSError('private cleanup failure'))
            failed = False
            try:
                fixture.main(Path('/verified'), output)
            except SystemExit as error:
                self.assertEqual(error.code, 1)
                failed = True
            value = json.loads(output.read_bytes())
            fixture.report_document(value)
            return value, failed, server, jvm, popen, run, sends

    def test_pass_only_after_both_children_reaped_and_private_env(self):
        value, failed, server, jvm, popen, run, sends = self.execute()
        self.assertFalse(failed)
        self.assertEqual(value['status'], 'PASS')
        self.assertEqual(value['cleanup'], {'jvm': 'REAPED', 'xvfb': 'REAPED'})
        self.assertEqual(value['exit_codes'], {'jvm': -15, 'xvfb': -15})
        self.assertEqual(server.wait_calls, [2])
        self.assertEqual(jvm.wait_calls, [2])
        self.assertEqual([c.args[0] for c in sends.call_args_list], [202, 201])
        xvfb_args, java_args = [call.args[0] for call in popen.call_args_list]
        self.assertIn('-nolisten', xvfb_args)
        self.assertIn('-auth', xvfb_args)
        self.assertEqual(java_args[0], '/verified/idea/jbr/bin/java')
        self.assertIn('-Xmx64m', java_args)
        self.assertIn('-XX:ActiveProcessorCount=2', java_args)
        self.assertIn(str(fixture.HELPER), java_args)
        for call in popen.call_args_list:
            self.assertEqual(call.kwargs['env']['DISPLAY'], fixture.DISPLAY)
            self.assertNotIn('JAVA_TOOL_OPTIONS', call.kwargs['env'])
            self.assertEqual(call.kwargs['stderr'], subprocess.DEVNULL)
        self.assertLessEqual(run.call_args.kwargs['timeout'], 2)

    def test_probe_timeout_and_cancellation_reap_both(self):
        for error, expected in ((subprocess.TimeoutExpired('private', 2), 'PROBE_TIMEOUT'),
                                (InterruptedError('private cancellation'), 'CANCELLED')):
            with self.subTest(error=error):
                value, failed, server, jvm, *_ = self.execute(failure=error)
                self.assertTrue(failed)
                self.assertEqual(value['error'], expected)
                self.assertEqual(value['cleanup'], {'jvm': 'REAPED', 'xvfb': 'REAPED'})
                self.assertNotIn('private', json.dumps(value))

    def test_jvm_start_failure_is_typed_and_cleans_both(self):
        value, failed, *_ = self.execute(ready_failure=ValueError('private startup output'))
        self.assertTrue(failed)
        self.assertEqual(value['error'], 'JVM_START_UNAVAILABLE')
        self.assertIsNone(value['runtime']['java_runtime_version'])
        self.assertEqual(value['cleanup'], {'jvm': 'REAPED', 'xvfb': 'REAPED'})

    def test_pidfd_failure_still_reaps_the_spawned_server(self):
        value, failed, server, jvm, popen, *_ = self.execute(pidfd_failure=True)
        self.assertTrue(failed)
        self.assertEqual(value['cleanup'], {'jvm': 'NOT_STARTED', 'xvfb': 'REAPED'})
        self.assertEqual(value['exit_codes'], {'jvm': None, 'xvfb': -15})
        self.assertEqual(popen.call_count, 1)
        self.assertEqual(server.wait_calls, [2])

    def test_jvm_cleanup_failure_still_reaps_xvfb_and_prevents_pass(self):
        value, failed, server, *_ = self.execute(cleanup_failure=True)
        self.assertTrue(failed)
        self.assertEqual(value['error'], 'CLEANUP_UNVERIFIED')
        self.assertEqual(value['cleanup'], {'jvm': 'UNVERIFIED', 'xvfb': 'REAPED'})
        self.assertEqual(value['exit_codes'], {'jvm': None, 'xvfb': -15})
        self.assertEqual(server.wait_calls, [2])

    def test_total_activity_budget_failure_cleans_both_without_probe(self):
        value, failed, server, jvm, popen, run, sends = self.execute(expired_budget=True)
        self.assertTrue(failed)
        self.assertEqual(value['error'], 'BUDGET_EXHAUSTED')
        self.assertEqual(value['elapsed_milliseconds'], 41000)
        self.assertEqual(value['cleanup'], {'jvm': 'REAPED', 'xvfb': 'REAPED'})
        run.assert_not_called()


class ReadyHandshake(unittest.TestCase):
    def read(self, chunks, *, exited=False, timed_out=False):
        jvm, server = Child(100), Child(101)
        jvm.stdout = Mock()
        jvm.stdout.fileno.return_value = 200
        if exited:
            jvm.returncode = 2
        with ExitStack() as stack:
            stack.enter_context(patch.object(fixture.os, 'set_blocking'))
            stack.enter_context(patch.object(fixture.os, 'read', side_effect=chunks))
            stack.enter_context(patch.object(fixture.select, 'select', return_value=([jvm.stdout], [], [])))
            if timed_out:
                stack.enter_context(patch.object(fixture.time, 'monotonic', side_effect=[0, 21]))
                stack.enter_context(patch.object(fixture, '_remaining', return_value=20))
            fixture._ready(jvm, server, float('inf'))

    def test_live_exact_version_marker_can_arrive_in_fragments(self):
        marker = ('AWT_TITLE_FIXTURE_READY:' + fixture.RUNTIME_VERSION + '\n').encode('ascii')
        self.read([marker[:10], marker[10:]])

    def test_unexpected_output_eof_or_exited_jvm_fails(self):
        for chunks, exited in (([b'PRIVATE_STDOUT'], False), ([b''], False), ([], True)):
            with self.subTest(chunks=chunks, exited=exited), self.assertRaises(ValueError):
                self.read(chunks, exited=exited)

    def test_readiness_wait_has_fixed_upper_bound(self):
        with self.assertRaises(TimeoutError):
            self.read([], timed_out=True)


class Reaping(unittest.TestCase):
    def test_exact_child_kill_after_term_timeout_is_bounded(self):
        child = Child(100)
        def wait(timeout):
            child.wait_calls.append(timeout)
            if len(child.wait_calls) == 1:
                raise subprocess.TimeoutExpired('owned child', timeout)
            child.returncode = -9
        child.wait = wait
        with patch.object(fixture.signal, 'pidfd_send_signal') as sends:
            self.assertEqual(fixture._reap(child, 200), 'REAPED')
        self.assertEqual([c.args for c in sends.call_args_list], [(200, signal.SIGTERM), (200, signal.SIGKILL)])
        self.assertEqual(child.wait_calls, [2, 2])

    def test_exit_between_poll_and_signal_is_still_reaped(self):
        child = Child(100)
        with patch.object(fixture.signal, 'pidfd_send_signal', side_effect=ProcessLookupError):
            self.assertEqual(fixture._reap(child, 200), 'REAPED')
        self.assertEqual(child.wait_calls, [2])

    def test_failed_wait_after_kill_is_never_claimed_reaped(self):
        child = Child(100)
        child.wait = Mock(side_effect=subprocess.TimeoutExpired('owned child', 2))
        with patch.object(fixture.signal, 'pidfd_send_signal') as sends:
            self.assertEqual(fixture._reap(child, 200), 'UNVERIFIED')
        self.assertEqual(child.wait.call_count, 2)
        self.assertEqual([c.args for c in sends.call_args_list], [(200, signal.SIGTERM), (200, signal.SIGKILL)])

    @unittest.skipUnless(hasattr(os, 'pidfd_open') and hasattr(signal, 'pidfd_send_signal'), 'Linux pidfd required')
    def test_nonprivileged_python_child_is_reaped(self):
        child = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(30)'],
                                 stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        descriptor = None
        try:
            descriptor = os.pidfd_open(child.pid)
            self.assertEqual(fixture._reap(child, descriptor), 'REAPED')
            self.assertIsNotNone(child.returncode)
            with self.assertRaises(ChildProcessError):
                os.waitpid(child.pid, os.WNOHANG)
        finally:
            if child.poll() is None:
                child.kill()
                child.wait(timeout=2)
            if descriptor is not None:
                os.close(descriptor)


if __name__ == '__main__':
    unittest.main()
