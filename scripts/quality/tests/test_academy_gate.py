"""Adversarial regression tests for the gate itself; no Gradle/IDE required."""
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
import zipfile

SPEC = importlib.util.spec_from_file_location('academy_gate', Path(__file__).resolve().parents[1] / 'academy_gate.py')
gate = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(gate)


class GateTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    def xml(self, text):
        folder = self.root / 'section/task/build/test-results/test'
        folder.mkdir(parents=True, exist_ok=True)
        (folder / 'TEST-Lab.xml').write_text(text)

    def results(self, expected_pass):
        return gate.collect_results(self.root, [{'path': 'section/task'}], 'test', expected_pass)

    def test_utf16_astral_prefix_and_multiple_spans(self):
        source = '//😀\nabc DEF xyz GHI'
        first = len('//😀\nabc '.encode('utf-16-le')) // 2
        second = len('//😀\nabc DEF xyz '.encode('utf-16-le')) // 2
        text, answers = gate.replace_placeholders(source, [
            {'offset': first, 'length': 3, 'placeholder_text': 'TODO'},
            {'offset': second, 'length': 3, 'placeholder_text': '?'},
        ])
        self.assertEqual('//😀\nabc TODO xyz ?', text)
        self.assertEqual(['DEF', 'GHI'], answers)

    def test_utf16_surrogate_split_rejected(self):
        with self.assertRaisesRegex(gate.GateError, 'surrogate'):
            gate.replace_placeholders('😀abc', [{'offset': 1, 'length': 1, 'placeholder_text': '?'}])

    def test_overlapping_spans_rejected(self):
        with self.assertRaises(gate.GateError):
            gate.replace_placeholders('abcdef', [
                {'offset': 0, 'length': 3, 'placeholder_text': '?'},
                {'offset': 2, 'length': 2, 'placeholder_text': '?'}])

    def test_negative_offset_and_boolean_length_rejected(self):
        for offset, length in [(-1, 1), (0, True), (0, 99), (False, 1)]:
            with self.subTest(offset=offset, length=length), self.assertRaises(gate.GateError):
                gate.replace_placeholders('abc', [{'offset': offset, 'length': length, 'placeholder_text': '?'}])

    def test_identity_placeholder_rejected(self):
        with self.assertRaises(gate.GateError):
            gate.replace_placeholders('abc', [{'offset': 0, 'length': 3, 'placeholder_text': 'abc'}])

    def test_noncanonical_and_escape_paths_rejected(self):
        for name in ('/etc/passwd', '../escape', 'x/../y', 'x//y', './x', 'x\\y', 'C:/x', ''):
            with self.subTest(name=name), self.assertRaises(gate.GateError):
                gate.relative_path(name)

    def test_symlink_asset_rejected(self):
        (self.root / 'real').write_text('real')
        (self.root / 'link').symlink_to(self.root / 'real')
        with self.assertRaises(gate.GateError):
            gate.local_file(self.root, 'link')

    def test_duplicate_yaml_keys_rejected(self):
        file = self.root / 'meta.yaml'
        file.write_text('type: edu\ntype: theory\n')
        with self.assertRaises(gate.GateError):
            gate.read_yaml(file)

    def test_no_xml_cannot_count_as_learner_rejection(self):
        with self.assertRaisesRegex(gate.GateError, 'no fresh JUnit XML'):
            self.results(False)

    def test_zero_and_skipped_tests_cannot_pass(self):
        for xml in ('<testsuite tests="0"/>', '<testsuite tests="1" skipped="1"/>',
                    '<testsuite tests="2" skipped="1" failures="1"/>'):
            with self.subTest(xml=xml):
                self.xml(xml)
                with self.assertRaises(gate.GateError):
                    self.results(False)

    def test_exact_expected_outcomes(self):
        self.xml('<testsuite tests="3" failures="1" errors="0" skipped="0"><testcase name="contract"><failure type="java.lang.AssertionError">bad answer</failure></testcase></testsuite>')
        self.assertEqual(1, self.results(False)[0]['failures'])
        with self.assertRaises(gate.GateError):
            self.results(True)
        self.xml('<testsuite tests="3" failures="0" errors="0" skipped="0"/>')
        self.assertEqual(3, self.results(True)[0]['tests'])
        with self.assertRaises(gate.GateError):
            self.results(False)

    def test_duplicate_zip_rejected(self):
        archive = self.root / 'duplicate.zip'
        import warnings
        with warnings.catch_warnings():
            warnings.simplefilter('ignore')
            with zipfile.ZipFile(archive, 'w') as z:
                z.writestr('file', 'abc')
                z.writestr('file', 'abc')
        with self.assertRaisesRegex(gate.GateError, 'duplicate'):
            gate.unpack_fixture(archive, self.root / 'import', {'file': gate.digest(b'abc')})

    def test_archive_corruption_rejected(self):
        archive = self.root / 'bad.zip'
        with zipfile.ZipFile(archive, 'w') as z:
            z.writestr('file', 'tampered')
        with self.assertRaisesRegex(gate.GateError, 'content mismatch'):
            gate.unpack_fixture(archive, self.root / 'import', {'file': gate.digest(b'original')})

    def test_archive_traversal_rejected_before_any_write(self):
        archive = self.root / 'bad.zip'
        with zipfile.ZipFile(archive, 'w') as z:
            z.writestr('../escape', 'x')
        with self.assertRaises(gate.GateError):
            gate.unpack_fixture(archive, self.root / 'import', {'../escape': gate.digest(b'x')})
        self.assertFalse((self.root / 'import').exists())

    def test_existing_import_destination_not_overwritten(self):
        with self.assertRaisesRegex(gate.GateError, 'overwrite'):
            gate.unpack_fixture(self.root / 'unused', self.root, {})

    def test_current_repository_metadata(self):
        roots = gate.discover(gate.REPO, [])
        self.assertGreaterEqual(len(roots), 10)
        count = sum(len(gate.inspect_course(root)['tasks']) for root in roots)
        self.assertGreaterEqual(count, 96)

    def test_missing_dependency_cannot_count_as_rejection(self):
        self.xml('<testsuite tests="1" errors="1"><testcase name="initializationError"><error type="java.lang.NoClassDefFoundError">missing dependency</error></testcase></testsuite>')
        with self.assertRaisesRegex(gate.GateError, 'infrastructure|initialization'):
            self.results(False)

    def test_container_start_failure_cannot_count_as_rejection(self):
        self.xml('<testsuite tests="1" failures="1"><testcase name="initializationError"><failure type="org.testcontainers.containers.ContainerLaunchException">cannot start</failure></testcase></testsuite>')
        with self.assertRaisesRegex(gate.GateError, 'infrastructure|initialization'):
            self.results(False)

    def test_wrapped_unimplemented_code_is_attributable(self):
        self.xml('<testsuite tests="1" failures="1"><testcase name="contract"><failure type="java.util.concurrent.ExecutionException">Caused by: java.lang.UnsupportedOperationException: TODO</failure></testcase></testsuite>')
        self.assertEqual(1, self.results(False)[0]['attributable_failures'])

    def test_rpc_unknown_cannot_borrow_a_server_todo_from_suite_output(self):
        self.xml('<testsuite tests="1" failures="1"><testcase name="rpc"><failure type="io.grpc.StatusRuntimeException">UNKNOWN</failure></testcase><system-err>java.lang.UnsupportedOperationException: 请按本步骤合同完成实现 at labs.distributed.grpc.Lab$TraceInterceptor.interceptCall</system-err></testsuite>')
        with self.assertRaisesRegex(gate.GateError, 'unclassified'):
            self.results(False)

    def test_rpc_failure_with_its_own_todo_cause_is_attributable(self):
        self.xml('<testsuite tests="1" failures="1"><testcase name="rpc"><failure type="io.grpc.StatusRuntimeException">UNKNOWN; Caused by: java.lang.UnsupportedOperationException: 请按本步骤合同完成实现</failure></testcase></testsuite>')
        self.assertEqual(1, self.results(False)[0]['attributable_failures'])

    def test_unclassified_failure_cannot_prove_rejection(self):
        self.xml('<testsuite tests="1" failures="1"><testcase name="contract"><failure type="unclassified.RunnerProblem">unknown</failure></testcase></testsuite>')
        with self.assertRaisesRegex(gate.GateError, 'unclassified failure'):
            self.results(False)

    def test_unrelated_unsupported_operation_is_not_todo(self):
        self.xml('<testsuite tests="1" failures="1"><testcase name="startsRuntime"><failure type="java.lang.UnsupportedOperationException">Platform does not support this process operation</failure></testcase></testsuite>')
        with self.assertRaisesRegex(gate.GateError, 'unclassified'):
            self.results(False)

    def test_mixed_todo_and_bind_failure_rejected(self):
        self.xml('<testsuite tests="2" failures="2"><testcase name="one"><failure type="java.lang.UnsupportedOperationException">TODO</failure></testcase><testcase name="two"><failure type="java.net.BindException">Address already in use</failure></testcase></testsuite>')
        with self.assertRaisesRegex(gate.GateError, 'infrastructure'):
            self.results(False)

    def test_mixed_todo_and_unknown_failure_rejected(self):
        self.xml('<testsuite tests="2" failures="2"><testcase name="one"><failure type="java.lang.UnsupportedOperationException">TODO</failure></testcase><testcase name="two"><failure type="unknown.InfrastructureFailure">unknown</failure></testcase></testsuite>')
        with self.assertRaisesRegex(gate.GateError, 'unclassified'):
            self.results(False)

    def test_legacy_validator_preserves_required_heading(self):
        import shutil
        repo = self.root / 'repo'
        source = gate.REPO / 'courses/java-foundations'
        copy = repo / 'courses/java-foundations'
        shutil.copytree(source, copy, ignore=shutil.ignore_patterns(*gate.IGNORED))
        file = copy / 'c00/01-workspace/lab/task.md'
        file.write_text(file.read_text().replace('## 面试问答与迁移', '## 自由笔记'))
        with self.assertRaisesRegex(gate.GateError, 'legacy validator failed'):
            gate.legacy_metadata(copy, repo)

    def test_integration_required_is_not_claimed_as_rejection(self):
        model = {'root': Path('/courses/redis-engineering'), 'tasks': [{'path': 'redis/04-consistency'}]}
        _, tasks, _, _ = gate.suite_plan(model, 'contract')
        self.assertIn('integration_required', tasks[0])
        folder = self.root / 'redis/04-consistency/build/test-results/unitTest'
        folder.mkdir(parents=True)
        (folder / 'TEST-Consistency.xml').write_text('<testsuite tests="3" failures="0"/>')
        result = gate.collect_results(self.root, tasks, 'unitTest', False)
        self.assertEqual('INTEGRATION_REQUIRED', result[0]['rejection_contract'])
        self.assertEqual(0, result[0]['attributable_failures'])

    def test_sigkill_cannot_count_as_learner_rejection(self):
        from types import SimpleNamespace
        from unittest.mock import patch
        args = SimpleNamespace(gradle=Path('/trusted/gradle'), suite='contract',
                               gradle_arg=[], offline=True, java_home=Path('/jdk21'),
                               gradle_user_home=None, timeout=2)
        model = {'root': Path('/courses/java-foundations'), 'tasks': [{'path': 'section/task'}]}
        with patch.object(gate.subprocess, 'Popen') as popen:
            popen.return_value.wait.return_value = -9
            with self.assertRaisesRegex(gate.GateError, 'unexpected Gradle exit -9'):
                gate.run_gradle(self.root, model, args, 'killed', self.root, False)

    def sample_course(self):
        source = gate.REPO / 'courses/java-concurrency'
        model = gate.inspect_course(source)
        archive = self.root / 'sample.zip'
        manifest = gate.pack_fixture(model, archive)
        dest = self.root / 'course'
        gate.unpack_fixture(archive, dest, manifest)
        return dest

    def test_concurrent_new_undeclared_asset_invalidates_roundtrip(self):
        from types import SimpleNamespace
        from unittest.mock import patch
        course = self.sample_course()
        model = gate.inspect_course(course)
        def changed(*args, **kwargs):
            (course / model['tasks'][0]['path'] / 'src/Added.java').write_text('class Added {}')
            return {'status': 'PASS'}
        with patch.object(gate, 'run_gradle', side_effect=changed):
            with self.assertRaisesRegex(gate.GateError, 'undeclared task asset'):
                gate.roundtrip(model, SimpleNamespace(work_dir=self.root / 'run'), {'course': 'fixture'})

    def test_missing_declared_asset_rejected(self):
        course = self.sample_course()
        (course / 'gradle/wrapper/gradle-wrapper.jar').unlink()
        with self.assertRaisesRegex(gate.GateError, 'missing declared asset'):
            gate.inspect_course(course)

    def test_hidden_public_test_rejected(self):
        course = self.sample_course()
        file = next(course.rglob('task-info.yaml'))
        file.write_text(file.read_text().replace('visible: true', 'visible: false', 1))
        with self.assertRaisesRegex(gate.GateError, 'must be visible'):
            gate.inspect_course(course)

    def test_undeclared_runtime_asset_rejected(self):
        course = self.sample_course()
        file = next(course.rglob('task-info.yaml'))
        (file.parent / 'missing-resource.txt').write_text('required at runtime')
        with self.assertRaisesRegex(gate.GateError, 'undeclared task asset'):
            gate.inspect_course(course)

    def test_reference_answer_visibility_is_required(self):
        course = self.sample_course()
        file = next(course.rglob('task-info.yaml'))
        (file.parent / 'task.md').write_text('No reference answer')
        for solution in (file.parent / 'solution').rglob('*.txt'):
            solution.write_text('No reference answer')
        with self.assertRaisesRegex(gate.GateError, 'reference segments missing'):
            gate.inspect_course(course)

    def test_integration_counts_only_explicit_integration_xml(self):
        self.xml('<testsuite tests="3" failures="1"/>')
        with self.assertRaisesRegex(gate.GateError, 'integration class XML missing'):
            gate.collect_results(self.root, [{'path': 'section/task', 'xml_classes': ['RealDatabaseTest']}], 'test', False)

    def test_repository_integration_scope_is_explicit(self):
        for name, expected in [('data-storage/mysql-engineering', 7), ('data-storage/redis-engineering', 7),
                               ('messaging', 12), ('distributed-systems', 4), ('java-frameworks', 1),
                               ('backend-capstone', 4)]:
            model = gate.inspect_course(gate.REPO / 'courses' / name)
            _, selected, _, outside = gate.suite_plan(model, 'integration')
            self.assertEqual(expected, len(selected))
            self.assertEqual(len(model['tasks']), len(selected) + len(outside))

    def test_failed_selection_writes_machine_report(self):
        from contextlib import redirect_stderr, redirect_stdout
        from io import StringIO
        report = self.root / 'report.json'
        stdout, stderr = StringIO(), StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            code = gate.main(['metadata', '--course', 'nonexistent', '--report', str(report)])
        self.assertEqual(1, code)
        self.assertIn(f'FAIL: {report}; native IDEA: NOT_RUN', stdout.getvalue())
        self.assertIn('nonexistent: FAIL:', stderr.getvalue())
        data = json.loads(report.read_text())
        self.assertEqual('FAIL', data['status'])
        self.assertEqual('NOT_RUN', data['native_idea'])


if __name__ == '__main__':
    unittest.main()
