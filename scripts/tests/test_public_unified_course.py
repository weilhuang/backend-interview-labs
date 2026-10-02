"""Public source-builder and multi-language learner projection regressions.

No Java, Go, Docker or IDE execution. Negative controls exercise static gates.
"""
from pathlib import Path
import copy
import importlib.util
import json
import re
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.dont_write_bytecode = True
REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / 'scripts'))
import build_unified_course as builder

class PublicUnifiedCourseTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.root = Path(cls.temp.name)
        cls.output = cls.root / 'course'
        cls.report = builder.build(REPO, cls.output)
        sys.path.insert(0, str(cls.output / 'authoring/quality'))
        spec = importlib.util.spec_from_file_location('public_gate_test', cls.output / 'authoring/quality/academy_gate.py')
        cls.gate = importlib.util.module_from_spec(spec); spec.loader.exec_module(cls.gate)
        cls.model = cls.gate.inspect_course(cls.output)
        cls.inputs = json.loads((REPO / 'authoring/unified-course/manifest.json').read_text())

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def clone(self):
        root = self.root / ('fixture-' + self._testMethodName)
        shutil.copytree(self.output, root)
        return root

    def clone_inputs(self):
        root = self.root / ('inputs-' + self._testMethodName)
        shutil.copytree(REPO / 'authoring/unified-course', root / 'authoring/unified-course')
        return root

    def test_exact_output_manifest_and_counts(self):
        self.assertEqual(builder.manifest(self.output), self.inputs['expected_manifest'])
        self.assertEqual(self.report['counts'], builder.COUNTS)
        self.assertEqual(self.report['source_files'], 1726)
        self.assertEqual(self.report['full_manifest_sha256'], self.inputs['full_manifest_sha256'])

    def test_second_fresh_build_is_byte_identical(self):
        output = self.root / 'second-course'
        report = builder.build(REPO, output)
        self.assertEqual(builder.manifest(output), builder.manifest(self.output))
        self.assertEqual(report, self.report)

    def test_existing_output_is_never_overwritten(self):
        before = builder.manifest(self.output)
        with self.assertRaisesRegex(ValueError, 'must not exist'):
            builder.build(REPO, self.output)
        self.assertEqual(before, builder.manifest(self.output))

    def test_reject_changed_overlay(self):
        root = self.clone_inputs(); p=root/'authoring/unified-course/overlay/README.md';p.write_text('unreviewed')
        with self.assertRaisesRegex(ValueError, 'exact allowlist'):builder.load_inputs(root)

    def test_reject_extra_overlay_file(self):
        root=self.clone_inputs();(root/'authoring/unified-course/overlay/extra.txt').write_text('extra')
        with self.assertRaisesRegex(ValueError, 'exact allowlist'):builder.load_inputs(root)

    def test_reject_missing_overlay_file(self):
        root=self.clone_inputs();(root/'authoring/unified-course/overlay/README.md').unlink()
        with self.assertRaisesRegex(ValueError, 'exact allowlist'):builder.load_inputs(root)

    def test_reject_overlay_symlink(self):
        root=self.clone_inputs();p=root/'authoring/unified-course/overlay/README.md';p.unlink();p.symlink_to(self.output/'README.md')
        with self.assertRaisesRegex(ValueError, 'Symlink'):builder.load_inputs(root)

    def test_reject_traversal_and_ambiguous_names(self):
        for name in ('../outside','a/../b','/absolute','a\\b','a//b','a/./b','a/'):
            with self.subTest(name=name), self.assertRaises(ValueError):builder.safe_name(name)

    def test_reject_wrong_expected_manifest_digest(self):
        root=self.clone_inputs();p=root/'authoring/unified-course/manifest.json';m=json.loads(p.read_text());m['full_manifest_sha256']='0'*64;p.write_text(json.dumps(m))
        with self.assertRaisesRegex(ValueError, 'not sealed'):builder.load_inputs(root)

    def test_all_editable_regions_materialize_without_other_byte_changes(self):
        learner=self.clone();before=builder.manifest(learner)
        hashes=self.gate.make_learner(self.model, learner)
        self.assertEqual(len(hashes),110)
        after=builder.manifest(learner)
        self.assertEqual({name for name in before if before[name]!=after[name]},set(hashes))
        for name, regions in self.model['placeholders'].items():
            source=(self.output/name).read_text();actual=(learner/name).read_text()
            expected,_=self.gate.replace_placeholders(source,regions)
            self.assertEqual(actual,expected)
            # Independently construct the UTF-16 splice, including unchanged boundaries.
            raw=source.encode('utf-16-le');parts=[];cursor=0
            for region in sorted(regions,key=lambda p:p['offset']):
                start=region['offset']*2;end=start+region['length']*2
                parts.extend([raw[cursor:start],region['placeholder_text'].encode('utf-16-le')]);cursor=end
            parts.append(raw[cursor:]);self.assertEqual(actual.encode('utf-16-le'),b''.join(parts))
        self.assertEqual(sum(len(v) for v in self.model['placeholders'].values()),159)

    def test_utf16_surrogate_split_rejected(self):
        with self.assertRaises(self.gate.GateError):
            self.gate.replace_placeholders('A😀B',[{'offset':2,'length':1,'placeholder_text':'x'}])

    def test_overlapping_regions_rejected(self):
        with self.assertRaises(self.gate.GateError):
            self.gate.replace_placeholders('abcdef',[{'offset':1,'length':3,'placeholder_text':'x'},{'offset':2,'length':2,'placeholder_text':'y'}])

    def test_unknown_editable_path_rejected(self):
        root=self.clone();p=root/'authoring/public-build-contract.json';c=json.loads(p.read_text());c['editable_files']['not-a-task/file.go']=1;p.write_text(json.dumps(c))
        with self.assertRaisesRegex(self.gate.GateError,'inventory mismatch'):self.gate.inspect_course(root)

    def test_wrong_editable_count_rejected(self):
        root=self.clone();p=root/'authoring/public-build-contract.json';c=json.loads(p.read_text());key=next(iter(c['editable_files']));c['editable_files'][key]+=1;p.write_text(json.dumps(c))
        with self.assertRaisesRegex(self.gate.GateError,'outside the explicit contract'):self.gate.inspect_course(root)

    def test_missing_public_contract_does_not_silently_allow_other_languages(self):
        root=self.clone();(root/'authoring/public-build-contract.json').unlink()
        with self.assertRaises(self.gate.GateError):self.gate.inspect_course(root)

    def test_all_100_tasks_have_direct_source_reference(self):
        mapping=json.loads((self.output/'authoring/course-map.json').read_text())
        for task in mapping['tasks']:
            text=re.sub(r'```.*?```','',(self.output/task['path']/'task.md').read_text(),flags=re.S)
            self.assertTrue(re.findall(r'!?\[[^\]\n]*\]\((https?://[^\s)]+)\)',text),task['path'])

    def test_no_private_machine_paths_in_generated_source(self):
        for p in self.output.rglob('*'):
            if p.is_file():
                data=p.read_bytes()
                for marker in (b'/workspace/shared/',b'/home/agent/',b'/root/.codex/',b'13622993145@'):
                    self.assertNotIn(marker,data,p.relative_to(self.output))

    def test_no_runtime_result_is_inferred_from_static_pass(self):
        for key in ('native_idea','gradle','go','docker','full_course_runtime'):
            self.assertEqual(self.report[key],'NOT_RUN')

if __name__ == '__main__':unittest.main()
