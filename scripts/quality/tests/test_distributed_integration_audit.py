"""Audit fail-closed regression tests. These synthetic reports are not Docker evidence."""
import copy
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import xml.etree.ElementTree as ET

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import distributed_integration_audit as audit
from academy_gate import GateError, inspect_course


class DistributedIntegrationAuditTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.model = inspect_course(audit.REPO / audit.COURSE)
        cls.cases = audit.plan(cls.model)

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.case = self.cases[0]

    def tearDown(self):
        self.temp.cleanup()

    def xml(self, changed=True, case=None):
        case = case or self.case
        root = ET.Element('testsuite', name=case['test_class'], tests=str(len(case['test_cases'])),
                          failures='1' if changed else '0', errors='0', skipped='0')
        for name in case['test_cases']:
            child = ET.SubElement(root, 'testcase', name=name, classname=case['test_class'])
            if changed and name == case['rejecting_test']:
                failure = ET.SubElement(child, 'failure', type='java.lang.UnsupportedOperationException')
                failure.text = ('java.lang.UnsupportedOperationException: ' + audit.TODO + '\n\tat ' +
                                case['owner'] + '.' + case['method'] + '(' + Path(case['file']).name +
                                ':' + str(case['todo_line']) + ')')
        return root

    def write(self, root, case=None):
        case = case or self.case
        folder = self.root / case['task'] / 'build/test-results/test'
        folder.mkdir(parents=True, exist_ok=True)
        path = folder / ('TEST-' + case['test_class'] + '.xml')
        ET.ElementTree(root).write(path, encoding='utf-8')
        return path

    def check(self, changed=True, code=None, case=None):
        return audit.validate_xml(self.root, case or self.case, changed, (1 if changed else 0) if code is None else code)

    def test_plan_uses_current_file_local_yaml_regions(self):
        self.assertEqual([('DS-17', 0), ('DS-19', 1), ('DS-21', 0), ('DS-22', 1)],
                         [(c['region'], c['index_zero_based']) for c in self.cases])
        for case in self.cases:
            ph = self.model['placeholders'][case['file']][case['index_zero_based']]
            self.assertEqual(ph['offset'], case['offset_utf16'])
            self.assertEqual(ph['length'], case['length_utf16'])
            self.assertNotEqual(case['source_sha256'], case['learner_sha256'])

    def test_plan_rejects_shifted_region_meaning(self):
        model = copy.deepcopy(self.model)
        ph = model['placeholders'][self.case['file']][0]
        ph['offset'] = 0
        with self.assertRaisesRegex(GateError, 'no longer matches'):
            audit.plan(model)

    def test_reference_requires_all_expected_tests(self):
        self.write(self.xml(False))
        self.assertEqual(0, self.check(False)['counts']['failures'])

    def test_each_exact_todo_is_accepted(self):
        for case in self.cases:
            with self.subTest(region=case['region']):
                self.write(self.xml(case=case), case)
                self.assertEqual(1, len(self.check(case=case)['attributed']))

    def test_publish_lambda_assertthrows_wrapper_is_attributed(self):
        case = self.cases[1]
        root = self.xml(case=case)
        failure = root.find('.//failure')
        failure.set('type', 'org.opentest4j.AssertionFailedError')
        failure.set('message', 'Unexpected exception type thrown, expected: <java.lang.IllegalStateException> but was: <java.lang.UnsupportedOperationException>')
        failure.text = failure.text.replace('.publishOne(', '.lambda$publishOne$1(')
        self.write(root, case)
        self.assertEqual(1, len(self.check(case=case)['attributed']))

    def test_missing_xml_and_compile_failure_are_not_rejection(self):
        with self.assertRaisesRegex(GateError, 'missing'):
            self.check()

    def test_successful_mutant_and_abnormal_process_exit_rejected(self):
        self.write(self.xml())
        for code in (0, 2, -9):
            with self.subTest(code=code), self.assertRaisesRegex(GateError, 'Gradle exit'):
                self.check(code=code)

    def test_zero_testcase_xml_rejected(self):
        root = self.xml(False)
        for child in list(root):
            root.remove(child)
        root.set('tests', '0')
        self.write(root)
        with self.assertRaisesRegex(GateError, 'zero'):
            self.check(False)

    def test_missing_and_duplicate_testcases_rejected(self):
        for duplicate in (False, True):
            root = self.xml()
            root.remove(root.findall('testcase')[1])
            if duplicate:
                root.append(copy.deepcopy(root.find('testcase')))
            self.write(root)
            with self.subTest(duplicate=duplicate), self.assertRaises(GateError):
                self.check()

    def test_skipped_test_even_with_false_counter_rejected(self):
        root = self.xml()
        ET.SubElement(root.findall('testcase')[1], 'skipped')
        self.write(root)
        with self.assertRaisesRegex(GateError, 'skipped'):
            self.check()

    def test_junit_error_is_not_todo_rejection(self):
        root = self.xml()
        root.set('failures', '0')
        root.set('errors', '1')
        root.find('.//failure').tag = 'error'
        self.write(root)
        with self.assertRaisesRegex(GateError, 'infrastructure'):
            self.check()

    def test_environment_failure_cannot_inherit_todo(self):
        root = self.xml()
        root.find('.//failure').text += '\nCaused by: org.testcontainers.containers.ContainerLaunchException: setup failed'
        self.write(root)
        with self.assertRaisesRegex(GateError, 'infrastructure'):
            self.check()

    def test_other_region_and_wrong_source_line_are_not_attributed(self):
        for old, new in [(self.case['owner'], 'labs.distributed.transactions.Saga'),
                         (str(self.case['todo_line']) + ')', str(self.case['todo_line'] + 1) + ')'),
                         (audit.TODO, 'unsupported runtime operation')]:
            root = self.xml()
            root.find('.//failure').text = root.find('.//failure').text.replace(old, new)
            self.write(root)
            with self.subTest(new=new), self.assertRaises(GateError):
                self.check()

    def test_unrelated_assertion_or_runtime_exception_cannot_inherit_todo(self):
        for kind in ('org.opentest4j.AssertionFailedError', 'org.opentest4j.MultipleFailuresError', 'java.lang.IllegalStateException'):
            root = self.xml()
            root.find('.//failure').set('type', kind)
            self.write(root)
            with self.subTest(kind=kind), self.assertRaisesRegex(GateError, 'expected direct TODO'):
                self.check()

    def test_failure_in_other_test_rejected(self):
        root = self.xml()
        first, second = root.findall('testcase')
        failure = first.find('failure')
        first.remove(failure)
        second.append(failure)
        self.write(root)
        with self.assertRaisesRegex(GateError, 'unrelated test'):
            self.check()

    def test_unexpected_class_xml_rejected(self):
        file = self.write(self.xml())
        file.with_name('TEST-other.xml').write_text('<testsuite/>')
        with self.assertRaisesRegex(GateError, 'unexpected integration class'):
            self.check()

    def test_inconsistent_failure_count_rejected(self):
        root = self.xml()
        root.set('failures', '2')
        self.write(root)
        with self.assertRaisesRegex(GateError, 'failure count'):
            self.check()

    def test_fixture_drift_rejected(self):
        file = self.root / 'Lab.java'
        file.write_text('reference')
        manifest = {'Lab.java': audit.digest(file.read_bytes())}
        audit.verify_inputs(self.root, manifest)
        file.write_text('other change')
        with self.assertRaisesRegex(GateError, 'source drift'):
            audit.verify_inputs(self.root, manifest)

    def test_each_staged_case_changes_only_its_declared_region(self):
        archive = self.root / 'fixture.zip'
        manifest = audit.pack_fixture(self.model, archive)
        versions = audit.REPO / 'infra/versions.env'
        args = SimpleNamespace(gradle=None, offline=True, java_home=Path('/unit-test-jdk'),
                               gradle_user_home=None, timeout=30, total_timeout=30, budget=audit.ExecutionBudget(30))
        for case in self.cases:
            def synthetic_process(command, cwd, env, log, timeout):
                audit.verify_inputs(cwd, manifest, case)
                self.assertIn(':' + case['module'] + ':test', command)
                self.assertIn('--no-build-cache', command)
                self.assertIn('--rerun-tasks', command)
                folder = cwd / case['task'] / 'build/test-results/test'
                folder.mkdir(parents=True)
                ET.ElementTree(self.xml(case=case)).write(folder / ('TEST-' + case['test_class'] + '.xml'))
                for source_set, owner in [('main', case['owner']), ('integrationTest', case['test_class'])]:
                    file = cwd / case['task'] / 'build/classes/java' / source_set / (owner.replace('.', '/') + '.class')
                    file.parent.mkdir(parents=True)
                    file.write_bytes(b'synthetic unit-test fixture, not compiled evidence')
                return 1
            with self.subTest(region=case['region']), patch.object(audit, 'run_process', side_effect=synthetic_process):
                result = audit.run_case(self.model, archive, manifest, versions, args, case, True,
                                        self.root / case['region'])
                self.assertEqual('PASS', result['status'])
                self.assertEqual(2, len(result['compiled_class_sha256']))
        audit.verify_inputs(self.model['root'], manifest)

    def test_timeout_is_not_rejection(self):
        with patch.object(audit, 'run_logged', side_effect=audit.subprocess.TimeoutExpired(['gradle'], 30)):
            with self.assertRaisesRegex(GateError, 'never accepted'):
                audit.run_process(['gradle'], self.root, {}, self.root / 'timeout.log', 30)

    def test_prepare_never_launches_process_and_reports_not_run(self):
        work, report = self.root / 'work', self.root / 'report.json'
        with patch.object(audit.subprocess, 'run', side_effect=AssertionError('process launched')), \
             patch.object(audit.subprocess, 'Popen', side_effect=AssertionError('process launched')):
            self.assertEqual(2, audit.main(['--work-dir', str(work), '--report', str(report)]))
        import json
        saved = json.loads(report.read_text())
        self.assertEqual('NOT_RUN', saved['status'])
        self.assertEqual('NOT_RUN', saved['docker_integration'])
        self.assertEqual([], saved['mutation_runs'])
        self.assertEqual(4, len(saved['regions']))

    def test_existing_work_directory_is_not_reused(self):
        report = self.root / 'report.json'
        self.assertEqual(1, audit.main(['--work-dir', str(self.root), '--report', str(report)]))

    def test_docker_preflight_failure_starts_no_gradle(self):
        work, report = self.root / 'work', self.root / 'report.json'
        with patch.object(audit.subprocess, 'run', side_effect=[
                SimpleNamespace(returncode=0, stdout='openjdk version "21.0.1"', stderr=''),
                SimpleNamespace(returncode=1, stdout='', stderr='Docker unavailable')]), \
             patch.object(audit.subprocess, 'Popen', side_effect=AssertionError('Gradle launched')):
            self.assertEqual(1, audit.main(['--execute', '--work-dir', str(work), '--report', str(report)]))
        import json
        saved = json.loads(report.read_text())
        self.assertEqual('FAIL', saved['status'])
        self.assertEqual('NOT_RUN', saved['docker_integration'])
        self.assertEqual([], saved['mutation_runs'])

    def test_rejected_report_paths_preserve_bytes_and_start_nothing(self):
        course = self.root / 'repo' / audit.COURSE
        course.mkdir(parents=True)
        protected = course / 'Lab.java'
        protected.write_text('must remain unchanged')
        existing = self.root / 'existing.json'
        existing.write_text('old report')
        alias = self.root / 'alias.json'
        alias.symlink_to(protected)
        for target in (protected, existing, alias, course / 'new.java'):
            with self.subTest(target=target), patch.object(audit.subprocess, 'run', side_effect=AssertionError('process started')):
                self.assertEqual(1, audit.main(['--repo', str(self.root / 'repo'), '--execute',
                                               '--work-dir', str(self.root / 'work'), '--report', str(target)]))
        self.assertEqual('must remain unchanged', protected.read_text())
        self.assertEqual('old report', existing.read_text())
        self.assertFalse((course / 'new.java').exists())
        self.assertFalse((self.root / 'work').exists())

    def test_suppressed_sql_cleanup_cannot_borrow_todo(self):
        root = self.xml()
        root.find('.//failure').text += '\nSuppressed: java.sql.SQLNonTransientConnectionException: Connection is closed during rollback'
        self.write(root)
        with self.assertRaisesRegex(GateError, 'suppressed'):
            self.check()

    def test_unrelated_cause_cannot_borrow_todo(self):
        root = self.xml()
        root.find('.//failure').text += '\nCaused by: java.net.SocketTimeoutException: timed out'
        self.write(root)
        with self.assertRaisesRegex(GateError, 'nested'):
            self.check()

    def test_total_budget_caps_next_case_and_reserves_cleanup(self):
        with patch.object(audit.time, 'monotonic', return_value=100) as now:
            budget = audit.ExecutionBudget(900)
            self.assertEqual(300, budget.allowance(300, 'first', reserve=15))
            now.return_value = 790
            self.assertEqual(210, budget.allowance(300, 'last', reserve=15))
            now.return_value = 990
            with self.assertRaisesRegex(GateError, 'budget exhausted'):
                budget.allowance(300, 'next', reserve=15)

    def test_total_budget_expiry_stops_sequence_and_preserves_log(self):
        work, report = self.root / 'work', self.root / 'report.json'
        def one_run(model, archive, manifest, versions, args, case, changed, location):
            location.mkdir()
            (location / 'gradle.log').write_text('saved output before total deadline')
            args.budget.deadline = audit.time.monotonic() - 1
            return {'status': 'PASS'}
        with patch.object(audit.subprocess, 'run', side_effect=[
                SimpleNamespace(returncode=0, stdout='openjdk version "21.0.1"', stderr=''),
                SimpleNamespace(returncode=0, stdout='27.0.0', stderr='')]), \
             patch.object(audit, 'run_case', side_effect=one_run) as run:
            self.assertEqual(1, audit.main(['--execute', '--work-dir', str(work), '--report', str(report)]))
        self.assertEqual(1, run.call_count)
        import json
        saved = json.loads(report.read_text())
        self.assertEqual('FAIL', saved['runtime']['status'])
        self.assertEqual(1, saved['runtime']['completed_runs'])
        self.assertEqual([], saved['mutation_runs'])
        self.assertEqual('saved output before total deadline', Path(saved['reference_runs'][0]['log']).read_text())

    def test_disabled_ryuk_starts_no_java_or_docker(self):
        with patch.dict(audit.os.environ, {'TESTCONTAINERS_RYUK_DISABLED': 'true'}), \
             patch.object(audit.subprocess, 'run', side_effect=AssertionError('process started')):
            self.assertEqual(1, audit.main(['--execute', '--work-dir', str(self.root / 'work'),
                                           '--report', str(self.root / 'report.json')]))

    def test_commit_controls_delete_only_one_statement_in_same_yaml_region(self):
        controls = audit.commit_controls(self.model, self.cases)
        self.assertEqual(2, len(controls))
        for case in controls:
            original = (self.model['root'] / case['file']).read_text()
            mutated = audit.learner_source(self.model, case)
            self.assertEqual(original.replace(case['omitted_statement'], '', 1), mutated)
            self.assertEqual(case['learner_sha256'], audit.digest(mutated.encode()))
            self.assertEqual(0, case['index_zero_based'])

    def semantic_xml(self, case):
        root = self.xml(False, case)
        root.set('failures', '1')
        target = next(c for c in root.findall('testcase') if c.get('name') == case['rejecting_test'])
        failure = ET.SubElement(target, 'failure', type='org.opentest4j.MultipleFailuresError')
        failure.text = ('org.opentest4j.MultipleFailuresError: Multiple Failures (1 failure)\n'
                        + 'Suppressed: org.opentest4j.AssertionFailedError: ' + case['assertion_message']
                        + ' ==> expected: <0> but was: <1>\n'
                        + 'at labs.distributed.MySqlTransactionTest.lambda$' + case['rejecting_test'].removesuffix('()')
                        + '$0(MySqlTransactionTest.java:'
                        + str(case['assertion_line']) + ')')
        return root

    def test_commit_controls_require_exact_normal_branch_assertion(self):
        for case in audit.commit_controls(self.model, self.cases):
            root = self.semantic_xml(case)
            self.write(root, case)
            self.assertEqual(1, len(self.check(case=case)['attributed']))
            root.find('.//failure').text += '\nSuppressed: java.sql.SQLException: rollback failed'
            self.write(root, case)
            with self.assertRaisesRegex(GateError, 'nested or cleanup'):
                self.check(case=case)

    def real_commit_xml(self):
        # Sanitized run 36776413515 evidence: only logs/properties/host/timing
        # metadata removed. Exact failure attributes and stack are retained.
        fixture = Path(__file__).parent / 'fixtures/distributed-xa-omit-ra-gradle.xml'
        return ET.parse(fixture).getroot()

    def test_real_gradle_commit_failure_with_app_loader_and_repeated_cause(self):
        case = audit.commit_controls(self.model, self.cases)[0]
        self.assertEqual(52, case['assertion_line'], 'review the recorded XML if the assertion moves')
        self.write(self.real_commit_xml(), case)
        result = self.check(case=case)
        self.assertEqual(1, result['counts']['failures'])
        self.assertEqual([{'test': case['rejecting_test'], 'type': 'org.opentest4j.MultipleFailuresError',
                           'assertion_line': 52}], result['attributed'])

    def test_real_commit_trace_rejects_wrong_branch_frame_or_nested_runtime(self):
        case = audit.commit_controls(self.model, self.cases)[0]
        for corruption in ('cause branch', 'cause line', 'cause owner', 'cause method',
                           'suppressed line', 'extra sql', 'extra assertion', 'extra todo',
                           'two failures', 'duplicate failure tag'):
            root = self.real_commit_xml()
            failure = root.find('.//failure')
            before, cause = failure.text.split('\nCaused by: ', 1)
            if corruption == 'cause branch':
                cause = cause.replace('转出分支未完成', '转入分支未完成')
            elif corruption == 'cause line':
                cause = cause.replace('MySqlTransactionTest.java:52', 'MySqlTransactionTest.java:53')
            elif corruption == 'cause owner':
                cause = cause.replace('labs.distributed.MySqlTransactionTest.lambda$', 'labs.distributed.OtherTest.lambda$')
            elif corruption == 'cause method':
                cause = cause.replace('lambda$两个MySQL资源准备后无决策回滚有决策提交$', 'lambda$unrelated$')
            elif corruption == 'suppressed line':
                before = before.replace('MySqlTransactionTest.java:52', 'MySqlTransactionTest.java:53')
            elif corruption == 'extra sql':
                cause += '\nCaused by: java.sql.SQLException: cleanup failed'
            elif corruption == 'extra assertion':
                cause += '\nSuppressed: org.opentest4j.AssertionFailedError: unrelated'
            elif corruption == 'extra todo':
                cause += '\nSuppressed: java.lang.UnsupportedOperationException: TODO'
            elif corruption == 'two failures':
                before = before.replace('Multiple Failures (1 failure)', 'Multiple Failures (2 failures)')
            else:
                target = next(c for c in root.findall('testcase') if c.find('failure') is not None)
                target.append(copy.deepcopy(failure))
                root.set('failures', '2')
            failure.text = before + '\nCaused by: ' + cause
            self.write(root, case)
            with self.subTest(corruption=corruption), self.assertRaises(GateError):
                self.check(case=case)

    def test_real_commit_failure_cannot_be_assigned_to_opposite_branch_or_other_test(self):
        outbound, inbound = audit.commit_controls(self.model, self.cases)
        self.write(self.real_commit_xml(), inbound)
        with self.assertRaises(GateError):
            self.check(case=inbound)
        for attribute, value in [('name', 'unrelated()'), ('classname', 'labs.distributed.OtherTest')]:
            root = self.real_commit_xml()
            target = next(c for c in root.findall('testcase') if c.find('failure') is not None)
            target.set(attribute, value)
            self.write(root, outbound)
            with self.subTest(attribute=attribute), self.assertRaises(GateError):
                self.check(case=outbound)

    def test_normal_xa_assertions_precede_application_recovery(self):
        path = audit.REPO / audit.COURSE / audit.BASE / '06-transactions/integration-test/labs/distributed/MySqlTransactionTest.java'
        source = path.read_text()
        start = source.index('transfer("xa_normal", 20, false, false)')
        scan_a = source.index('preparedBranches(Images.database(first)', start)
        scan_b = source.index('preparedBranches(Images.database(second)', start)
        balance_a = source.index('assertEquals(50, a.scalar', start)
        balance_b = source.index('assertEquals(150, b.scalar', start)
        recovery = source.index('normalRecovered.recover', start)
        self.assertLess(scan_a, balance_a)
        self.assertLess(scan_b, balance_a)
        self.assertLess(balance_a, recovery)
        self.assertLess(balance_b, recovery)
        self.assertIn('transfer("xa_abort", 30, true, false)', source)
        self.assertIn('transfer("xa_commit", 30, false, true)', source)
        self.assertEqual(2, source.count('Images.restartAndAwait('))


if __name__ == '__main__':
    unittest.main()
