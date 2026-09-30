"""在无父仓库的临时目录验证快照、显式覆盖及拒绝漂移；不启动 Docker。"""
from __future__ import annotations

import importlib.util
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

SPEC = importlib.util.spec_from_file_location("course_versions", Path(__file__).resolve().parents[1] / "sync_course_versions.py")
versions = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(versions)


class SnapshotGenerationTest(unittest.TestCase):
    def test_generated_files_are_repeatable_and_detect_drift(self):
        with tempfile.TemporaryDirectory(prefix="课程台账生成-") as temporary:
            root = Path(temporary)
            (root / "infra").mkdir()
            (root / "infra/versions.env").write_text("MYSQL_IMAGE=mysql:8.4.7\n")
            course = root / "courses/example"
            course.mkdir(parents=True)
            (course / "course-info.yaml").write_text("type: marketplace\nadditional_files:\n- name: README.md\nyaml_version: 2\n")
            versions.sync(root, ("courses/example",), False)
            before = (course / "course-info.yaml").read_bytes()
            versions.sync(root, ("courses/example",), False)
            self.assertEqual(before, (course / "course-info.yaml").read_bytes())
            self.assertEqual([], versions.sync(root, ("courses/example",), True))
            (course / "shared/versions.env").write_text("MYSQL_IMAGE=mysql:0.0.0\n")
            self.assertIn("courses/example/shared/versions.env", versions.sync(root, ("courses/example",), True))
            (root / "infra/versions.env").write_text("MYSQL_IMAGE=mysql:8.4.8\n")
            self.assertGreaterEqual(len(versions.sync(root, ("courses/example",), True)), 3)

    def test_registration_does_not_duplicate_existing_names(self):
        original = "additional_files:\n- name: shared/versions.env\nyaml_version: 2\n"
        result = versions.registered_metadata(original, ["shared/versions.env", "shared/versions.env.sha256"])
        self.assertEqual(result.count("- name: shared/versions.env\n"), 1)
        self.assertIn("- name: shared/versions.env.sha256\n", result)


class JavaLedgerTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.build = tempfile.TemporaryDirectory(prefix="课程台账编译-")
        cls.classes = Path(cls.build.name)
        jdk = os.environ.get("JAVA_HOME")
        cls.java = str(Path(jdk) / "bin/java") if jdk else shutil.which("java")
        javac = str(Path(jdk) / "bin/javac") if jdk else shutil.which("javac")
        if not javac or not cls.java:
            raise RuntimeError("验证需要完整 JDK21，请设置 JAVA_HOME")
        source = cls.classes / "VersionLedger.java"
        source.write_text(versions.JAVA_READER)
        probe = cls.classes / "LedgerProbe.java"
        probe.write_text('import labs.environment.VersionLedger; public class LedgerProbe { public static void main(String[] args) { System.out.println(VersionLedger.get(args[0])); } }\n')
        subprocess.run([javac, "--release", "21", "-Xlint:all", "-Werror", "-d", str(cls.classes), str(source), str(probe)], check=True, capture_output=True, text=True, timeout=30)

    @classmethod
    def tearDownClass(cls):
        cls.build.cleanup()

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="无父仓库的课程-")
        self.root = Path(self.temporary.name)
        for relative, content in versions.generated(b"MYSQL_IMAGE=mysql:8.4.7\nREDIS_IMAGE=redis:7.4.7-alpine3.21\n").items():
            path = self.root / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(content)
        self.environment = dict(os.environ)
        for key in ("LAB_SHARED_VERSIONS", "LAB_REPO_ROOT", "LAB_VERSIONS", "JAVA_TOOL_OPTIONS", "JDK_JAVA_OPTIONS", "_JAVA_OPTIONS"):
            self.environment.pop(key, None)

    def tearDown(self):
        self.temporary.cleanup()

    def run_probe(self, key="MYSQL_IMAGE", properties=(), cwd=None):
        return subprocess.run([self.java, *properties, "-cp", str(self.classes), "LedgerProbe", key], cwd=cwd or self.root, env=self.environment, capture_output=True, text=True, timeout=10)

    def assert_image(self, expected, **kwargs):
        result = self.run_probe(**kwargs)
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual(expected, result.stdout.strip())

    def test_standalone_snapshot_works_from_nested_task(self):
        nested = self.root / "课程/第一节"
        nested.mkdir(parents=True)
        self.assert_image("mysql:8.4.7", cwd=nested)

    def test_course_root_property_works_from_unrelated_directory(self):
        self.assert_image("redis:7.4.7-alpine3.21", key="REDIS_IMAGE", cwd=self.classes, properties=[f"-Dcourse.root={self.root}"])

    def test_explicit_shared_ledger_overrides_snapshot(self):
        source = self.root / "override.env"
        source.write_text("MYSQL_IMAGE=mysql:8.4.8\n")
        self.environment["LAB_SHARED_VERSIONS"] = str(source)
        self.assert_image("mysql:8.4.8")

    def test_explicit_repository_overrides_snapshot(self):
        repository = self.root / "external"
        (repository / "infra").mkdir(parents=True)
        (repository / "infra/versions.env").write_text("MYSQL_IMAGE=mysql:8.4.8\n")
        self.environment["LAB_REPO_ROOT"] = str(repository)
        self.assert_image("mysql:8.4.8")

    def test_invalid_explicit_setting_never_falls_back(self):
        for variable in ("LAB_SHARED_VERSIONS", "LAB_REPO_ROOT", "LAB_VERSIONS"):
            with self.subTest(variable=variable):
                self.environment[variable] = str(self.root / "missing")
                result = self.run_probe()
                self.assertNotEqual(0, result.returncode)
                self.assertIn("禁止静默回退", result.stderr)
                del self.environment[variable]

    def test_system_property_is_same_resolved_ledger_used_by_gradle(self):
        source = self.root / "resolved.env"
        source.write_text("MYSQL_IMAGE=mysql:8.4.8\n")
        self.environment["LAB_SHARED_VERSIONS"] = str(self.root / "missing")
        self.assert_image("mysql:8.4.8", properties=[f"-Dlab.versions={source}"])

    def test_repository_truth_is_preferred_to_snapshot(self):
        (self.root / "infra").mkdir()
        (self.root / "infra/versions.env").write_text("MYSQL_IMAGE=mysql:8.4.8\n")
        self.assert_image("mysql:8.4.8")

    def test_changed_snapshot_is_rejected(self):
        (self.root / "shared/versions.env").write_text("MYSQL_IMAGE=mysql:8.4.8\n")
        result = self.run_probe()
        self.assertNotEqual(0, result.returncode)
        self.assertIn("SHA256 不一致", result.stderr)

    def test_missing_checksum_is_rejected(self):
        (self.root / "shared/versions.env.sha256").unlink()
        result = self.run_probe()
        self.assertNotEqual(0, result.returncode)
        self.assertIn("缺少 SHA256", result.stderr)

    def test_missing_key_and_unfixed_image_are_rejected(self):
        result = self.run_probe(key="MISSING_IMAGE")
        self.assertNotEqual(0, result.returncode)
        source = self.root / "override.env"
        self.environment["LAB_SHARED_VERSIONS"] = str(source)
        for value in ("mysql", "mysql:latest", "mysql:8.4.7 invalid"):
            with self.subTest(value=value):
                source.write_text("MYSQL_IMAGE=" + value + "\n")
                result = self.run_probe()
                self.assertNotEqual(0, result.returncode)
                self.assertIn("缺少固定版本键", result.stderr)

    def test_legacy_redis_override_remains_supported(self):
        source = self.root / "legacy.env"
        source.write_text("MYSQL_IMAGE=mysql:8.4.8\n")
        self.environment["LAB_VERSIONS"] = str(source)
        self.assert_image("mysql:8.4.8")


if __name__ == "__main__":
    unittest.main()
