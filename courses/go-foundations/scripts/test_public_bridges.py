"""公开桥验证器的普通回归；不执行 Java、Go 或网络。"""
from pathlib import Path
import copy
import importlib.util
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET

SCRIPT = Path(__file__).with_name('verify_public_bridges.py')
spec = importlib.util.spec_from_file_location('public_bridge_validator', SCRIPT)
bridge = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bridge)


def lessons():
    return [{'id': key, 'slug': value[0], 'variants': sorted(value[1]), 'mutants': sorted(value[2])}
            for key, value in bridge.EXPECTED.items()]


def scenarios(key):
    _, variants, mutants = bridge.EXPECTED[key]
    return [('starter', 'BUSINESS_RED', ''), ('missing-go', 'ENVIRONMENT_REJECTED', ''),
            ('syntax-error', 'COMPILE_REJECTED', '')] + [
        ('answer-' + value + '.go', 'CORRECT', '') for value in variants] + [
        ('mutant-' + value + '.go', 'BUSINESS_RED', '') for value in mutants]


class ValidatorTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def xml(self, failure_target=None, failure_type='java.lang.AssertionError', failure_text='GREETING: wrong'):
        suite = ET.Element('testsuite')
        for classname, name in sorted(bridge.EXPECTED_JUNIT):
            case = ET.SubElement(suite, 'testcase', classname=classname, name=name)
            if (classname, name) == failure_target:
                ET.SubElement(case, 'failure', type=failure_type, message=failure_text).text = failure_text
        ET.ElementTree(suite).write(self.root / 'TEST-junit-jupiter.xml')
        return suite

    def save(self, suite):
        ET.ElementTree(suite).write(self.root / 'TEST-junit-jupiter.xml')

    def test_exact_inventory_and_scenarios(self):
        bridge.validate_inventory(lessons())
        for key in bridge.EXPECTED:
            bridge.validate_scenarios(key, scenarios(key))

    def test_missing_lesson_rejected(self):
        with self.assertRaises(ValueError):
            bridge.validate_inventory(lessons()[:-1])

    def test_duplicate_lesson_rejected(self):
        value = lessons()
        value[-1] = copy.deepcopy(value[0])
        with self.assertRaises(ValueError):
            bridge.validate_inventory(value)

    def test_duplicate_wrong_inventory_rejected(self):
        value = lessons()
        value[0]['mutants'][1] = value[0]['mutants'][0]
        with self.assertRaises(ValueError):
            bridge.validate_inventory(value)

    def test_duplicate_wrong_scenario_rejected(self):
        value = scenarios('C13-01')
        value[-1] = value[-2]
        with self.assertRaises(ValueError):
            bridge.validate_scenarios('C13-01', value)

    def test_wrong_scenario_classification_rejected(self):
        value = scenarios('C13-01')
        value[0] = ('starter', 'CORRECT', '')
        with self.assertRaises(ValueError):
            bridge.validate_scenarios('C13-01', value)

    def test_exact_correct_junit_suite(self):
        self.xml()
        _, failures = bridge.validate_junit(self.root, 'CORRECT')
        self.assertEqual(failures, 0)

    def test_wrong_suite_rejected(self):
        suite = self.xml()
        suite[0].set('classname', 'UnrelatedTest')
        self.save(suite)
        with self.assertRaises(ValueError):
            bridge.validate_junit(self.root, 'CORRECT')

    def test_duplicate_method_rejected(self):
        suite = self.xml()
        suite[2].attrib.update(suite[1].attrib)
        self.save(suite)
        with self.assertRaises(ValueError):
            bridge.validate_junit(self.root, 'CORRECT')

    def test_exact_business_failure_accepted(self):
        self.xml(bridge.CONTRACT_TEST)
        _, failures = bridge.validate_junit(self.root, 'BUSINESS_RED')
        self.assertEqual(failures, 1)

    def test_wrong_failure_target_rejected(self):
        self.xml(('GoTestBridgeTest', 'rejectsFalseGreen()'))
        with self.assertRaises(ValueError):
            bridge.validate_junit(self.root, 'BUSINESS_RED')

    def test_infra_failure_type_rejected(self):
        self.xml(bridge.CONTRACT_TEST, 'java.lang.IllegalStateException')
        with self.assertRaises(ValueError):
            bridge.validate_junit(self.root, 'BUSINESS_RED')

    def test_infra_marker_rejected(self):
        self.xml(bridge.CONTRACT_TEST, failure_text='GREETING: INVALID_ENV')
        with self.assertRaises(ValueError):
            bridge.validate_junit(self.root, 'BUSINESS_RED')

    def test_skip_and_error_rejected(self):
        for node in ('skipped', 'error'):
            with self.subTest(node=node):
                suite = self.xml(bridge.CONTRACT_TEST)
                ET.SubElement(suite[1], node)
                self.save(suite)
                with self.assertRaises(ValueError):
                    bridge.validate_junit(self.root, 'BUSINESS_RED')

    def test_expected_missing_go_error_is_classified_as_environment(self):
        suite = self.xml()
        case = next(c for c in suite if c.get('classname') == 'GoContractTest')
        ET.SubElement(case, 'error', type='java.lang.IllegalStateException', message='INVALID_ENV: missing Go')
        suite.set('errors', '1')
        self.save(suite)
        _, failures = bridge.validate_junit(self.root, 'ENVIRONMENT_REJECTED')
        self.assertEqual(failures, 1)
        with self.assertRaises(ValueError):
            bridge.validate_junit(self.root, 'BUSINESS_RED')

    def test_wrong_environment_error_rejected(self):
        for target, exception, message in [
            ('GoTestBridgeTest', 'java.lang.IllegalStateException', 'INVALID_ENV'),
            ('GoContractTest', 'java.lang.NullPointerException', 'INVALID_ENV'),
            ('GoContractTest', 'java.lang.IllegalStateException', 'unrelated'),
            ('GoContractTest', 'java.lang.IllegalStateException', 'prefix INVALID_ENV: fake'),
            ('GoContractTest', 'java.lang.IllegalStateException', 'INVALID_ENV without colon')]:
            with self.subTest(target=target, exception=exception, message=message):
                suite = self.xml()
                case = next(c for c in suite if c.get('classname') == target)
                ET.SubElement(case, 'error', type=exception, message=message)
                suite.set('errors', '1')
                self.save(suite)
                with self.assertRaises(ValueError):
                    bridge.validate_junit(self.root, 'ENVIRONMENT_REJECTED')

    def test_extra_environment_error_rejected(self):
        suite = self.xml()
        for case in suite[:2]:
            ET.SubElement(case, 'error', type='java.lang.IllegalStateException', message='INVALID_ENV')
        suite.set('errors', '2')
        self.save(suite)
        with self.assertRaises(ValueError):
            bridge.validate_junit(self.root, 'ENVIRONMENT_REJECTED')

    def test_failure_cannot_replace_expected_environment_error(self):
        self.xml(bridge.CONTRACT_TEST, 'java.lang.IllegalStateException', 'INVALID_ENV: missing Go')
        with self.assertRaises(ValueError):
            bridge.validate_junit(self.root, 'ENVIRONMENT_REJECTED')

    def test_environment_fail_plus_error_rejected(self):
        suite = self.xml(bridge.CONTRACT_TEST)
        case = next(c for c in suite if c.get('classname') == 'GoContractTest')
        ET.SubElement(case, 'error', type='java.lang.IllegalStateException', message='INVALID_ENV: missing Go')
        suite.set('errors', '1')
        self.save(suite)
        with self.assertRaises(ValueError):
            bridge.validate_junit(self.root, 'ENVIRONMENT_REJECTED')

    def test_exact_compile_failure_and_wrong_error(self):
        self.xml(bridge.CONTRACT_TEST, failure_text='compiler feedback [build failed]')
        bridge.validate_junit(self.root, 'COMPILE_REJECTED')
        suite = self.xml(bridge.CONTRACT_TEST, failure_text='compiler feedback [build failed]')
        problem = suite.find('testcase/failure')
        problem.tag = 'error'
        suite.set('errors', '1')
        self.save(suite)
        with self.assertRaises(ValueError):
            bridge.validate_junit(self.root, 'COMPILE_REJECTED')

    def test_old_xml_removed_and_cannot_pass_without_fresh_suite(self):
        self.xml()
        bridge.prepare_xml_dir(self.root)
        self.assertEqual(list(self.root.iterdir()), [])
        with self.assertRaises(ValueError):
            bridge.validate_junit(self.root, 'CORRECT')

    def test_optimization_rejected_with_failed_evidence(self):
        script = self.root / 'scripts/verify_public_bridges.py'
        script.parent.mkdir()
        shutil.copyfile(SCRIPT, script)
        process = subprocess.run([sys.executable, '-O', str(script)], capture_output=True, timeout=10)
        self.assertEqual(process.returncode, 2)
        evidence = json.loads((self.root / 'evidence/bridge-ci/final-summary.json').read_text())
        self.assertEqual(evidence['status'], 'FAILED')
        self.assertIn('OPTIMIZATION_FORBIDDEN', evidence['failure'])
        self.assertEqual(evidence['scenarios'], 0)


if __name__ == '__main__':
    unittest.main(verbosity=2)
