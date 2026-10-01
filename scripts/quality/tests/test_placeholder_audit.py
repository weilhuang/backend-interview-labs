import importlib.util
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import placeholder_audit as audit
import academy_gate as gate


class PlaceholderAuditTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        file = self.root / 'source/task/src/Lab.java'
        file.parent.mkdir(parents=True)
        file.write_text('class Lab {}')
        self.task = {'path': 'task'}
        self.model = {'root': self.root / 'source', 'assets': ['task/src/Lab.java'],
                      'placeholders': {'task/src/Lab.java': [{'offset': 0, 'length': 5, 'placeholder_text': 'TODO'}]}}
        self.changed = {'file': 'task/src/Lab.java', 'index': 0}
        self.out = self.root / 'case'

    def tearDown(self):
        self.temp.cleanup()

    def mocked(self, xml, exit_code=1):
        calls = 0
        def run(command, **kwargs):
            nonlocal calls
            calls += 1
            if calls == 1:
                kwargs['log'].write_text('')
                return 0
            if xml is not None:
                reports = self.out / 'xml'
                reports.mkdir()
                (reports / 'TEST-junit-jupiter.xml').write_text(xml)
            summary = '\n'.join(f'[ 1 tests {k} ]' for k in ('found', 'started', 'failed')) + '\n' + '\n'.join(f'[ 0 tests {k} ]' for k in ('successful', 'skipped', 'aborted'))
            kwargs['log'].write_text(summary)
            return exit_code
        return run

    def case(self):
        return audit.run_case(self.model, self.task, Path('/jdk'), Path('/junit.jar'), self.out, self.changed)

    def test_console_error_todo_is_normalized_and_attributed(self):
        xml = '<testsuite tests="1" failures="0" errors="1"><testcase name="contract"><error type="java.lang.UnsupportedOperationException">TODO</error></testcase></testsuite>'
        with patch.object(audit, 'run_logged', side_effect=self.mocked(xml)):
            self.assertEqual('PASS', self.case()['status'])

    def test_dependency_error_cannot_count_as_rejection(self):
        xml = '<testsuite tests="1" failures="0" errors="1"><testcase name="ordinaryTest"><error type="java.lang.NoClassDefFoundError">missing</error></testcase></testsuite>'
        with patch.object(audit, 'run_logged', side_effect=self.mocked(xml)):
            with self.assertRaisesRegex(gate.GateError, 'infrastructure'):
                self.case()

    def test_unrelated_unsupported_operation_is_not_todo(self):
        xml = '<testsuite tests="1" failures="0" errors="1"><testcase name="startsRuntime"><error type="java.lang.UnsupportedOperationException">Platform does not support this process operation</error></testcase></testsuite>'
        with patch.object(audit, 'run_logged', side_effect=self.mocked(xml)):
            with self.assertRaisesRegex(gate.GateError, 'infrastructure'):
                self.case()

    def test_summary_without_xml_cannot_count_as_rejection(self):
        with patch.object(audit, 'run_logged', side_effect=self.mocked(None)):
            with self.assertRaisesRegex(gate.GateError, 'no fresh JUnit XML'):
                self.case()

    def test_signal_termination_cannot_count_as_rejection(self):
        xml = '<testsuite tests="1" failures="1" errors="0"><testcase name="contract"><failure type="java.lang.AssertionError">bad</failure></testcase></testsuite>'
        with patch.object(audit, 'run_logged', side_effect=self.mocked(xml, -9)):
            self.assertEqual('FAIL', self.case()['status'])


if __name__ == '__main__':
    unittest.main()
