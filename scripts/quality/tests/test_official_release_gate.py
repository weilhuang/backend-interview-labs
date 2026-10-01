"""Synthetic fixtures exercise the guard; none represents official GUI evidence."""
import json
import copy
from pathlib import Path
import sys
import shutil
import stat
import tempfile
import unittest
from unittest.mock import patch
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import official_release_gate as gate
import yaml


class ReleaseGateTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source = self.root / 'courses/source'
        self.release = self.root / 'release'
        self.release.mkdir()
        self.patch = patch.dict(gate.COURSES, {'java-concurrency': ('source', 1, 1)}, clear=True)
        self.patch.start()
        self.addCleanup(self.patch.stop)
        self.code = 'class Lab { int value(){return 42;} }'
        self.ph = {'offset': self.code.index('return'), 'length': 10, 'placeholder_text': 'TODO'}
        self.write('lesson/task/src/Lab.java', self.code)
        self.write('lesson/task/test/LabTest.java', 'class LabTest {}')
        self.write('lesson/task/task.md', 'Answer: return 42;')
        self.additional = ['build.gradle', 'settings.gradle', 'gradle.properties', 'gradlew',
                           'gradle/wrapper/gradle-wrapper.jar', 'gradle/wrapper/gradle-wrapper.properties', 'README.md']
        for name in self.additional:
            self.write(name, 'fixture')
        self.meta = {'type': 'marketplace', 'language': 'Chinese', 'title': 'Fixture title', 'summary': 'Fixture summary',
                     'programming_language': 'Java', 'environment_settings': {'jvm_language_level': 'JDK_21'},
                     'content': ['lesson'], 'additional_files': [{'name': name} for name in self.additional]}
        self.write_yaml('course-info.yaml', self.meta)
        self.write_yaml('lesson/lesson-info.yaml', {'content': ['task']})
        self.write_yaml('lesson/task/task-info.yaml', {'type': 'edu', 'files': [
            {'name': 'src/Lab.java', 'visible': True, 'placeholders': [self.ph]},
            {'name': 'test/LabTest.java', 'visible': True}]})
        self.task = {'name': 'task', 'task_type': 'edu', 'description_text': 'Answer: return 42;', 'files': {
            'src/Lab.java': {'is_visible': True, 'placeholders': [dict(self.ph, length=4, possible_answer='opaque')]},
            'test/LabTest.java': {'is_visible': True, 'placeholders': []}}}
        self.data = {'version': 23, 'edu_plugin_version': 'unit-fixture-only',
                     'title': 'Fixture title', 'summary': 'Fixture summary', 'language': 'zh',
                     'programming_language_id': 'JAVA', 'course_type': 'Marketplace',
                     'environment_settings': {'jvm_language_level': 'JDK_21'},
                     'items': [{'title': 'lesson', 'task_list': [self.task]}],
                     'additional_files': [{'name': name, 'is_visible': False} for name in self.additional
                                          if name not in gate.GENERATED_WRAPPERS]}
        self.archive = self.release / 'archives/course.zip'
        self.archive.parent.mkdir()
        self.package()
        self.inventory_path = self.release / 'import.json'
        # Explicit synthetic plaintext inventory for regression only, not production provenance.
        self.inventory = {'schema_version': 1, 'fresh_native_execution': dict(gate.RUNTIME),
                          'kind': 'recorded-existing-native-import-plaintext',
                          'archive_sha256': gate.digest(self.archive.read_bytes()),
                          'observed_at_utc': 'fixture-only', 'evidence_reference': 'synthetic unit test',
                          'assets': gate.learner_assets(self.source, gate.inspect_course(self.source))}
        self.row = {'status': 'READY', 'source_root': 'courses/source', 'tasks': 1, 'placeholders': 1,
                    'archive': self.file_record(self.archive), 'exporter_version': 'unit-fixture-only',
                    'current_source_assets': {name: gate.digest((self.source / name).read_bytes())
                                              for name in gate.inspect_course(self.source)['assets']},
                    'omitted_additional_files': [], 'packaging_overlays': []}
        self.save_inventory()
        self.manifest_path = self.release / 'manifest.json'
        self.manifest = {'schema_version': 1, 'source_base_commit': 'f5b0d493573f241bf6ea2bad3318911debd7f74f',
                         'courses': {'java-concurrency': self.row}}

    def write(self, name, text):
        path = self.source / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)

    def write_yaml(self, name, data):
        self.write(name, yaml.safe_dump(data))

    def file_record(self, path):
        return {'path': path.relative_to(self.release).as_posix(), 'bytes': path.stat().st_size,
                'sha256': gate.digest(path.read_bytes())}

    def package(self, missing=None):
        with zipfile.ZipFile(self.archive, 'w') as archive:
            archive.writestr('course.json', json.dumps(self.data))
            names = ['lesson/task/src/Lab.java', 'lesson/task/test/LabTest.java'] + [f['name'] for f in self.data['additional_files']]
            for name in names:
                if name != missing:
                    archive.writestr('contents/' + name, b'synthetic-opaque-payload')

    def save_inventory(self):
        self.inventory_path.write_text(json.dumps(self.inventory))
        self.row['native_import_inventory'] = self.file_record(self.inventory_path)

    def repin_fixture(self):
        self.row['archive'] = self.file_record(self.archive)
        self.inventory['archive_sha256'] = self.row['archive']['sha256']
        self.save_inventory()

    def check(self):
        self.manifest_path.write_text(json.dumps(self.manifest))
        return gate.check_release(self.root, self.manifest_path)

    def assert_failed(self, phrase):
        result = self.check()
        self.assertEqual('FAIL', result['status'])
        self.assertIn(phrase, result['courses'][0]['error'])

    def test_recorded_match_has_no_native_or_docker_claim(self):
        before = {p: p.read_bytes() for p in self.source.rglob('*') if p.is_file()}
        result = self.check()
        self.assertEqual('PASS', result['status'])
        self.assertEqual(gate.RUNTIME, {key: result[key] for key in gate.RUNTIME})
        self.assertIn('not a fresh import', result['courses'][0]['recorded_import_inventory'])
        self.assertEqual(before, {p: p.read_bytes() for p in self.source.rglob('*') if p.is_file()})

    def test_archive_hash_and_size_drift(self):
        self.archive.write_bytes(self.archive.read_bytes() + b'x')
        self.assert_failed('integrity mismatch')

    def test_source_drift(self):
        self.write('lesson/task/test/LabTest.java', 'changed')
        self.assert_failed('source inventory/hash drift')

    def test_import_inventory_file_drift(self):
        self.inventory_path.write_text('{}')
        self.assert_failed('integrity mismatch')

    def test_import_inventory_wrong_archive(self):
        self.inventory['archive_sha256'] = '0' * 64
        self.save_inventory()
        self.assert_failed('inventory/archive mismatch')

    def test_inventory_cannot_claim_fresh_gui_or_java(self):
        self.inventory['fresh_native_execution'] = {'native_idea': 'PASS', 'java': 'PASS'}
        self.save_inventory()
        self.assert_failed('must not claim fresh')

    def test_inventory_unknown_schema(self):
        self.inventory['schema_version'] = 2
        self.save_inventory()
        self.assert_failed('unsupported native import inventory schema')

    def test_import_plaintext_wrong_or_missing(self):
        self.inventory['assets'].pop('lesson/task/test/LabTest.java')
        self.save_inventory()
        self.assert_failed('plaintext inventory differs')

    def test_import_plaintext_changed_hash(self):
        self.inventory['assets']['lesson/task/test/LabTest.java'] = '0' * 64
        self.save_inventory()
        self.assert_failed('plaintext inventory differs')

    def test_hidden_task_test_rejected(self):
        self.task['files']['test/LabTest.java']['is_visible'] = False
        self.package(); self.repin_fixture()
        self.assert_failed('hidden in official archive')

    def test_missing_payload_rejected(self):
        self.package(missing='lesson/task/test/LabTest.java'); self.repin_fixture()
        self.assert_failed('missing or empty encrypted payload')

    def test_unknown_archive_format(self):
        self.data['version'] = 24
        self.package(); self.repin_fixture()
        self.assert_failed('unsupported archive format')

    def test_wrong_course_identity_fields(self):
        for key in ('title', 'summary', 'language', 'programming_language_id', 'course_type'):
            with self.subTest(field=key):
                original = self.data[key]
                self.data[key] = 'wrong'
                self.package(); self.repin_fixture()
                self.assert_failed('course identity differs')
                self.data[key] = original

    def test_unexpected_empty_hierarchy_node(self):
        self.data['items'].append({'title': 'unexpected', 'items': []})
        self.package(); self.repin_fixture()
        self.assert_failed('hierarchy/order differs')

    def test_task_order_drift(self):
        shutil.copytree(self.source / 'lesson/task', self.source / 'lesson/second')
        self.write_yaml('lesson/lesson-info.yaml', {'content': ['task', 'second']})
        second = copy.deepcopy(self.task)
        second['name'] = 'second'
        self.data['items'][0]['task_list'] = [second, self.task]
        gate.COURSES['java-concurrency'] = ('source', 2, 2)
        self.row.update(tasks=2, placeholders=2)
        self.row['current_source_assets'] = {name: gate.digest((self.source / name).read_bytes())
                                             for name in gate.inspect_course(self.source)['assets']}
        self.package()
        with zipfile.ZipFile(self.archive, 'a') as archive:
            for name in ('src/Lab.java', 'test/LabTest.java'):
                archive.writestr('contents/lesson/second/' + name, b'synthetic-opaque-payload')
        self.repin_fixture()
        self.assert_failed('hierarchy/order differs')

    def test_duplicate_archive_json_key_rejected(self):
        with zipfile.ZipFile(self.archive) as archive:
            files = {name: archive.read(name) for name in archive.namelist()}
        files['course.json'] = files['course.json'].decode().replace('"version": 23', '"version":24,"version":23').encode()
        with zipfile.ZipFile(self.archive, 'w') as archive:
            for name, data in files.items():
                archive.writestr(name, data)
        self.repin_fixture()
        self.assert_failed('duplicate JSON key')

    def test_payload_must_not_have_directory_type(self):
        with zipfile.ZipFile(self.archive) as archive:
            files = [(entry, archive.read(entry)) for entry in archive.infolist()]
        with zipfile.ZipFile(self.archive, 'w') as archive:
            for entry, data in files:
                if entry.filename == 'contents/lesson/task/src/Lab.java':
                    entry.external_attr = (stat.S_IFDIR | 0o755) << 16
                archive.writestr(entry, data)
        self.repin_fixture()
        self.assert_failed('filename/type mismatch')

    def test_source_roundtrip_fixture_is_not_official_format(self):
        with zipfile.ZipFile(self.archive, 'w') as archive:
            archive.writestr('course-info.yaml', 'synthetic source fixture')
        self.repin_fixture()
        self.assert_failed('course.json')

    def test_arbitrary_omission_rejected(self):
        self.row['omitted_additional_files'] = ['README.md']
        self.assert_failed('unapproved exporter omission')

    def test_narrow_courseignore_omission(self):
        with patch.dict(gate.OMISSIONS, {'java-concurrency': {'.courseignore'}}):
            self.write('.courseignore', 'author-only control')
            self.meta['additional_files'].append({'name': '.courseignore'})
            self.write_yaml('course-info.yaml', self.meta)
            self.row['current_source_assets'] = {name: gate.digest((self.source / name).read_bytes())
                                                 for name in gate.inspect_course(self.source)['assets']}
            self.row['omitted_additional_files'] = ['.courseignore']
            self.assertEqual('PASS', self.check()['status'])
            self.assertTrue((self.source / '.courseignore').is_file())

    def test_arbitrary_overlay_rejected(self):
        self.row['packaging_overlays'] = [{'target': 'build.gradle', 'operation': 'replace'}]
        self.assert_failed('unapproved packaging overlay')

    def test_explicit_document_overlay_preserves_source(self):
        with patch.dict(gate.OVERLAYS, {'java-concurrency': {'README.md': 'replace'}}):
            overlay = self.release / 'readme-overlay.md'
            overlay.write_text('reviewed packaging-only documentation')
            self.row['packaging_overlays'] = [dict(self.file_record(overlay), target='README.md', operation='replace',
                                                  source_sha256=self.row['current_source_assets']['README.md'])]
            self.inventory['assets']['README.md'] = gate.digest(overlay.read_bytes())
            self.save_inventory()
            self.assertEqual('PASS', self.check()['status'])
            self.assertEqual('fixture', (self.source / 'README.md').read_text())

    def test_regenerated_ids_are_not_source_drift(self):
        self.data['id'] = 9001
        self.data['items'][0]['id'] = 9002
        self.task['id'] = 9003
        self.package(); self.repin_fixture()
        self.assertEqual('PASS', self.check()['status'])

    def test_not_ready_is_nonzero_and_no_invented_import(self):
        self.archive.unlink()
        self.row.update(status='NOT_READY', reason='Official export pending')
        del self.row['archive']; del self.row['native_import_inventory']
        self.assertEqual('NOT_READY', self.check()['status'])
        self.assertEqual(2, gate.main(['--repo', str(self.root), '--manifest', str(self.manifest_path),
                                      '--report', str(self.root / 'build/quality/report.json')]))

    def run_main(self, output):
        self.manifest_path.write_text(json.dumps(self.manifest))
        return gate.main(['--repo', str(self.root), '--manifest', str(self.manifest_path), '--report', str(output)])

    def assert_output_rejected_unchanged(self, output):
        self.manifest_path.write_text(json.dumps(self.manifest))
        before = {path: path.read_bytes() for path in self.root.rglob('*') if path.is_file()}
        before_paths = set(self.root.rglob('*'))
        with patch.object(gate, 'check_release', side_effect=AssertionError('must reject before validation')) as validate:
            self.assertEqual(1, self.run_main(output))
            validate.assert_not_called()
        self.assertEqual(before, {path: path.read_bytes() for path in self.root.rglob('*') if path.is_file()})
        self.assertEqual(before_paths, set(self.root.rglob('*')))

    def test_report_cannot_overwrite_source_manifest_or_archive(self):
        for output in (self.source / 'lesson/task/src/Lab.java', self.manifest_path, self.archive):
            with self.subTest(output=output):
                self.assert_output_rejected_unchanged(output)

    def test_report_cannot_overwrite_existing_report(self):
        report = self.root / 'build/quality/existing.json'
        report.parent.mkdir(parents=True)
        report.write_text('preserve existing report')
        self.assert_output_rejected_unchanged(report)

    def test_report_cannot_create_inside_source_or_release(self):
        for output in (self.source / 'new-report.json', self.release / 'new-report.json', self.root / 'new-report.json'):
            with self.subTest(output=output):
                self.assert_output_rejected_unchanged(output)
                self.assertFalse(output.exists())

    def test_report_path_traversal_cannot_create_source_directories(self):
        self.assert_output_rejected_unchanged(self.root / 'courses/unexpected-dir/../../build/quality/report.json')
        self.assertFalse((self.root / 'courses/unexpected-dir').exists())

    def test_report_symlink_target_or_parent_rejected(self):
        directory = self.root / 'build/quality'
        directory.mkdir(parents=True)
        linked = directory / 'linked.json'
        linked.symlink_to(self.source / 'lesson/task/src/Lab.java')
        self.assert_output_rejected_unchanged(linked)
        dangling = directory / 'dangling.json'
        dangling.symlink_to(self.root / 'absent.json')
        self.assert_output_rejected_unchanged(dangling)
        parent = directory / 'linked-parent'
        parent.symlink_to(self.source, target_is_directory=True)
        self.assert_output_rejected_unchanged(parent / 'new.json')

    def test_new_build_quality_report_allowed(self):
        report = self.root / 'build/quality/new.json'
        self.assertEqual(0, self.run_main(report))
        self.assertEqual('PASS', json.loads(report.read_text())['status'])

    def test_new_external_temporary_report_allowed(self):
        with tempfile.TemporaryDirectory() as directory:
            report = Path(directory) / 'new.json'
            self.assertEqual(0, self.run_main(report))
            self.assertEqual('PASS', json.loads(report.read_text())['status'])

    def test_report_exclusive_creation_preserves_late_existing_file(self):
        report = self.root / 'build/quality/race.json'
        original_open = gate.os.open
        def open_after_creation(path, flags, *args, **kwargs):
            if path == 'race.json' and flags & gate.os.O_CREAT:
                fd = original_open(path, gate.os.O_WRONLY | gate.os.O_CREAT | gate.os.O_EXCL, 0o600, **kwargs)
                with gate.os.fdopen(fd, 'w') as stream:
                    stream.write('arrived after preflight')
            return original_open(path, flags, *args, **kwargs)
        with patch.object(gate.os, 'open', open_after_creation), patch.object(
                gate.os, 'supports_dir_fd', gate.os.supports_dir_fd | {open_after_creation}):
            self.assertEqual(1, self.run_main(report))
        self.assertEqual('arrived after preflight', report.read_text())

    def test_late_parent_replacement_cannot_redirect_into_source(self):
        report = self.root / 'build/quality/race.json'
        original_open = gate.os.open
        def open_after_replacement(path, flags, *args, **kwargs):
            if path == 'race.json' and flags & gate.os.O_CREAT:
                report.parent.rename(report.parent.with_name('pinned-original'))
                report.parent.symlink_to(self.source, target_is_directory=True)
            return original_open(path, flags, *args, **kwargs)
        with patch.object(gate.os, 'open', open_after_replacement), patch.object(
                gate.os, 'supports_dir_fd', gate.os.supports_dir_fd | {open_after_replacement}):
            self.assertEqual(1, self.run_main(report))
        self.assertFalse((self.source / 'race.json').exists())

    def test_unsupported_safe_writer_has_no_fallback(self):
        report = self.root / 'build/quality/report.json'
        with patch.object(gate.os, 'supports_dir_fd', set()):
            self.assertEqual(1, self.run_main(report))
        self.assertFalse((self.root / 'build').exists())

    def test_pilot_or_extra_course_rejected(self):
        self.manifest['courses']['java-recovery-collections'] = self.row
        with self.assertRaisesRegex(Exception, 'excluding pilot'):
            self.check()

    def test_unlisted_archive_rejected(self):
        (self.archive.parent / 'extra.zip').write_bytes(b'extra')
        with self.assertRaisesRegex(Exception, 'ZIP inventory differs'):
            self.check()

    def test_uppercase_or_renamed_surplus_archive_rejected(self):
        for name in ('pilot.ZIP', 'renamed-archive.bin'):
            extra = self.archive.parent / name
            extra.write_bytes(b'extra')
            with self.assertRaisesRegex(Exception, 'ZIP inventory differs'):
                self.check()
            extra.unlink()

    def test_duplicate_json_keys_rejected(self):
        self.manifest_path.write_text('{"schema_version":1,"schema_version":1}')
        with self.assertRaisesRegex(Exception, 'duplicate JSON key'):
            gate.check_release(self.root, self.manifest_path)


if __name__ == '__main__':
    unittest.main()
