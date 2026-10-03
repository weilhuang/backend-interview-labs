"""Real bounded filesystem prechecks; synthetic metadata, no Java/display launch."""
import hashlib
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import awt_title_fixture as fixture


class PrecheckBoundary(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.folder = Path(self.tmp.name)
        self.root = self.folder / 'toolchain'
        self.files = {
            'idea/product-info.json': json.dumps({'version': fixture.IDEA_VERSION,
                'buildNumber': fixture.IDEA_BUILD}).encode(),
            'idea/jbr/release': b'JAVA_VERSION="25.0.4"\n',
            'idea/jbr/bin/java': b'synthetic regular file; never executed',
            'idea/jbr/lib/server/libjvm.so': b'synthetic JVM bytes',
            'idea/jbr/lib/libawt_xawt.so': b'synthetic AWT bytes',
        }
        for name, raw in self.files.items():
            path = self.root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(raw)
        (self.root / 'idea/jbr/bin/java').chmod(0o700)
        self.environment = patch.dict(os.environ, {'RUNNER_TEMP': str(self.folder),
            'TOOLCHAIN_DIR': str(self.root), 'GITHUB_RUN_ID': '123',
            'GITHUB_RUN_ATTEMPT': '1', 'GITHUB_SHA': 'a' * 40})
        self.environment.start()
        self.addCleanup(self.environment.stop)

    def precheck_fails(self, expected_step, expected_reason=None):
        with self.assertRaises(fixture.PrecheckFailure) as error:
            fixture._runtime_identity(self.root)
        value = error.exception.document
        self.assertEqual(value['step'], expected_step)
        if expected_reason:
            self.assertEqual(value['reason'], expected_reason)
        self.assertEqual(fixture.precheck_document(value), value)
        self.assertNotIn(str(self.folder), json.dumps(value))
        return value

    def test_real_filesystem_and_all_hashes_without_validity_mocks(self):
        java, value = fixture._runtime_identity(self.root)
        self.assertEqual(java, self.root / 'idea/jbr/bin/java')
        self.assertIsNone(value['java_runtime_version'])
        for key, relative in (('release_sha256', 'idea/jbr/release'),
                              ('java_sha256', 'idea/jbr/bin/java'),
                              ('libjvm_sha256', 'idea/jbr/lib/server/libjvm.so'),
                              ('libawt_xawt_sha256', 'idea/jbr/lib/libawt_xawt.so')):
            self.assertEqual(value['hashes'][key], hashlib.sha256(self.files[relative]).hexdigest())

    def test_missing_environment_is_bound_to_root_step_without_value_leak(self):
        with patch.dict(os.environ, {}, clear=True):
            self.precheck_fails('ROOT_BINDING', 'REQUIRED_FIELD')

    def test_missing_product_info_is_specific(self):
        (self.root / 'idea/product-info.json').unlink()
        self.precheck_fails('PRODUCT_READ', 'MISSING')

    def test_product_size_boundary_records_safe_size_without_reading_payload(self):
        (self.root / 'idea/product-info.json').write_bytes(b'SYNTHETIC_PRIVATE' * 5000)
        value = self.precheck_fails('PRODUCT_READ', 'CONDITION_REJECTED')
        self.assertEqual(value['facts']['size_bytes'], 85000)
        self.assertFalse(value['facts']['within_limit'])
        self.assertNotIn('SYNTHETIC_PRIVATE', json.dumps(value))

    def test_product_parse_and_identity_are_distinct(self):
        path = self.root / 'idea/product-info.json'
        for raw, step in ((b'{', 'PRODUCT_JSON'),
                          (b'{"version":"other","buildNumber":"private"}', 'PRODUCT_IDENTITY'),
                          (b'{"version":"2026.1.5","version":"2026.1.5"}', 'PRODUCT_JSON')):
            with self.subTest(raw=raw):
                path.write_bytes(raw)
                self.precheck_fails(step)

    def test_release_missing_wrong_version_duplicate_and_zero_are_distinct_from_read_cap(self):
        path = self.root / 'idea/jbr/release'
        path.unlink()
        self.precheck_fails('RELEASE_READ', 'MISSING')
        for raw in (b'', b'JAVA_VERSION="25.0.4+1"\n', b'JAVA_VERSION="25.0.4"\n' * 2):
            with self.subTest(raw=raw):
                path.write_bytes(raw)
                value = self.precheck_fails('RELEASE_VERSION', 'CONDITION_REJECTED')
                self.assertFalse(value['facts']['identity_matches'])
                self.assertEqual(value['facts']['metadata_sha256'], hashlib.sha256(raw).hexdigest())
                if b'+1' in raw:
                    self.assertEqual(value['facts']['observed_version'], '25.0.4+1')
        path.write_bytes(b'x' * 16385)
        self.assertFalse(self.precheck_fails('RELEASE_READ')['facts']['within_limit'])

    def test_executable_mode_and_missing_library_have_exact_steps(self):
        java = self.root / 'idea/jbr/bin/java'
        java.chmod(0o600)
        self.assertFalse(self.precheck_fails('JAVA_EXECUTABLE')['facts']['executable'])
        java.chmod(0o700)
        (self.root / 'idea/jbr/lib/server/libjvm.so').unlink()
        self.precheck_fails('HASH_LIBJVM', 'MISSING')

    def test_nonregular_and_symlink_ancestors_remain_rejected(self):
        path = self.root / 'idea/product-info.json'
        path.unlink(); path.symlink_to(self.root / 'idea/jbr/release')
        self.precheck_fails('PRODUCT_READ')
        path.unlink(); path.mkdir()
        self.precheck_fails('PRODUCT_READ', 'PATH_OR_FILE_BOUNDARY')
        path.rmdir(); path.write_bytes(self.files['idea/product-info.json'])
        moved = self.root / 'idea-real'; (self.root / 'idea').rename(moved)
        (self.root / 'idea').symlink_to(moved, target_is_directory=True)
        self.precheck_fails('PRODUCT_READ', 'PATH_OR_FILE_BOUNDARY')

    def test_full_main_retains_first_precheck_and_never_spawns(self):
        (self.root / 'idea/jbr/release').write_bytes(b'JAVA_VERSION="not-approved"\n')
        output = self.folder / 'report.json'
        with patch.object(fixture.subprocess, 'Popen') as spawn:
            with self.assertRaises(SystemExit):
                fixture.main(self.root, output)
        spawn.assert_not_called()
        value = fixture.report_document(json.loads(output.read_bytes()))
        self.assertEqual(value['precheck_failure']['step'], 'RELEASE_VERSION')
        self.assertEqual(value['cleanup'], {'jvm': 'NOT_STARTED', 'xvfb': 'NOT_STARTED'})
        self.assertEqual(value['exit_codes'], {'jvm': None, 'xvfb': None})
        self.assertIsNone(value['runtime'])

    def test_complete_prechecks_reach_first_spawn_boundary_without_execution(self):
        binary = self.folder / 'synthetic-Xvfb'
        binary.write_bytes(b'fixture only; never executed')
        binary.chmod(0o700)
        output = self.folder / 'report.json'
        with patch.object(fixture, 'BINARY', binary), patch.object(fixture.subprocess, 'Popen',
                side_effect=OSError('SYNTHETIC_NO_EXECUTION')) as spawn:
            with self.assertRaises(SystemExit):
                fixture.main(self.root, output)
        self.assertEqual(spawn.call_count, 1)
        value = fixture.report_document(json.loads(output.read_bytes()))
        self.assertEqual(value['error'], 'XVFB_START_UNAVAILABLE')
        self.assertIsNone(value['precheck_failure'])
        self.assertIsNotNone(value['runtime'])
        self.assertEqual(value['cleanup'], {'jvm': 'NOT_STARTED', 'xvfb': 'NOT_STARTED'})
        self.assertNotIn('SYNTHETIC_NO_EXECUTION', output.read_text())

    def test_cancellation_during_precheck_is_retained_and_no_child_starts(self):
        output = self.folder / 'report.json'
        with patch.object(fixture, 'validate_directory', side_effect=InterruptedError('SYNTHETIC_PRIVATE')):
            with patch.object(fixture.subprocess, 'Popen') as spawn:
                with self.assertRaises(SystemExit):
                    fixture.main(self.root, output)
        spawn.assert_not_called()
        value = fixture.report_document(json.loads(output.read_bytes()))
        self.assertEqual(value['error'], 'CANCELLED')
        self.assertEqual(value['precheck_failure']['step'], 'ROOT_DIRECTORY')
        self.assertEqual(value['precheck_failure']['reason'], 'CANCELLED')
        self.assertNotIn('SYNTHETIC_PRIVATE', output.read_text())

    def test_every_step_exception_is_fixed_and_does_not_serialize_payload(self):
        for step in fixture.PRECHECK_STEPS:
            with self.subTest(step=step):
                def bad():
                    raise RuntimeError({'environment': 'SYNTHETIC_PRIVATE'})
                with self.assertRaises(fixture.PrecheckFailure) as error:
                    fixture._checked(step, bad)
                self.assertEqual(error.exception.document['step'], step)
                self.assertEqual(error.exception.document['exception_class'], 'OTHER_EXCEPTION')
                self.assertNotIn('SYNTHETIC_PRIVATE', json.dumps(error.exception.document))


class PrecheckSchema(unittest.TestCase):
    def test_nested_payloads_wrong_types_and_unknown_fields_rejected(self):
        base = {'step': 'PRODUCT_READ', 'reason': 'MISSING',
                'exception_class': 'FileNotFoundError', 'facts': {}}
        mutations = ({'step': {'command': 'SYNTHETIC_PRIVATE'}}, {'step': 'PRIVATE_PATH'},
                     {'reason': ['MISSING']}, {'exception_class': 'CustomPrivateClass'},
                     {'environment': {'secret': 'SYNTHETIC_PRIVATE'}},
                     {'facts': {'size_bytes': False}}, {'facts': {'size_bytes': 2 ** 31}},
                     {'facts': {'size_bytes': -1}}, {'facts': {'within_limit': 1}},
                     {'facts': {'identity_matches': {'environment': 'SYNTHETIC_PRIVATE'}}},
                     {'facts': {'observed_version': 'SYNTHETIC_PRIVATE'}},
                     {'facts': {'observed_build': {'environment': 'SYNTHETIC_PRIVATE'}}},
                     {'facts': {'observed_version': '25.0.4+1-b329.128/private'}},
                     {'facts': {'metadata_sha256': 'PRIVATE_HASH'}},
                     {'facts': {'version_field_count': True}},
                     {'facts': {'version_field_count': 17}},
                     {'facts': {'raw': 'SYNTHETIC_PRIVATE' * 10000}})
        for mutation in mutations:
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                fixture.precheck_document({**base, **mutation})
        value = {**base, 'facts': {'size_bytes': 17, 'regular': True}}
        clean = fixture.precheck_document(value)
        value['facts']['size_bytes'] = 22
        self.assertEqual(clean['facts']['size_bytes'], 17)

    def test_numeric_identity_projection_rejects_arbitrary_vendor_text(self):
        for value in ('25.0.4', '25.0.4+1-b329.128', '2026.1.5', '261.27258.48'):
            self.assertEqual(fixture._identity_token(value), value)
        for value in ('PRIVATE', '25.0.4\nPRIVATE', '25.0.4+ghp_PRIVATE', '1' * 10000, {}, None):
            self.assertIsNone(fixture._identity_token(value))


if __name__ == '__main__':
    unittest.main()
