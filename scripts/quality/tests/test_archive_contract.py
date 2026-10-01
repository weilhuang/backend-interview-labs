import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest
import zipfile

QUALITY = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(QUALITY))
import archive_contract as archive
import academy_gate as gate
import yaml


class ArchiveTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.course = self.root / 'source'
        task = self.course / 'sec/lesson/task'
        task.mkdir(parents=True)
        code = 'class Lab { int value(){return 42;} }'
        self.source_code = code
        self.placeholder = {'offset': code.index('return'), 'length': len('return 42;'), 'placeholder_text': 'TODO'}
        self.write('sec/lesson/task/src/Lab.java', code)
        self.write('sec/lesson/task/test/LabTest.java', 'class LabTest {}')
        self.write('sec/lesson/task/task.md', 'Answer: return 42;')
        for name in ['build.gradle', 'settings.gradle', 'gradle.properties', 'gradlew',
                     'gradle/wrapper/gradle-wrapper.jar', 'gradle/wrapper/gradle-wrapper.properties']:
            self.write(name, 'fixture')
        self.additional = [p.relative_to(self.course).as_posix() for p in self.course.rglob('*') if p.is_file() and 'sec' not in p.relative_to(self.course).parts]
        self.yaml('course-info.yaml', {'programming_language': 'Java', 'environment_settings': {'jvm_language_level': 'JDK_21'}, 'content': ['sec'], 'additional_files': [{'name': n} for n in self.additional]})
        self.yaml('sec/section-info.yaml', {'content': ['lesson']})
        self.yaml('sec/lesson/lesson-info.yaml', {'content': ['task']})
        self.yaml('sec/lesson/task/task-info.yaml', {'type': 'edu', 'files': [
            {'name': 'src/Lab.java', 'visible': True, 'placeholders': [self.placeholder]},
            {'name': 'test/LabTest.java', 'visible': True}]})
        ph = dict(self.placeholder, length=4, possible_answer='opaque')
        self.task = {'name': 'task', 'task_type': 'edu', 'description_text': 'Answer: return 42;', 'files': {
            'src/Lab.java': {'is_visible': True, 'placeholders': [ph]},
            'test/LabTest.java': {'is_visible': True, 'placeholders': []}}}
        self.data = {'version': 23, 'edu_plugin_version': 'fixture-only',
                     'environment_settings': {'jvm_language_level': 'JDK_21'},
                     'items': [{'title': 'sec', 'items': [{'title': 'lesson', 'task_list': [self.task]}]}],
                     'additional_files': [{'name': n} for n in self.additional if n not in archive.GENERATED_WRAPPERS]}

    def tearDown(self):
        self.temp.cleanup()

    def write(self, name, value):
        file = self.course / name
        file.parent.mkdir(parents=True, exist_ok=True)
        file.write_text(value)

    def yaml(self, name, value):
        self.write(name, yaml.safe_dump(value))

    def package(self, missing=None):
        path = self.root / 'official-shaped-fixture.zip'
        with zipfile.ZipFile(path, 'w') as z:
            z.writestr('course.json', json.dumps(self.data))
            names = ['sec/lesson/task/src/Lab.java', 'sec/lesson/task/test/LabTest.java'] + [f['name'] for f in self.data['additional_files']]
            for name in names:
                if name != missing:
                    z.writestr('contents/' + name, b'opaque-encrypted-payload')
        return path

    def test_archive_metadata_does_not_claim_decryption(self):
        report = archive.inspect_archive(self.course, self.package())
        self.assertEqual('PASS', report['status'])
        self.assertEqual('NOT_RUN', report['native_idea'])
        self.assertEqual('NOT_RUN', report['imported_plaintext'])
        self.assertIn('OPAQUE', report['archive_payload'])

    def test_missing_payload_rejected(self):
        with self.assertRaisesRegex(gate.GateError, 'missing or empty'):
            archive.inspect_archive(self.course, self.package('sec/lesson/task/test/LabTest.java'))

    def test_wrong_shifted_offset_rejected(self):
        self.task['files']['src/Lab.java']['placeholders'][0]['offset'] += 1
        with self.assertRaisesRegex(gate.GateError, 'offset/length'):
            archive.inspect_archive(self.course, self.package())

    def test_hidden_archive_test_rejected(self):
        self.task['files']['test/LabTest.java']['is_visible'] = False
        with self.assertRaisesRegex(gate.GateError, 'hidden'):
            archive.inspect_archive(self.course, self.package())

    def test_unregistered_root_asset_rejected(self):
        package = self.package()
        with zipfile.ZipFile(package, 'a') as z:
            z.writestr('unlisted-answer-copy.txt', self.source_code)
        with self.assertRaisesRegex(gate.GateError, 'unexpected root asset'):
            archive.inspect_archive(self.course, package)

    def test_answer_payload_requires_string(self):
        self.task['files']['src/Lab.java']['placeholders'][0]['possible_answer'] = {'not': 'serialized-answer'}
        with self.assertRaisesRegex(gate.GateError, 'answer payload'):
            archive.inspect_archive(self.course, self.package())

    def test_new_archive_version_fails_closed(self):
        self.data['version'] = 24
        with self.assertRaisesRegex(gate.GateError, 'unsupported archive format'):
            archive.inspect_archive(self.course, self.package())

    def test_native_import_bytes_compared_without_modification(self):
        import shutil
        imported = self.root / 'native-import-fixture'
        shutil.copytree(self.course, imported)
        file = imported / 'sec/lesson/task/src/Lab.java'
        file.write_text(gate.replace_placeholders(self.source_code, [self.placeholder])[0])
        report = archive.inspect_archive(self.course, self.package(), imported)
        self.assertTrue(report['imported_plaintext'].startswith('PASS'))
        file.write_text(self.source_code)
        with self.assertRaisesRegex(gate.GateError, 'plaintext differs'):
            archive.inspect_archive(self.course, self.package(), imported)
        self.assertEqual(self.source_code, file.read_text())


if __name__ == '__main__':
    unittest.main()
