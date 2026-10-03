#!/usr/bin/env python3
"""Python-only C11-01..03 bridge regressions. Never launches Java, Gradle, Go, or Docker.

Run from an assembled root, or pass --source-root for the preserved input tree.
Gradle/JUnit source assertions below are wiring checks, not execution evidence.
"""
import argparse
import contextlib
import fnmatch
import importlib.util
import io
import json
import pathlib
import subprocess
import sys
import tempfile
import unittest
import yaml
from unittest.mock import patch

ROOT = pathlib.Path(__file__).resolve().parents[2]
SOURCE = ROOT
CHECKER = ROOT / 'materials/cloud-native/tests/check_task.py'
spec = importlib.util.spec_from_file_location('c11_bridge_checker', CHECKER)
checker = importlib.util.module_from_spec(spec)
spec.loader.exec_module(checker)


class StructuralContractTests(unittest.TestCase):
    def setUp(self):
        self.material = SOURCE / 'materials/cloud-native'
        self.direct = (self.material / 'answers/Dockerfile.exec').read_text()
        self.script = (self.material / 'answers/Dockerfile.exec-script').read_text()
        self.ignore = (self.material / '.dockerignore').read_text()
        self.entry = (self.material / 'container/entrypoint.sh').read_text()

    def validate(self, source=None, ignore=None, entry=None):
        return checker.validate(self.direct if source is None else source,
                                self.ignore if ignore is None else ignore,
                                self.entry if entry is None else entry)

    def reject(self, source, case=None):
        with self.assertRaises(checker.ContractViolation) as result:
            self.validate(source)
        if case:
            self.assertEqual(result.exception.case_id, case)

    def test_direct_reference_passes_eight_nonzero_cases(self):
        self.assertEqual(self.validate(), list(checker.EXPECTED_CASES))
        self.assertEqual(len(self.validate()), 8)

    def test_script_reference_passes(self):
        self.assertEqual(len(self.validate(self.script)), 8)

    def test_task_author_source_passes(self):
        task = SOURCE / 'c11-cloud-native/01-images/01-build-and-stop'
        self.assertEqual(checker.run('C11-01', task, self.material)['status'], 'PASS')

    def test_actual_learner_starter_fails(self):
        metadata = yaml.safe_load((SOURCE / 'c11-cloud-native/01-images/01-build-and-stop/task-info.yaml').read_text())
        item = next(item for item in metadata['files'] if item['name'] == 'Dockerfile')
        self.reject(item['placeholders'][0]['placeholder_text'], 'separate_build_runtime')

    def test_shared_starter_fails(self):
        self.reject((self.material / 'starter/Dockerfile').read_text(), 'separate_build_runtime')

    def test_root_user_fails(self):
        self.reject(self.direct.replace('USER 10001:10001', 'USER root'), 'non_root_runtime')

    def test_comment_is_not_an_executed_user(self):
        self.reject(self.direct.replace('USER 10001:10001', '# USER 10001:10001\nUSER root'), 'non_root_runtime')

    def test_default_image_bypasses_ledger_fails(self):
        self.reject(self.direct.replace('ARG JAVA_BUILD_IMAGE', 'ARG JAVA_BUILD_IMAGE=example:latest'), 'explicit_version_arguments')

    def test_runtime_build_image_fails(self):
        self.reject(self.direct.replace('FROM ${JAVA_RUNTIME_IMAGE}', 'FROM ${JAVA_BUILD_IMAGE}'), 'separate_build_runtime')

    def test_runtime_compiler_install_fails(self):
        self.reject(self.direct.replace('USER 10001:10001', 'RUN install-jdk\nUSER 10001:10001'), 'minimal_runtime_copies')

    def test_all_context_copy_fails(self):
        self.reject(self.direct.replace('USER 10001:10001', 'COPY . /opt/app/leak\nUSER 10001:10001'), 'minimal_runtime_copies')

    def test_missing_class_copy_fails(self):
        self.reject('\n'.join(line for line in self.direct.splitlines() if not line.startswith('COPY --from=')), 'minimal_runtime_copies')

    def test_duplicate_copy_fails(self):
        self.reject(self.direct.replace('USER 10001:10001', 'COPY --chown=10001:10001 web/ ./web/\nUSER 10001:10001'), 'minimal_runtime_copies')

    def test_shell_entrypoint_fails(self):
        self.reject(self.direct[:self.direct.index('ENTRYPOINT')] + 'ENTRYPOINT java -cp /opt/app/classes labs.CloudNativeApp\n', 'exec_entrypoint')

    def test_json_shell_wrapper_fails(self):
        self.reject(self.direct[:self.direct.index('ENTRYPOINT')] + 'ENTRYPOINT ["sh", "-c", "java -cp /opt/app/classes labs.CloudNativeApp"]\n', 'exec_entrypoint')

    def test_script_without_copied_entry_fails(self):
        self.reject(self.direct[:self.direct.index('ENTRYPOINT')] + 'ENTRYPOINT ["/opt/app/entrypoint.sh"]\n', 'exec_entrypoint')

    def test_script_without_exec_fails(self):
        with self.assertRaises(checker.ContractViolation) as result:
            self.validate(self.script, entry=self.entry.replace('exec java', 'java'))
        self.assertEqual(result.exception.case_id, 'exec_entrypoint')

    def test_later_user_override_fails(self):
        self.reject(self.direct + '\nUSER 0\n', 'non_root_runtime')

    def test_cmd_override_fails(self):
        self.reject(self.direct + '\nCMD ["unexpected"]\n', 'minimal_runtime_copies')

    def test_false_compile_comment_fails(self):
        self.reject(self.direct.replace('RUN mkdir', 'RUN echo mkdir'), 'bounded_build_instructions')

    def test_missing_port_or_signal_fails(self):
        for line in ('EXPOSE 8080', 'STOPSIGNAL SIGTERM'):
            with self.subTest(line=line):
                self.reject(self.direct.replace(line, ''), 'declared_port_and_signal')

    def test_secret_or_answer_allowlist_fails(self):
        for extra in ('!.env', '!answers/**', '!tests/**', '!wrong/**'):
            with self.subTest(extra=extra), self.assertRaises(checker.ContractViolation) as result:
                self.validate(ignore=self.ignore + '\n' + extra)
            self.assertEqual(result.exception.case_id, 'build_context_allowlist')

    def test_continuation_and_alternative_stage_name_pass(self):
        source = self.direct.replace('AS build', 'AS compiler').replace('--from=build', '--from=compiler')
        source = source.replace('&& javac', '&& \\\n  javac')
        self.assertEqual(len(self.validate(source)), 8)

    def test_empty_or_unterminated_source_fails(self):
        for source in ('', '# no instructions', 'ARG \\'):
            with self.subTest(source=source), self.assertRaises(checker.ContractViolation):
                self.validate(source)

    def test_unknown_task_and_missing_paths_are_invalid_environment(self):
        for task, taskdir in [('C11-99', SOURCE), ('C11-01', SOURCE / 'does-not-exist')]:
            with self.subTest(task=task), self.assertRaises(checker.InvalidEnvironment):
                checker.run(task, taskdir, self.material)

    def test_missing_or_oversized_input_is_invalid_environment(self):
        with tempfile.TemporaryDirectory() as folder:
            path = pathlib.Path(folder) / 'Dockerfile'
            with self.assertRaises(checker.InvalidEnvironment):
                checker.read_input(path)
            path.write_text(' ' * (checker.MAX_SOURCE_BYTES + 1))
            with self.assertRaises(checker.InvalidEnvironment):
                checker.read_input(path)

    def test_zero_or_partial_cases_are_never_pass(self):
        task = SOURCE / 'c11-cloud-native/01-images/01-build-and-stop'
        for cases in ([], ['non_root_runtime']):
            with self.subTest(cases=cases), patch.object(checker, 'validate', return_value=cases):
                with self.assertRaises(checker.InvalidEnvironment):
                    checker.run('C11-01', task, self.material)

    def test_cli_success_labels_structural_scope(self):
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            status = checker.main(['--task', 'C11-01', '--task-dir', str(SOURCE / 'c11-cloud-native/01-images/01-build-and-stop'), '--materials-dir', str(self.material)])
        self.assertEqual(status, 0)
        self.assertIn('cases=8 scope=STRUCTURAL_ONLY docker_runtime=NOT_RUN', output.getvalue())

    def test_cli_invalid_environment_has_nonzero_exit_and_no_pass_marker(self):
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            status = checker.main(['--task', 'C11-01', '--task-dir', '/definitely-not-a-course-directory', '--materials-dir', str(self.material)])
        self.assertEqual(status, 2)
        self.assertNotIn(checker.PASS_MARKER, output.getvalue())

    def test_python_optimized_mode_does_not_disable_assertions(self):
        # The only launched executable in these regressions is this Python interpreter.
        with tempfile.TemporaryDirectory() as folder:
            task = pathlib.Path(folder)
            (task / 'Dockerfile').write_text(self.direct.replace('USER 10001:10001', 'USER root'))
            result = subprocess.run([sys.executable, '-O', str(CHECKER), '--task', 'C11-01',
                                     '--task-dir', str(task), '--materials-dir', str(self.material)],
                                    capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn('non_root_runtime', result.stdout)
        self.assertNotIn(checker.PASS_MARKER, result.stdout)

    def test_cli_requires_explicit_paths(self):
        result = subprocess.run([sys.executable, str(CHECKER)], capture_output=True, text=True, timeout=10)
        self.assertNotEqual(result.returncode, 0)
        self.assertNotIn(checker.PASS_MARKER, result.stdout)


class BridgeWiringSourceTests(unittest.TestCase):
    """Static wiring inspection only. It does not certify Gradle or JVM execution."""
    def setUp(self):
        self.manifest = json.loads((ROOT / 'materials/cloud-native/gradle/bridge-inputs.json').read_text())
        self.gradle = (ROOT / 'materials/cloud-native/course.gradle').read_text()

    def test_only_three_expected_tasks_and_unique_projects(self):
        specs = self.manifest['tasks']
        self.assertEqual([row['task_id'] for row in specs], ['C11-01', 'C11-02', 'C11-03'])
        self.assertEqual(len({row['gradle_project'] for row in specs}), 3)
        for row in specs:
            self.assertEqual(row['gradle_project'], ':' + row['task_path'].replace('/', '-'))

    def test_sources_form_exactly_one_overlay_per_policy_task(self):
        shared = self.manifest['shared_main_files']
        self.assertEqual(len(shared), len(set(shared)))
        self.assertEqual(len(shared), 6)
        for row in self.manifest['tasks'][1:]:
            resolved = [(SOURCE / 'materials/cloud-native/src/labs' / name)
                        for name in shared if name != row['learner_java']]
            resolved.append(SOURCE / row['task_path'] / row['learner_java'])
            self.assertEqual(len(resolved), 6)
            self.assertEqual(len({file.name for file in resolved}), 6)
            self.assertTrue(all(file.is_file() for file in resolved))
            self.assertFalse(any('/answers/' in str(file) or '/starter/' in str(file) or '/wrong/' in str(file) for file in resolved))
        self.assertIn("expectedMain.findAll { it != spec.learner_java }", self.gradle)
        self.assertIn("duplicatesStrategy = DuplicatesStrategy.FAIL", self.gradle)
        self.assertIn("java.setSrcDirs([stagedMain])", self.gradle)
        self.assertIn("if (observed != expected)", self.gradle)

    def test_missing_compiled_bridge_and_zero_skipped_suite_fail_closed(self):
        self.assertIn("requireFile(new File(module.projectDir, 'test/LabCheckTest.java'))", self.gradle)
        self.assertIn("tasks.register('requireCloudNativeBridge')", self.gradle)
        self.assertIn("dependsOn(requireCompiledBridge)", self.gradle)
        self.assertIn("if (!present) throw new GradleException", self.gradle)
        self.assertIn("result.testCount == 0", self.gradle)
        self.assertNotIn("result.successfulTestCount == 0", self.gradle)  # Preserve ordinary failed-suite XML; Test fails it normally.
        self.assertIn("result.skippedTestCount > 0", self.gradle)
        self.assertIn("failOnNoMatchingTests = true", self.gradle)
        self.assertIn("timeout = Duration.ofSeconds(45)", self.gradle)
        self.assertIn("outputs.upToDateWhen { false }", self.gradle)
        self.assertIn("outputs.cacheIf { false }", self.gradle)

    def test_image_bridge_has_no_pipe_deadlock_and_bounded_timeout(self):
        path = self.manifest['tasks'][0]['task_path']
        source = (ROOT / path / 'test/LabCheckTest.java').read_text()
        self.assertIn('.redirectOutput(outputFile.toFile())', source)
        self.assertNotIn('getInputStream()', source)
        self.assertIn('process.waitFor(30, TimeUnit.SECONDS)', source)
        self.assertIn('process.descendants().forEach(ProcessHandle::destroyForcibly)', source)
        self.assertIn('process.destroyForcibly()', source)
        self.assertIn('assertEquals(8, Integer.parseInt(marker.group(1))', source)
        self.assertIn('docker_runtime=NOT_RUN', source)
        for key in ('course.taskDir', 'course.materialsDir', 'course.python', 'course.taskId'):
            self.assertIn('required("' + key + '")', source)

    def test_policy_bridges_call_existing_shared_contract(self):
        for row in self.manifest['tasks'][1:]:
            source = (ROOT / row['task_path'] / 'test/LabCheckTest.java').read_text()
            self.assertIn('labs.PolicyContractTest.main(new String[0]);', source)
            self.assertIn('"' + row['task_id'] + '"', source)
            self.assertIn('@Timeout(value = 10', source)
            self.assertNotIn('ProcessBuilder', source)
        self.assertIn('labs/PolicyContractTest.java', self.gradle)


def selected_suite(pattern='*'):
    suite = unittest.TestSuite()
    for cls in (StructuralContractTests, BridgeWiringSourceTests):
        for test in unittest.defaultTestLoader.loadTestsFromTestCase(cls):
            if fnmatch.fnmatch(test.id(), pattern):
                suite.addTest(test)
    if suite.countTestCases() == 0:
        raise RuntimeError('No C11 bridge regression tests selected; zero tests is not PASS')
    return suite


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-root', type=pathlib.Path, default=ROOT)
    parser.add_argument('--pattern', default='*')
    args = parser.parse_args()
    SOURCE = args.source_root.resolve()
    try:
        suite = selected_suite(args.pattern)
    except RuntimeError as error:
        parser.exit(2, str(error) + '\n')
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    sys.exit(0 if result.wasSuccessful() else 1)
