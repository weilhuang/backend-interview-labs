#!/usr/bin/env python3
"""由唯一镜像台账生成可独立导入的课程快照；--check 只读检查漂移。"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path

REPOSITORY = Path(__file__).resolve().parents[1]
COURSES = (
    "courses/data-storage/mysql-engineering",
    "courses/data-storage/redis-engineering",
    "courses/java-frameworks",
)

JAVA_READER = r'''package labs.environment;

import java.io.ByteArrayInputStream;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.HexFormat;
import java.util.Properties;

/** 自动生成的镜像台账读取器；版本值只能由仓库 infra/versions.env 生成。 */
public final class VersionLedger {
    private VersionLedger() {}

    public static Path locate() {
        String explicit = System.getProperty("lab.versions");
        if (explicit == null || explicit.isBlank()) explicit = System.getenv("LAB_SHARED_VERSIONS");
        // 兼容旧 Redis 学员副本；新说明统一使用 LAB_SHARED_VERSIONS。
        if (explicit == null || explicit.isBlank()) explicit = System.getenv("LAB_VERSIONS");
        if (explicit != null && !explicit.isBlank()) return requireFile(Path.of(explicit));
        String repository = System.getenv("LAB_REPO_ROOT");
        if (repository != null && !repository.isBlank()) {
            return requireFile(Path.of(repository).resolve("infra/versions.env"));
        }
        Path start = Path.of(System.getProperty("course.root", ".")).toAbsolutePath().normalize();
        Path snapshot = null;
        for (Path directory = start; directory != null; directory = directory.getParent()) {
            Path source = directory.resolve("infra/versions.env");
            if (Files.isRegularFile(source)) return source;
            Path candidate = directory.resolve("shared/versions.env");
            if (snapshot == null && Files.isRegularFile(candidate)) snapshot = candidate;
        }
        if (snapshot != null) return snapshot;
        throw new IllegalStateException("未找到镜像台账：请保留课程 shared 目录，或设置 LAB_SHARED_VERSIONS / LAB_REPO_ROOT");
    }

    private static Path requireFile(Path file) {
        Path normalized = file.toAbsolutePath().normalize();
        if (!Files.isRegularFile(normalized)) {
            throw new IllegalStateException("显式指定的镜像台账不存在，禁止静默回退：" + normalized);
        }
        return normalized;
    }

    public static String get(String key) {
        Path file = locate();
        try {
            byte[] bytes = Files.readAllBytes(file);
            verifySnapshot(file, bytes);
            Properties values = new Properties();
            try (var input = new ByteArrayInputStream(bytes)) {
                values.load(input);
            }
            String image = values.getProperty(key);
            if (image == null || image.isBlank() || image.matches(".*\\s+.*")
                    || image.endsWith(":latest") || (!image.contains(":") && !image.contains("@"))) {
                throw new IllegalStateException("镜像台账缺少固定版本键：" + key);
            }
            return image;
        } catch (IOException e) {
            throw new IllegalStateException("镜像台账读取失败：" + file, e);
        }
    }

    private static void verifySnapshot(Path file, byte[] bytes) throws IOException {
        Path checksum = file.resolveSibling(file.getFileName() + ".sha256");
        boolean snapshot = file.getParent().getFileName().toString().equals("shared")
                && file.getFileName().toString().equals("versions.env");
        if (!Files.isRegularFile(checksum)) {
            if (snapshot) throw new IllegalStateException("课程镜像快照缺少 SHA256：" + checksum);
            return;
        }
        String expected = Files.readString(checksum, StandardCharsets.UTF_8).trim().split("\\s+")[0];
        try {
            String actual = HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256").digest(bytes));
            if (!expected.matches("[0-9a-f]{64}") || !expected.equals(actual)) {
                throw new IllegalStateException("课程镜像快照 SHA256 不一致，请从原仓库重新生成：" + file);
            }
        } catch (NoSuchAlgorithmException e) {
            throw new IllegalStateException("JDK 不提供 SHA-256", e);
        }
    }
}
'''

GRADLE_READER = r'''// 由 scripts/sync_course_versions.py 生成；不要在课程内手写镜像版本。
import java.security.MessageDigest

String explicit = [System.getProperty('lab.versions'), System.getenv('LAB_SHARED_VERSIONS'), System.getenv('LAB_VERSIONS')].find { it != null && !it.isBlank() }
String repository = System.getenv('LAB_REPO_ROOT')
if (repository != null && repository.isBlank()) repository = null
File ledger = explicit ? file(explicit) : (repository ? new File(repository, 'infra/versions.env') : null)
File snapshot = rootProject.file('shared/versions.env')
boolean overridden = ledger != null
if (!ledger) {
    for (File directory = rootProject.projectDir; directory != null; directory = directory.parentFile) {
        File candidate = new File(directory, 'infra/versions.env')
        if (candidate.isFile()) { ledger = candidate; break }
    }
    if (!ledger) ledger = snapshot
}
if (!ledger.isFile()) throw new GradleException('镜像台账不存在，禁止静默回退：' + ledger)
ledger = ledger.canonicalFile

def sha256 = { File source -> MessageDigest.getInstance('SHA-256').digest(source.bytes).encodeHex().toString() }
File checksum = new File(ledger.parentFile, ledger.name + '.sha256')
boolean usingSnapshot = ledger.parentFile.name == 'shared' && ledger.name == 'versions.env'
if (usingSnapshot && !checksum.isFile()) throw new GradleException('课程镜像快照缺少 SHA256：' + checksum)
if (checksum.isFile()) {
    String expected = checksum.getText('UTF-8').trim().split(/\s+/)[0]
    if (!(expected ==~ /[0-9a-f]{64}/) || expected != sha256(ledger)) {
        throw new GradleException('课程镜像快照 SHA256 不一致，请从原仓库重新生成：' + ledger)
    }
}
if (!overridden && !usingSnapshot && snapshot.isFile() && sha256(snapshot) != sha256(ledger)) {
    throw new GradleException('课程快照与仓库真源已漂移，请在仓库根运行 python scripts/sync_course_versions.py')
}
Properties values = new Properties()
ledger.withInputStream { values.load(it) }
def requiredImage = { String key ->
    String image = values.getProperty(key)
    if (!image || image.trim() != image || image ==~ /.*\s+.*/ || image.endsWith(':latest') || (!image.contains(':') && !image.contains('@'))) {
        throw new GradleException('镜像台账缺少固定版本键：' + key)
    }
    image
}
def helperImages = [
    TESTCONTAINERS_RYUK_CONTAINER_IMAGE: requiredImage('TESTCONTAINERS_RYUK_IMAGE'),
    TESTCONTAINERS_TINYIMAGE_CONTAINER_IMAGE: requiredImage('TESTCONTAINERS_TINY_IMAGE')
]
rootProject.ext.courseVersionsFile = ledger
subprojects {
    pluginManager.withPlugin('java') {
        sourceSets.main.java.srcDir(rootProject.file('shared/src'))
    }
    tasks.withType(Test).configureEach {
        systemProperty 'lab.versions', ledger.absolutePath
        systemProperty 'course.root', rootProject.projectDir.absolutePath
        helperImages.each { variable, image -> environment variable, image }
        if (project.hasProperty('dockerApiVersion')) systemProperty 'api.version', project.property('dockerApiVersion')
    }
    tasks.withType(JavaExec).configureEach {
        systemProperty 'lab.versions', ledger.absolutePath
        systemProperty 'course.root', rootProject.projectDir.absolutePath
        helperImages.each { variable, image -> environment variable, image }
    }
}
tasks.register('verifyCourseVersions') {
    group = 'verification'
    description = '只读检查课程镜像台账、SHA256 和全部测试的辅助镜像配置，不启动 Docker'
    doLast {
        println '镜像台账：' + ledger
        println 'SHA256：' + sha256(ledger)
        values.stringPropertyNames().sort().each { key -> println key + '=' + requiredImage(key) }
        subprojects.each { child ->
            if (child.plugins.hasPlugin('java') && !child.sourceSets.main.java.srcDirs.contains(rootProject.file('shared/src'))) {
                throw new GradleException('课程镜像读取器未加入编译源目录：' + child.path)
            }
            child.tasks.withType(Test).each { task ->
                helperImages.each { variable, image ->
                    if (task.environment[variable] != image) throw new GradleException('测试辅助镜像未统一：' + task.path)
                }
                if (task.systemProperties['lab.versions'] != ledger.absolutePath) throw new GradleException('测试台账路径不一致：' + task.path)
            }
        }
    }
}
'''


SNAPSHOT_GUIDE = """# 独立课程镜像台账

本目录由仓库根的 `python scripts/sync_course_versions.py` 自动生成。唯一版本来源是 `infra/versions.env`，不是第二份人工维护的版本表。更新版本时先修改根台账，再重新生成并运行 `python scripts/sync_course_versions.py --check`。

## 源码仓库与独立包

- 完整仓库：Gradle 向父目录查找 `infra/versions.env`，并拒绝与课程快照不一致的版本
- 独立课程：保留本 `shared` 目录，直接读取 `versions.env`；同目录 `versions.env.sha256` 会校验内容，`source-manifest.json` 保留来源与 SHA256
- 清单和读取器都登记在课程 `course-info.yaml` 的 `additional_files`；生成教案或普通学员副本后仍须保留这些文件
- SHA256 检查发现误改或传输差异，不等于发布者数字签名，也不代表已核验镜像 digest、架构支持或安全漏洞

## 显式覆盖与错误边界

可设置 `LAB_SHARED_VERSIONS=/绝对路径/versions.env`，或 `LAB_REPO_ROOT=/完整仓库根目录`。优先级为 Gradle/JVM 的 `lab.versions` 系统属性、`LAB_SHARED_VERSIONS`、兼容旧 Redis 副本的 `LAB_VERSIONS`、`LAB_REPO_ROOT`、自动发现。显式路径不存在时立即失败，不回退到另一份台账。请使用绝对路径，避免不同工作目录造成含义变化。

Gradle 为全部 Test 和 JavaExec 任务传入同一解析后的路径，并从台账设置 `TESTCONTAINERS_RYUK_CONTAINER_IMAGE` 与 `TESTCONTAINERS_TINYIMAGE_CONTAINER_IMAGE`。直接在 IDE 启动 JUnit 而不通过 Gradle 时，也需要设置这两个辅助镜像环境变量；值读取本台账中的 `TESTCONTAINERS_RYUK_IMAGE` 和 `TESTCONTAINERS_TINY_IMAGE`，不能手写默认标签。推荐使用 Gradle 委托测试。

`verifyCourseVersions` 只做台账、校验和及测试配置检查，不启动容器。独立包不需要父仓库；首次 Gradle/Maven 依赖下载仍需要网络，离线构建需要预先准备相同依赖缓存。真实数据库/Redis 验收仍需要 Docker，快照读取通过不代表集成通过。

## 运行入口

源码仓库或普通源码分发目录保留 Wrapper 时，可在课程根运行 `./gradlew verifyCourseVersions`，再运行课程 README 中的具体检查任务。Academy 官方导出可能移除 `gradlew`、`gradlew.bat` 与 `gradle-wrapper.jar`；这类 ZIP 使用 IDE 的 Check/Run 或 Gradle 工具窗口，不要求目录中存在 `./gradlew`。原生插件导出与干净导入是否实测，仍以课程验收报告为准。
"""


def generated(source: bytes) -> dict[str, bytes]:
    digest = hashlib.sha256(source).hexdigest()
    manifest = {
        "source": "infra/versions.env",
        "sha256": digest,
        "generator": "scripts/sync_course_versions.py",
        "notice": "自动生成的独立课程快照；修改版本须先改仓库真源，再重新生成。SHA256 用于一致性检查，不是数字签名。",
    }
    return {
        "shared/README.md": SNAPSHOT_GUIDE.encode(),
        "shared/versions.env": source,
        "shared/versions.env.sha256": f"{digest}  versions.env\n".encode(),
        "shared/source-manifest.json": (json.dumps(manifest, ensure_ascii=False, indent=2) + "\n").encode(),
        "shared/versions.gradle": GRADLE_READER.encode(),
        "shared/src/labs/environment/VersionLedger.java": JAVA_READER.encode(),
    }


def registered_metadata(text: str, names: list[str]) -> str:
    if "additional_files:\n" not in text:
        raise ValueError("course-info.yaml 缺少 additional_files")
    present = set(re.findall(r"^- name: ([^\n]+)$", text, flags=re.MULTILINE))
    missing = [name for name in names if name not in present]
    return text.replace("additional_files:\n", "additional_files:\n" + "".join(f"- name: {name}\n" for name in missing), 1)


def sync(repository: Path, courses: tuple[str, ...], check: bool) -> list[str]:
    files = generated((repository / "infra/versions.env").read_bytes())
    errors = []
    for name in courses:
        course = repository / name
        if not (course / "course-info.yaml").is_file():
            raise ValueError(f"不是课程根目录：{course}")
        for relative, content in files.items():
            path = course / relative
            if check:
                if not path.is_file() or path.read_bytes() != content:
                    errors.append(str(path.relative_to(repository)))
            else:
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(content)
        metadata = course / "course-info.yaml"
        original = metadata.read_text(encoding="utf-8")
        updated = registered_metadata(original, list(files))
        if check and updated != original:
            errors.append(str(metadata.relative_to(repository)) + "：未登记全部快照文件")
        elif not check:
            metadata.write_text(updated, encoding="utf-8")
    return errors


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="只读核对真源、快照、读取器和 additional_files")
    parser.add_argument("--repo-root", type=Path, default=REPOSITORY)
    parser.add_argument("--course", action="append", choices=COURSES, help="只同步指定课程；默认同步三门")
    args = parser.parse_args()
    errors = sync(args.repo_root.resolve(), tuple(args.course or COURSES), args.check)
    if errors:
        raise SystemExit("课程镜像快照需要重新生成：\n" + "\n".join(errors))
    print("三门课程镜像快照与 SHA256 已核对" if args.check else "课程镜像快照已由唯一真源生成并登记")


if __name__ == "__main__":
    main()
