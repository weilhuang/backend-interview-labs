"""Guard C14's directory-level source model; no Java/Gradle/IDE is launched.

Gradle compile-only file exclusions previously let all tests pass while IDEA
indexed a second definition of each learner target. These checks intentionally
pin the supported declarative root selection, then inspect those actual roots.
A different Gradle source-wiring design must update this contract explicitly.
"""
from collections import Counter
import json
from pathlib import Path
import re
import unittest

import yaml

COURSE = Path(__file__).resolve().parents[3] / 'courses/backend-capstone'


class CapstoneSourceRootTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.manifest = json.loads((COURSE / 'authoring/manifest.json').read_text())
        cls.gradle = (COURSE / 'build.gradle').read_text()

    def assert_directory_selection(self, source):
        compact = re.sub(r'\s+', ' ', source)
        self.assertIn(
            'def referenceSourceDirs = targets.keySet().findAll { it != project.name } '
            '.collect { rootProject.file("reference/${it}/src") }', compact,
            'Select the four other reference directories before adding source roots')
        self.assertIn(
            "main { java.srcDirs = ['src', rootProject.file('app/src/main/java')] "
            '+ referenceSourceDirs resources.srcDirs', compact,
            'The learner and four completed classes must be represented by distinct roots')
        self.assertEqual(1, len(re.findall(r'\bsourceSets\s*\{', source)),
                         'Keep source roots in the single checked sourceSets block')
        self.assertEqual(3, len(re.findall(r'\bjava\.srcDirs\b', source)),
                         'Only main, test and integrationTest may declare Java roots once')
        self.assertEqual(2, len(re.findall(r'\breferenceSourceDirs\b', source)),
                         'Do not append to or mutate the selected reference directories')
        self.assertNotIn('reference/src', source, 'Do not index the legacy all-answers root')
        self.assertNotRegex(source, r'\bjava\.(?:srcDir|setSrcDirs|exclude|include)\b',
                            'Do not replace directory membership with compiler-only filters')
        self.assertNotRegex(source, r'sourceSets\s*\.\s*main\s*\.\s*java',
                            'Keep main Java root mutations in the checked sourceSets block')

    def test_gradle_selects_only_other_stage_roots(self):
        self.assert_directory_selection(self.gradle)
        mapping = re.search(r'def targets\s*=\s*\[([^\]]+)\]', self.gradle).group(1)
        targets = dict(re.findall(r"'([^']+)'\s*:\s*'([^']+)'", mapping))
        self.assertEqual({r['module']: r['target'] for r in self.manifest}, targets)

    def test_original_compiler_only_exclusion_is_rejected(self):
        old_model = self.gradle.replace(
            "java.srcDirs = ['src', rootProject.file('app/src/main/java')] + referenceSourceDirs",
            "java.srcDirs = ['src', rootProject.file('app/src/main/java')]\n"
            "            java.srcDir rootProject.file('reference/src')\n"
            "            java.exclude { item -> item.file.name == targets[project.name] + '.java' "
            "&& item.file.path.contains('/reference/') }")
        self.assertNotEqual(self.gradle, old_model)
        with self.assertRaises(AssertionError):
            self.assert_directory_selection(old_model)

    def test_appended_same_stage_reference_root_is_rejected(self):
        appended_root = self.gradle + '\nsubprojects { sourceSets { main { java.srcDirs += ' \
            '[rootProject.file("reference/${project.name}/src")] } } }\n'
        with self.assertRaises(AssertionError):
            self.assert_directory_selection(appended_root)

    def test_mutating_selected_reference_directories_is_rejected(self):
        mutated_roots = self.gradle.replace(
            '    sourceSets {',
            '    referenceSourceDirs += [rootProject.file("reference/${project.name}/src")]\n'
            '    sourceSets {', 1)
        self.assertNotEqual(self.gradle, mutated_roots)
        with self.assertRaises(AssertionError):
            self.assert_directory_selection(mutated_roots)

    def test_five_reference_implementations_are_separate_visible_assets(self):
        course = yaml.safe_load((COURSE / 'course-info.yaml').read_text())
        declared = {f['name'] for f in course['additional_files']}
        expected = set()
        self.assertEqual(5, len(self.manifest))
        for row in self.manifest:
            relative = f"reference/{row['module']}/src/labs/capstone/{row['target']}.java"
            expected.add(relative)
            self.assertIn(relative, declared)
            learner = COURSE / f"capstone/stages/{row['module']}/src/labs/capstone/{row['target']}.java"
            self.assertEqual(learner.read_bytes(), (COURSE / relative).read_bytes())
        actual = {p.relative_to(COURSE).as_posix() for p in (COURSE / 'reference').rglob('*.java')}
        self.assertEqual(expected, actual)
        self.assertFalse((COURSE / 'reference/src').exists())

    def test_each_main_model_has_one_target_and_no_duplicate_class(self):
        self.assert_directory_selection(self.gradle)
        for row in self.manifest:
            with self.subTest(stage=row['module']):
                learner = COURSE / f"capstone/stages/{row['module']}/src"
                roots = [learner, COURSE / 'app/src/main/java'] + [
                    COURSE / f"reference/{other['module']}/src"
                    for other in self.manifest if other['module'] != row['module']]
                self.assertTrue(all(root.is_dir() for root in roots))
                sources = [file for root in roots for file in root.rglob('*.java')]
                classes = Counter()
                for file in sources:
                    package = re.search(r'(?m)^package ([\w.]+);', file.read_text())
                    self.assertIsNotNone(package, file)
                    classes[package.group(1) + '.' + file.stem] += 1
                self.assertEqual({}, {name: count for name, count in classes.items() if count > 1})
                target_files = [f for f in sources if f.name == row['target'] + '.java']
                self.assertEqual([learner / 'labs/capstone' / (row['target'] + '.java')], target_files)
                self.assertIn('labs.capstone.Usage', classes)
                self.assertTrue(all('labs.capstone.' + r['target'] in classes for r in self.manifest))

    def test_nine_regions_still_belong_to_visible_learner_targets(self):
        regions = 0
        for row in self.manifest:
            task = COURSE / 'capstone/stages' / row['module']
            metadata = yaml.safe_load((task / 'task-info.yaml').read_text())
            targets = [f for f in metadata['files'] if f.get('placeholders')]
            self.assertEqual([f"src/labs/capstone/{row['target']}.java"], [f['name'] for f in targets])
            self.assertTrue(all(f['visible'] for f in metadata['files']))
            regions += sum(len(f['placeholders']) for f in targets)
        self.assertEqual(9, regions)


if __name__ == '__main__':
    unittest.main()
