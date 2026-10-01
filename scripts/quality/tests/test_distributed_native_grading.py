"""Static wiring and report-scope guards; these do not prove a Gradle or IDEA run."""
from pathlib import Path
import importlib.util
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import academy_gate as gate
import distributed_integration_audit as audit

COURSE = gate.REPO / 'courses/distributed-systems'


class DistributedNativeGradingTests(unittest.TestCase):
    def test_default_test_includes_both_compiled_source_sets_only_for_real_regions(self):
        source = (COURSE / 'build.gradle').read_text()
        self.assertIn("def realGradingModule = project.name in ['06-transactions', '07-outbox-cache']", source)
        start = source.index("if (realGradingModule) tasks.named('test', Test)")
        end = source.index("tasks.register('integrationTest', Test)", start)
        block = source[start:end]
        self.assertIn("dependsOn tasks.named('integrationTestClasses')", block)
        self.assertIn('testClassesDirs = sourceSets.test.output.classesDirs + sourceSets.integrationTest.output.classesDirs', block)
        self.assertIn('classpath = sourceSets.test.runtimeClasspath + sourceSets.integrationTest.runtimeClasspath', block)
        for token in ('onlyIf', 'ignoreFailures', 'exclude', 'enabled = false'):
            self.assertNotIn(token, block)

    def test_auxiliary_images_and_api_version_cover_real_default_test(self):
        source = (COURSE / 'build.gradle').read_text()
        self.assertIn("if (name == 'integrationTest' || (name == 'test' && realGradingModule))", source)
        for token in ('TESTCONTAINERS_RYUK_IMAGE', 'TESTCONTAINERS_TINY_IMAGE',
                      'TESTCONTAINERS_RYUK_CONTAINER_IMAGE', 'TESTCONTAINERS_TINYIMAGE_CONTAINER_IMAGE',
                      "systemProperty 'api.version', project.property('dockerApiVersion')"):
            self.assertIn(token, source)
        workflow = (gate.REPO / '.github/workflows/distributed.yml').read_text()
        self.assertIn("    env:\n      ORG_GRADLE_PROJECT_dockerApiVersion: '1.44'", workflow)
        self.assertIn('--max-workers=1 test verificationClasspath --continue --console=plain', workflow)
        self.assertNotIn('unitTest verificationClasspath', workflow)
        self.assertIn("report['grading_task'] == 'test'", workflow)
        self.assertIn('timeout-minutes: 60', workflow)
        self.assertIn('--timeout 300 --total-timeout 900', workflow)

    def test_pure_quick_task_is_explicit_and_keeps_original_source_set(self):
        source = (COURSE / 'build.gradle').read_text()
        start = source.index("tasks.register('unitTest', Test)")
        end = source.index("if (realGradingModule)", start)
        block = source[start:end]
        self.assertIn('testClassesDirs = sourceSets.test.output.classesDirs', block)
        self.assertIn('classpath = sourceSets.test.runtimeClasspath', block)
        self.assertNotIn('sourceSets.integrationTest', block)
        self.assertIn("tasks.register('unitTest') { dependsOn subprojects.collect", source)
        self.assertIn("tasks.register('integrationTest') { dependsOn subprojects.collect", source)

    def test_contract_scope_keeps_each_task_rejection_and_exposes_all_four_gaps(self):
        model = gate.inspect_course(COURSE)
        goal, tasks, extra, uncovered = gate.suite_plan(model, 'contract')
        self.assertEqual('unitTest', goal)
        self.assertEqual([], extra)
        self.assertEqual([], uncovered)
        self.assertEqual(8, len(tasks))
        regions = {t['path'].split('/')[-1]: t.get('outside_contract_regions', []) for t in tasks}
        self.assertEqual(['DS-17'], regions['06-transactions'])
        self.assertEqual(['DS-19', 'DS-21', 'DS-22'], regions['07-outbox-cache'])
        self.assertEqual(4, sum(map(len, regions.values())))
        self.assertTrue(all('integration_required' not in t for t in tasks))

    def test_partial_scope_survives_xml_report_and_cannot_waive_environment_failure(self):
        task = {'path': 'distributed-course/services/06-transactions', 'outside_contract_regions': ['DS-17']}
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            folder = root / task['path'] / 'build/test-results/unitTest'
            folder.mkdir(parents=True)
            file = folder / 'TEST-Contract.xml'
            file.write_text('<testsuite tests="1" failures="1"><testcase name="contract"><failure type="java.lang.UnsupportedOperationException">java.lang.UnsupportedOperationException: 请按本步骤合同完成实现</failure></testcase></testsuite>')
            report = gate.collect_results(root, [task], 'unitTest', False)[0]
            self.assertEqual(['DS-17'], report['outside_contract_regions'])
            self.assertEqual('REQUIRED', report['rejection_contract'])
            file.write_text(file.read_text().replace('请按本步骤合同完成实现', 'Could not find a valid Docker environment'))
            with self.assertRaisesRegex(gate.GateError, 'infrastructure'):
                gate.collect_results(root, [task], 'unitTest', False)

    def test_old_integration_xml_cannot_satisfy_new_default_task_audit(self):
        case = audit.plan(gate.inspect_course(COURSE))[0]
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            old = root / case['task'] / 'build/test-results/integrationTest'
            old.mkdir(parents=True)
            (old / ('TEST-' + case['test_class'] + '.xml')).write_text('<testsuite tests="2" failures="0"/>')
            with self.assertRaisesRegex(audit.GateError, 'missing'):
                audit.validate_xml(root, case, False, 0)

    def test_generator_matches_changed_task_docs_without_source_or_metadata_drift(self):
        with tempfile.TemporaryDirectory() as temporary:
            clone = Path(temporary) / 'course'
            shutil.copytree(COURSE, clone, ignore=shutil.ignore_patterns(*gate.IGNORED))
            protected = list(clone.rglob('*.java')) + list(clone.rglob('gradle.lockfile')) + list(clone.rglob('task-info.yaml'))
            before = {p.relative_to(clone): p.read_bytes() for p in protected}
            expected_docs = {name: (clone / 'distributed-course/services' / name / 'task.md').read_bytes()
                             for name in ('06-transactions', '07-outbox-cache')}
            spec = importlib.util.spec_from_file_location('distributed_generator', clone / 'authoring/build_course.py')
            generator = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(generator)
            generator.finish()
            for rel, data in before.items():
                self.assertEqual(data, (clone / rel).read_bytes(), rel)
            for name, data in expected_docs.items():
                self.assertEqual(data, (clone / 'distributed-course/services' / name / 'task.md').read_bytes(), name)


if __name__ == '__main__':
    unittest.main()
