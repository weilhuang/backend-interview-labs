"""Public evidence regression tests: Python fixtures only, never Java or Docker."""
from pathlib import Path
import hashlib
import importlib.util
import json
import os
import struct
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
import xml.etree.ElementTree as ET
import zlib

ROOT = Path(__file__).resolve().parents[3]
SCRIPT = ROOT / 'scripts/ci/collect_evidence.py'
# Do not collide with scripts/academy/collect_evidence.py and its shared sanitizer.
SPEC = importlib.util.spec_from_file_location('public_ci_collect_evidence_under_test', SCRIPT)
collector = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = collector
SPEC.loader.exec_module(collector)

COURSES = {
    'java-pilot': ('java-recovery-collections', 'java-recovery-collections'),
    'java-foundations': ('java-foundations', 'java-foundations'),
    'java-concurrency': ('java-concurrency', 'java-concurrency'),
    'java-jvm': ('java-jvm', 'java-jvm'),
    'java-frameworks-backend': ('java-frameworks', 'java-frameworks'),
    'java-frameworks-ui': ('java-frameworks', None),
    'mysql': ('data-storage/mysql-engineering', 'mysql'),
    'redis': ('data-storage/redis-engineering', 'redis'),
    'messaging': ('messaging', 'messaging'),
    'distributed': ('distributed-systems', 'distributed-systems'),
    'backend-capstone': ('backend-capstone', 'backend-capstone'),
    'lab-environment': ('java-recovery-collections', None),
}
CI_NAMES = {
    'ci-plan': {'build/ci/plan.json'},
    'ci-static': {'build/ci/docs.json', 'build/quality/academy-metadata.json',
                  'build/quality/academy-legacy-metadata.json', 'build/ci/public-course.json'},
    'ci-result': {'build/ci/evidence.json'},
}


def chunk(kind, payload):
    return struct.pack('>I', len(payload)) + kind + payload + struct.pack('>I', zlib.crc32(kind + payload) & 0xffffffff)


def png(metadata=True):
    header = chunk(b'IHDR', struct.pack('>IIBBBBB', 1, 1, 8, 2, 0, 0, 0))
    pixels = chunk(b'IDAT', zlib.compress(b'\x00\x11\x22\x33'))
    extras = b''
    if metadata:
        extras = b''.join(chunk(kind, b'private-token=/home/alice/.config/session')
                          for kind in (b'tEXt', b'iTXt', b'zTXt', b'eXIf', b'tIME'))
    return b'\x89PNG\r\n\x1a\n' + header + extras + pixels + chunk(b'IEND', b'')


class EvidenceFixtures(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.repo = self.root / 'repo'
        self.repo.mkdir()
        self.counter = 0

    def write(self, relative, content):
        path = self.repo / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content if isinstance(content, bytes) else content.encode())
        return path

    def collect(self, profile='ci-plan', status='failure'):
        self.counter += 1
        self.output = self.root / f'output-{self.counter}'
        result = collector.collect(self.repo, self.output, profile, status)
        self.assertEqual(json.loads((self.output / 'collection.json').read_text()), result)
        self.assertEqual(result['bytes'], sum(item['bytes'] for item in result['copied']))
        for item in result['copied']:
            uploaded = (self.output / item['path']).read_bytes()
            self.assertEqual(len(uploaded), item['bytes'])
            self.assertEqual(hashlib.sha256(uploaded).hexdigest(), item['uploaded_sha256'])
        return result

    def test_exact_profile_inventory_and_ci_filenames(self):
        self.assertEqual(collector.COURSES, COURSES)
        candidates = set().union(*CI_NAMES.values()) | {
            'build/ci/secret.json', 'build/ci/plan.json.bak', 'build/ci/private/plan.json',
            'build/quality/report.json', 'build/ci/.env', 'build/ci/source.java'}
        for profile, expected in CI_NAMES.items():
            actual = {name for name in candidates if collector.allowed(profile, name)}
            self.assertEqual(actual, expected)
            for name in expected:
                self.assertEqual(collector.allowed(profile, name), 'json')

    def test_course_and_quality_producer_names_are_scoped(self):
        for profile, (course, key) in COURSES.items():
            with self.subTest(profile=profile):
                prefix = f'courses/{course}/'
                self.assertEqual(collector.allowed(profile, prefix + 'build/verification/report.json'), None if profile == 'java-frameworks-ui' else 'json')
                self.assertEqual(collector.allowed(profile, prefix + 'module/build/test-results/test/TEST-Example$Nested.xml'), None if profile == 'java-frameworks-ui' else 'xml')
                for name in ('arbitrary-report.json', 'private.json', 'report.json.bak'):
                    self.assertIsNone(collector.allowed(profile, prefix + 'authoring/' + name))
                self.assertIsNone(collector.allowed(profile, 'courses/unrelated/build/verification/report.json'))
                if key:
                    base = 'build/quality/' + key + '-roundtrip'
                    self.assertEqual(collector.allowed(profile, base + '.json'), 'json')
                    self.assertEqual(collector.allowed(profile, base + '/reference/source-manifest.json'), 'json')
                    for name in ('learner-rejected.log', 'reference-accepted.log', 'rebuilt-learner-rejected.log'):
                        self.assertEqual(collector.allowed(profile, base + '/stage/' + name), 'log')
                    self.assertIsNone(collector.allowed(profile, base + '/stage/arbitrary.log'))
                    self.assertIsNone(collector.allowed(profile, base + '/source-fixture.zip'))
                self.assertIsNone(collector.allowed(profile, 'build/quality/unrelated-roundtrip.json'))
        self.assertEqual(collector.allowed('distributed', 'build/quality/distributed-region-audit.json'), 'json')
        self.assertEqual(collector.allowed('distributed', 'build/quality/distributed-region-audit/reference/source-manifest.json'), 'json')
        self.assertIsNone(collector.allowed('messaging', 'build/quality/distributed-region-audit.json'))

    def test_all_profiles_collect_their_own_fixture(self):
        for name in set().union(*CI_NAMES.values()):
            self.write(name, '{"status":"FAIL"}')
        for course, _ in COURSES.values():
            self.write(f'courses/{course}/build/verification/report.json', '{"status":"FAIL"}')
        self.write('courses/java-frameworks/authoring/ui-verification.json', '{"status":"FAIL"}')
        for profile in list(CI_NAMES) + list(COURSES):
            with self.subTest(profile=profile):
                result = self.collect(profile)
                expected = CI_NAMES[profile] if profile in CI_NAMES else {f'courses/{COURSES[profile][0]}/build/verification/report.json'}
                if profile == 'java-frameworks-ui': expected = {'courses/java-frameworks/authoring/ui-verification.json'}
                if profile == 'java-frameworks-backend': expected.add('courses/java-frameworks/authoring/ui-verification.json')
                self.assertEqual({item['path'] for item in result['copied']}, expected)
                self.assertEqual(result['collection_status'], 'COMPLETE')
                self.assertEqual(result['job_status'], 'failure')

    def test_framework_ui_excludes_committed_historical_pass_reports(self):
        prefix = 'courses/java-frameworks/'
        for name in ('callers-report.json', 'metadata-report.json', 'negative-report.json', 'source-verification.json'):
            self.write(prefix + 'authoring/' + name, '{"status":"passed","scope":"old committed evidence"}')
        self.write(prefix + 'authoring/ui-verification.json', '{"status":"passed","scope":"current UI producer"}')
        self.write(prefix + 'build/server/application.log', 'current synthetic server')
        result = self.collect('java-frameworks-ui', status='success')
        self.assertEqual({row['path'] for row in result['copied']}, {
            prefix + 'authoring/ui-verification.json', prefix + 'build/server/application.log'})

    def test_unsupported_profiles_and_statuses_fail_before_creating_output(self):
        output = self.root / 'rejected'
        for profile in ('unknown', 'java-advanced', '../ci-plan', ''):
            with self.subTest(profile=profile), self.assertRaises(ValueError):
                collector.collect(self.repo, output, profile)
            self.assertFalse(output.exists())
        with self.assertRaises(ValueError):
            collector.collect(self.repo, output, 'ci-plan', 'PASS')
        self.assertFalse(output.exists())

    def test_overlapping_and_existing_outputs_rejected_without_overwrite(self):
        for output in (self.repo, self.repo / 'evidence', self.root):
            with self.subTest(output=output), self.assertRaises(ValueError):
                collector.collect(self.repo, output, 'ci-plan')
        output = self.root / 'existing'; output.mkdir()
        sentinel = output / 'keep'; sentinel.write_text('original')
        with self.assertRaises(OSError):
            collector.collect(self.repo, output, 'ci-plan')
        self.assertEqual(sentinel.read_text(), 'original')
        self.assertEqual(list(output.iterdir()), [sentinel])

    def test_repo_and_output_parent_symlinks_rejected(self):
        repo_link = self.root / 'repo-link'; repo_link.symlink_to(self.repo, target_is_directory=True)
        with self.assertRaises(OSError):
            collector.collect(repo_link, self.root / 'out-link-repo', 'ci-plan')
        outside = self.root / 'outside'; outside.mkdir()
        output_parent = self.root / 'output-parent'; output_parent.symlink_to(outside, target_is_directory=True)
        with self.assertRaises(OSError):
            collector.collect(self.repo, output_parent / 'out', 'ci-plan')
        self.assertEqual(list(outside.iterdir()), [])

    def test_allowlisted_symlink_leaf_is_omitted(self):
        private = self.root / 'private.json'; private.write_text('{"private":"NEVER_COPY"}')
        leaf = self.repo / 'build/ci/plan.json'; leaf.parent.mkdir(parents=True)
        leaf.symlink_to(private)
        result = self.collect()
        self.assertEqual(result['copied'], [])
        self.assertEqual(result['collection_status'], 'PARTIAL')
        self.assertEqual(result['omitted'][0]['path'], 'build/ci/plan.json')
        self.assertNotIn('NEVER_COPY', (self.output / 'collection.json').read_text())

    def test_input_parent_symlink_never_traversed(self):
        outside = self.root / 'outside'; (outside / 'ci').mkdir(parents=True)
        (outside / 'ci/plan.json').write_text('{"private":"NEVER_COPY"}')
        (self.repo / 'build').symlink_to(outside, target_is_directory=True)
        result = self.collect()
        self.assertEqual(result['copied'], [])
        self.assertEqual(result['collection_status'], 'PARTIAL')
        self.assertNotIn('NEVER_COPY', (self.output / 'collection.json').read_text())

    def test_fifo_is_rejected_without_open_blocking(self):
        fifo = self.repo / 'build/ci/plan.json'; fifo.parent.mkdir(parents=True)
        os.mkfifo(fifo)
        process = subprocess.run([sys.executable, str(SCRIPT), '--repo', str(self.repo), '--profile', 'ci-plan',
                                  '--output', str(self.root / 'fifo-output'), '--job-status', 'failure'],
                                 capture_output=True, text=True, timeout=5)
        self.assertEqual(process.returncode, 0, process.stderr)
        result = json.loads((self.root / 'fifo-output/collection.json').read_text())
        self.assertEqual(result['copied'], [])
        self.assertEqual(result['collection_status'], 'PARTIAL')

    def test_json_secrets_private_paths_and_diagnostic_tokens_redacted(self):
        payload = {'status': 'FAIL', 'failed_tests': 2, 'token': 'JSON_TOKEN_SECRET',
                   'nested': [{'access_token': 'ACCESS_SECRET', 'Cookie': 'COOKIE_SECRET',
                               'text': 'Authorization: Bearer AUTH_SECRET\npassword=PASS_SECRET token=TOKEN_SECRET\n'
                                       'https://alice:URL_SECRET@example.invalid/api?access_token=QUERY_SECRET\n'
                                       'github_pat_GITHUBSECRET abc /home/alice/private/project.java '
                                       '/Users/alice/private/data /tmp/private-build/log.txt '
                                       '/workspace/private/project /root/.ssh/id_rsa C:\\Users\\alice\\private\\file'}]}
        self.write('build/ci/plan.json', json.dumps(payload))
        result = self.collect()
        output = (self.output / 'build/ci/plan.json').read_text()
        for secret in ('JSON_TOKEN_SECRET', 'ACCESS_SECRET', 'COOKIE_SECRET', 'AUTH_SECRET', 'PASS_SECRET',
                       'TOKEN_SECRET', 'URL_SECRET', 'QUERY_SECRET', 'GITHUBSECRET', '/home/alice', '/Users/alice',
                       '/tmp/private-build', '/workspace/private', '/root/.ssh', 'C:\\\\Users\\\\alice'):
            self.assertNotIn(secret, output, secret)
        value = json.loads(output)
        self.assertEqual(value['status'], 'FAIL')
        self.assertEqual(value['failed_tests'], 2)
        self.assertEqual(result['job_status'], 'failure')
        self.assertNotEqual(result['copied'][0]['original_sha256'], result['copied'][0]['uploaded_sha256'])

    def test_nested_keys_quoted_env_and_recognizable_credentials_redacted(self):
        secrets = ['DATABASE_SECRET', 'AWS_SECRET_VALUE', 'QUOTED VALUE WITH SPACES',
                   'QUOTED_JSON_SECRET', 'AKIA1234567890ABCDEF',
                   'eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiJhbGljZSJ9.signatureSecret',
                   'PRIVATE_KEY_PAYLOAD']
        payload = {'environment': {'DB_PASSWORD': secrets[0], 'AWS_SECRET_ACCESS_KEY': secrets[1]},
                   'text': 'API_TOKEN="' + secrets[2] + '"\n' +
                           '{"client_secret": "' + secrets[3] + '"}\n' +
                           secrets[4] + '\n' + secrets[5] + '\n' +
                           '-----BEGIN RSA PRIVATE KEY-----\n' + secrets[6] + '\n-----END RSA PRIVATE KEY-----',
                   '/home/alice/private/project': 'failure-location'}
        self.write('build/ci/plan.json', json.dumps(payload))
        self.collect()
        output = (self.output / 'build/ci/plan.json').read_text()
        for secret in secrets + ['/home/alice']:
            self.assertNotIn(secret, output)
        self.assertIn('failure-location', output)

    def test_log_full_cookie_and_credentials_assignments_are_redacted(self):
        relative = 'courses/java-foundations/build/verification/case/compile.log'
        self.write(relative, 'Cookie: session=SESSION_SECRET; refresh=REFRESH_SECRET\n'
                   'credentials=CREDENTIALS_SECRET\nFINAL_FAILURE')
        self.collect('java-foundations')
        output = (self.output / relative).read_text()
        for secret in ('SESSION_SECRET', 'REFRESH_SECRET', 'CREDENTIALS_SECRET'):
            self.assertNotIn(secret, output)
        self.assertIn('FINAL_FAILURE', output)

    def test_systemic_output_failure_is_fatal_and_does_not_write_success_manifest(self):
        self.write('build/ci/plan.json', '{}')
        output = self.root / 'failed-output'
        with patch.object(collector, 'write_new', side_effect=OSError('disk failure')):
            with self.assertRaises(OSError):
                collector.collect(self.repo, output, 'ci-plan', 'failure')
        self.assertFalse((output / 'collection.json').exists())

    def test_junit_verdicts_preserved_and_raw_properties_streams_removed(self):
        xml = '''<testsuites tests="3" failures="1" errors="1" skipped="1" hostname="private-host">
          <testsuite name="suite" tests="3" failures="1" errors="1" skipped="1" time="1.5">
            <properties><property name="secret" value="PROPERTY_SECRET"/></properties>
            <testcase name="fails" classname="Demo" time="0.5"><failure type="AssertionError" message="token=FAIL_SECRET">failed at /home/alice/Test.java</failure><system-out>STDOUT_SECRET</system-out></testcase>
            <testcase name="errors"><error type="IOException" message="password=ERROR_SECRET">error</error><system-err>STDERR_SECRET</system-err></testcase>
            <testcase name="skips"><skipped message="not available">skipped</skipped></testcase>
            <system-out>SUITE_STDOUT_SECRET</system-out><system-err>SUITE_STDERR_SECRET</system-err>
          </testsuite></testsuites>'''
        relative = 'courses/java-foundations/app/build/test-results/test/TEST-Demo.xml'
        self.write(relative, xml)
        self.collect('java-foundations')
        output = (self.output / relative).read_bytes(); root = ET.fromstring(output)
        self.assertEqual({key: root.attrib[key] for key in ('tests','failures','errors','skipped')},
                         {'tests':'3', 'failures':'1', 'errors':'1', 'skipped':'1'})
        self.assertEqual(len(root.findall('.//failure')), 1)
        self.assertEqual(len(root.findall('.//error')), 1)
        self.assertEqual(len(root.findall('.//skipped')), 1)
        self.assertEqual(root.find('.//failure').attrib['type'], 'AssertionError')
        for secret in ('PROPERTY_SECRET', 'STDOUT_SECRET', 'STDERR_SECRET', 'FAIL_SECRET', 'ERROR_SECRET', '/home/alice', 'private-host'):
            self.assertNotIn(secret.encode(), output)
        self.assertFalse(any(node.tag in {'properties', 'property', 'system-out', 'system-err'} for node in root.iter()))

    def test_invalid_json_and_xml_are_omitted_while_valid_evidence_survives(self):
        prefix = 'courses/java-foundations/'
        self.write(prefix + 'build/verification/report.json', '{broken')
        self.write(prefix + 'authoring/metadata-report.json', '{"status":"FAIL"}')
        self.write(prefix + 'app/build/test-results/test/TEST-Entity.xml',
                   '<!DOCTYPE testsuite [<!ENTITY secret SYSTEM "file:///etc/passwd">]><testsuite>&secret;</testsuite>')
        self.write(prefix + 'app/build/test-results/test/TEST-Other.xml', '<not-junit/>')
        result = self.collect('java-foundations')
        self.assertEqual(result['collection_status'], 'PARTIAL')
        self.assertEqual([item['path'] for item in result['copied']], [prefix + 'authoring/metadata-report.json'])
        self.assertEqual(len(result['omitted']), 3)
        for item in result['omitted']:
            self.assertRegex(item['reason'], r'^[A-Za-z_]+$')

    def test_arbitrary_sources_archives_profiles_classes_and_env_excluded(self):
        prefix = 'courses/java-frameworks/'
        allowed = prefix + 'authoring/metadata-report.json'
        self.write(allowed, '{"status":"FAIL"}')
        excluded = ['.env', 'build/ui/.env', 'build/ui/private.json', 'build/ui/arbitrary.png',
                    'build/server/environment.log', 'authoring/arbitrary-report.json', 'src/Private.java',
                    'build/classes/Private.class', 'build/libs/private.jar', 'build/archive.zip',
                    'build/profile/Local State', 'build/browser/profile/Cookies',
                    'build/ui-tools/node_modules/dependency/secret.json',
                    '.gradle/cache/secret', '.aws/credentials', '.ssh/id_rsa',
                    'module/build/test-results/test/private.xml', 'module/build/test-results/test/binary/output.bin']
        for name in excluded:
            self.write(prefix + name, 'NEVER_COPY')
        self.write('build/quality/java-frameworks-roundtrip/source-fixture.zip', 'NEVER_COPY')
        self.write('build/quality/java-frameworks-roundtrip/extra.log', 'NEVER_COPY')
        result = self.collect('java-frameworks-backend')
        self.assertEqual([item['path'] for item in result['copied']], [allowed])
        for path in self.output.rglob('*'):
            if path.is_file():
                self.assertNotIn(b'NEVER_COPY', path.read_bytes())

    def test_png_pixel_chunks_retained_and_ancillary_metadata_removed(self):
        original = png(metadata=True)
        self.assertEqual(collector.clean_png(original), png(metadata=False))
        relative = 'courses/java-frameworks/build/ui/desktop.png'
        self.write(relative, original)
        self.collect('java-frameworks-ui')
        self.assertEqual((self.output / relative).read_bytes(), png(metadata=False))

    def test_invalid_pngs_are_not_uploaded(self):
        examples = [b'not PNG', png(False)[:-1], png(False) + b'private-trailer',
                    png(False).replace(b'IDAT', b'XDAT', 1),
                    png(False)[:-12] + chunk(b'ABCD', b'critical') + chunk(b'IEND', b'')]
        for data in examples:
            with self.subTest(data=data[:20]), self.assertRaises(ValueError):
                collector.clean_png(data)
        self.write('courses/java-frameworks/build/ui/failure.png', examples[0])
        result = self.collect('java-frameworks-ui')
        self.assertEqual(result['copied'], [])
        self.assertEqual(result['collection_status'], 'PARTIAL')

    def test_logs_keep_bounded_tail_and_redact_secrets(self):
        relative = 'courses/java-foundations/build/verification/case/compile.log'
        original = 'HEAD_MUST_DISAPPEAR\n' + 'x' * 1000 + '\ntoken=TAIL_SECRET\nFINAL_FAILURE'
        self.write(relative, original)
        with patch.object(collector, 'MAX_LOG', 256):
            result = self.collect('java-foundations')
        output = (self.output / relative).read_bytes()
        self.assertNotIn(b'HEAD_MUST_DISAPPEAR', output)
        self.assertNotIn(b'TAIL_SECRET', output)
        self.assertIn(b'FINAL_FAILURE', output)
        self.assertTrue(result['copied'][0]['truncated'])
        self.assertLessEqual(len(output), 256)

    def test_log_truncation_flag_includes_header_budget_and_utf8_expansion(self):
        relative = 'courses/java-foundations/build/verification/case/compile.log'
        for data in (b'x' * 250, b'\xff' * 100):
            with self.subTest(original_bytes=len(data)):
                self.write(relative, data)
                with patch.object(collector, 'MAX_LOG', 256):
                    result = self.collect('java-foundations')
                self.assertTrue(result['copied'][0]['truncated'])
                self.assertLessEqual(result['copied'][0]['bytes'], 256)

    def test_invalid_utf8_log_output_remains_byte_bounded(self):
        relative = 'courses/java-foundations/build/verification/case/compile.log'
        self.write(relative, b'\xff' * 1024)
        with patch.object(collector, 'MAX_LOG', 256):
            self.collect('java-foundations')
        output = (self.output / relative).read_bytes()
        output.decode('utf-8')
        self.assertLessEqual(len(output), 256)

    def test_input_per_file_cap_omits_only_oversized_file(self):
        self.write('build/ci/docs.json', '{"padding":"' + 'x' * 400 + '"}')
        self.write('build/quality/academy-metadata.json', '{"status":"FAIL"}')
        with patch.object(collector, 'MAX_FILE', 128):
            result = self.collect('ci-static')
        self.assertEqual(result['collection_status'], 'PARTIAL')
        self.assertEqual([item['path'] for item in result['copied']], ['build/quality/academy-metadata.json'])
        self.assertEqual([item['path'] for item in result['omitted']], ['build/ci/docs.json'])

    def test_sanitized_json_expansion_cannot_exceed_per_file_cap(self):
        self.write('build/ci/plan.json', json.dumps([0] * 100, separators=(',', ':')))
        with patch.object(collector, 'MAX_FILE', 256):
            result = self.collect()
        self.assertTrue(all(item['bytes'] <= 256 for item in result['copied']))
        self.assertEqual(result['collection_status'], 'PARTIAL')

    def test_count_cap_and_total_byte_cap_record_partial_omissions(self):
        names = ['build/ci/docs.json', 'build/ci/public-course.json', 'build/quality/academy-metadata.json']
        for name in names:
            self.write(name, '{"status":"FAIL"}')
        with patch.object(collector, 'MAX_FILES', 1):
            result = self.collect('ci-static')
        self.assertEqual(len(result['copied']), 1)
        self.assertEqual(len(result['omitted']), 2)
        self.assertEqual(result['collection_status'], 'PARTIAL')
        with patch.object(collector, 'MAX_TOTAL', 30):
            result = self.collect('ci-static')
        self.assertLessEqual(result['bytes'], 30)
        self.assertEqual(len(result['copied']), 1)
        self.assertEqual(len(result['omitted']), 2)
        self.assertEqual(result['collection_status'], 'PARTIAL')

    def test_scan_and_depth_budgets_fail_bounded_with_partial_collection(self):
        self.write('build/ci/plan.json', '{}')
        self.write('build/ci/unrelated.json', '{}')
        with patch.object(collector, 'MAX_SCAN', 1):
            result = self.collect()
        self.assertEqual(result['collection_status'], 'PARTIAL')
        self.assertEqual(result['copied'], [])
        self.write('courses/java-foundations/a/b/build/verification/report.json', '{}')
        with patch.object(collector, 'MAX_DEPTH', 1):
            result = self.collect('java-foundations')
        self.assertEqual(result['collection_status'], 'PARTIAL')

    def test_missing_evidence_never_claims_pass_and_preserves_job_failure(self):
        for status in ('success', 'failure', 'cancelled', 'unknown'):
            result = self.collect(status=status)
            self.assertEqual(result['job_status'], status)
            self.assertEqual(result['collection_status'], 'NO_EVIDENCE')
            self.assertEqual(result['test_verdict'], 'NOT_INFERRED_FROM_COLLECTION')
            self.assertNotIn('PASS', result.values())

    def test_cli_failure_job_outcome_is_not_promoted_by_collection(self):
        self.write('build/ci/plan.json', '{"status":"FAIL","failures":3}')
        output = self.root / 'cli-output'
        process = subprocess.run([sys.executable, str(SCRIPT), '--repo', str(self.repo), '--profile', 'ci-plan',
                                  '--output', str(output), '--job-status', 'failure'],
                                 capture_output=True, text=True, timeout=5)
        self.assertEqual(process.returncode, 0, process.stderr)
        stdout = json.loads(process.stdout)
        self.assertEqual(stdout['job_status'], 'failure')
        self.assertEqual(stdout['collection_status'], 'COMPLETE')
        report = json.loads((output / 'build/ci/plan.json').read_text())
        self.assertEqual(report, {'status':'FAIL', 'failures':3})
        summary = json.loads((output / 'collection.json').read_text())
        self.assertEqual(summary['test_verdict'], 'NOT_INFERRED_FROM_COLLECTION')
        self.assertNotIn('PASS', summary.values())
        invalid = subprocess.run([sys.executable, str(SCRIPT), '--repo', str(self.repo), '--profile', 'unknown',
                                  '--output', str(self.root / 'invalid-cli')],
                                 capture_output=True, text=True, timeout=5)
        self.assertNotEqual(invalid.returncode, 0)
        self.assertFalse((self.root / 'invalid-cli').exists())


if __name__ == '__main__':
    unittest.main()
