"""Small text fixtures for diagnostics; imported bytes remain strictly gated."""
import json
from pathlib import Path
import sys
import tempfile
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from wrapper_diagnostic import compare_wrapper, sha, RELATIVE
from gates import inspect_import, GateError, dump
from collect_evidence import collect

SOURCE = ('distributionBase=GRADLE_USER_HOME\ndistributionPath=wrapper/dists\n'
          'distributionUrl=https\\://services.gradle.org/distributions/gradle-8.10.2-bin.zip\n'
          'distributionSha256Sum=' + 'a' * 64 + '\nnetworkTimeout=10000\n'
          'validateDistributionUrl=true\nzipStoreBase=GRADLE_USER_HOME\nzipStorePath=wrapper/dists\n')


class WrapperDiagnosticTests(unittest.TestCase):
    def fixtures(self, root, actual):
        author, student = root/'author', root/'student'
        for path, text in [(author/RELATIVE, SOURCE), (student/RELATIVE, actual)]:
            path.parent.mkdir(parents=True)
            path.write_bytes(text.encode())
        return author, student

    def test_order_comments_and_crlf_are_visible_but_do_not_pass_byte_gate(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            actual='# timestamp\r\n'+'\r\n'.join(reversed(SOURCE.splitlines()))+'\r\n'
            author,student=self.fixtures(root,actual)
            result=compare_wrapper(author,student)
            self.assertEqual(result['status'],'UNVERIFIED_DIAGNOSTIC')
            self.assertFalse(result['byte_equal'])
            self.assertTrue(result['all_eight_fields_present_and_equal'])
            for key in ('key_order','comments','crlf'):
                self.assertTrue(result['format_changes'][key])
            contract={'files':{RELATIVE:{'learner_sha256':sha(SOURCE.encode())}}}
            with self.assertRaises(GateError):inspect_import(student,contract,'student')

    def test_missing_checksum_and_changed_version_are_not_equal(self):
        for actual in (SOURCE.replace('distributionSha256Sum='+'a'*64+'\n',''),
                       SOURCE.replace('gradle-8.10.2-bin.zip','gradle-8.11-bin.zip')):
            with tempfile.TemporaryDirectory() as directory:
                result=compare_wrapper(*self.fixtures(Path(directory),actual))
                self.assertFalse(result['all_eight_fields_present_and_equal'])

    def test_unexpected_url_credentials_and_unknown_values_not_disclosed(self):
        actual=SOURCE.replace('https\\://services.gradle.org/distributions/gradle-8.10.2-bin.zip',
                              'https://alice:PRIVATE_VALUE@example.invalid/package.zip?token=PRIVATE_VALUE')
        actual+='extraKey=PRIVATE_VALUE\n'
        with tempfile.TemporaryDirectory() as directory:
            result=compare_wrapper(*self.fixtures(Path(directory),actual))
            self.assertNotIn('PRIVATE_VALUE',json.dumps(result))
            self.assertIn('extraKey',result['actual']['unknown_keys'])
            self.assertFalse(result['fields']['distributionUrl']['equal'])

    def test_duplicate_and_unsupported_syntax_are_unparseable(self):
        for actual in (SOURCE+'networkTimeout=20000\n',SOURCE+'continuation=one\\\n two\n'):
            with tempfile.TemporaryDirectory() as directory:
                result=compare_wrapper(*self.fixtures(Path(directory),actual))
                self.assertEqual(result['status'],'UNAVAILABLE_OR_UNPARSEABLE')
                self.assertNotIn('fields',result)
                self.assertIn('sha256',result['actual'])

    def test_missing_file_is_unavailable_and_size_is_bounded(self):
        with tempfile.TemporaryDirectory() as directory:
            author,student=self.fixtures(Path(directory),SOURCE)
            (student/RELATIVE).unlink()
            self.assertEqual(compare_wrapper(author,student)['status'],'UNAVAILABLE_OR_UNPARSEABLE')
            (student/RELATIVE).write_text('x'*8193)
            self.assertEqual(compare_wrapper(author,student)['status'],'UNAVAILABLE_OR_UNPARSEABLE')

    def test_report_is_persisted_and_collected_on_import_failure(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);run=root/'run';(run/'evidence').mkdir(parents=True)
            author,student=self.fixtures(run,SOURCE.replace('networkTimeout=10000','networkTimeout=9000'))
            report=compare_wrapper(author,student)
            path=run/'evidence/student-wrapper-diagnostic.json';dump(path,report)
            with self.assertRaises(GateError):inspect_import(student,{'files':{RELATIVE:{'learner_sha256':sha(SOURCE.encode())}}},'student')
            collect(run,root/'artifact')
            saved=json.loads((root/'artifact/student-wrapper-diagnostic.json').read_text())
            self.assertEqual(saved['status'],'UNVERIFIED_DIAGNOSTIC')
            self.assertFalse(saved['fields']['networkTimeout']['equal'])


if __name__ == '__main__':
    unittest.main()
