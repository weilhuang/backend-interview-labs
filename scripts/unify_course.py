#!/usr/bin/env python3
"""从九份作者真源生成一个 Academy 课程；不改源文件，不下载，不运行 Java。"""
from __future__ import annotations
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import urllib.parse
import yaml
from unified_markdown import migrate, command_inventory, launcher_text

COURSES = ('java-foundations', 'java-concurrency', 'java-jvm', 'java-frameworks',
           'data-storage/mysql-engineering', 'data-storage/redis-engineering',
           'distributed-systems', 'messaging', 'backend-capstone')
IGNORE = {'build', '.gradle', '.idea', '__pycache__', '.git', 'node_modules'}
WRAPPER = {'gradlew', 'gradlew.bat', 'gradle/wrapper/gradle-wrapper.jar', 'gradle/wrapper/gradle-wrapper.properties'}
SCHEMA = 1

def digest(data): return hashlib.sha256(data).hexdigest()
def dump_json(value): return json.dumps(value, ensure_ascii=False, indent=2) + '\n'
def require(ok, message):
    if not ok: raise ValueError(message)
def load_module(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    return module

def properties(path):
    return dict(line.split('=', 1) for line in path.read_text().splitlines() if '=' in line and not line.startswith('#'))

# Gradle 8.10.2 Wrapper / pinned Academy WrapperInit preflight writes these
# eight keys in this order. This is a byte-line permutation, not a Properties
# parser/serializer: preserve values and escapes and reject unfamiliar syntax.
WRAPPER_PROPERTIES_ORDER = (
    b'distributionBase', b'distributionPath', b'distributionSha256Sum',
    b'distributionUrl', b'networkTimeout', b'validateDistributionUrl',
    b'zipStoreBase', b'zipStorePath',
)

def normalize_wrapper_properties(data):
    lines = {}
    for line in data.splitlines(keepends=True):
        match = re.fullmatch(rb'([A-Za-z][A-Za-z0-9]*)=([!-~]+)\n', line)
        require(match is not None, 'Wrapper properties: unsupported byte-line format')
        key, value = match.groups()
        require(key in WRAPPER_PROPERTIES_ORDER, 'Wrapper properties: unknown key ' + repr(key))
        require(key not in lines, 'Wrapper properties: duplicate key ' + repr(key))
        require((len(value) - len(value.rstrip(b'\\'))) % 2 == 0,
                'Wrapper properties: continuations are unsupported')
        lines[key] = line
    require(set(lines) == set(WRAPPER_PROPERTIES_ORDER), 'Wrapper properties: expected fixed eight-key schema')
    return b''.join(lines[key] for key in WRAPPER_PROPERTIES_ORDER)

def old_module(course_id, path):
    parts = path.split('/')
    if course_id in ('java-foundations', 'java-concurrency', 'java-jvm', 'mysql-engineering'):
        return '-'.join(parts)
    if course_id == 'redis-engineering': return ':'.join(parts)
    if course_id == 'messaging': return '-'.join(parts[:2])
    return parts[-1]

def validate_destinations(repo, output, environment=None, locks_dir=None, report=None):
    """Resolve before writing; a learner/output directory must never contain an input or vice versa."""
    repo = repo.resolve(); output = output.resolve()
    environment = (environment or repo / 'scripts/unified-environment').resolve()
    locks_dir = (locks_dir or repo / 'scripts/unified-dependency-locks').resolve()
    protected = [repo / 'courses' / name for name in COURSES] + [repo / 'scripts', repo / 'infra', environment, locks_dir]
    require(not output.exists(), '目标必须不存在，避免覆盖学习者作答：' + str(output))
    for source in protected:
        source = source.resolve()
        require(not output.is_relative_to(source) and not source.is_relative_to(output),
                '输出目录与输入目录必须互不包含：' + str(source))
    if report is not None:
        report = report.resolve()
        require(not report.exists(), '报告必须是独立新文件，拒绝覆盖：' + str(report))
        require(not report.is_relative_to(output) and not output.is_relative_to(report), '报告不能覆盖生成课程资产')
        for source in protected:
            require(not report.is_relative_to(source.resolve()), '报告不能写入输入目录')
        require(not report.is_relative_to(repo) or report.is_relative_to(repo / 'build'),
                '仓库内报告只能写到 build 下的独立新文件')
    return output

def inspect_sources(repo):
    sys.path.insert(0, str(repo / 'scripts/quality'))
    gate = load_module(repo / 'scripts/quality/academy_gate.py', 'unified_academy_gate')
    result = []
    for name in COURSES:
        root = repo / 'courses' / name
        model = gate.inspect_course(root)
        meta = gate.read_yaml(root / 'course-info.yaml')
        result.append((root, model, meta))
    require(sum(len(m['tasks']) for _, m, _ in result) == 84, 'V1 应完整保留 84 题')
    require(sum(len(p) for _, m, _ in result for p in m['placeholders'].values()) == 136, 'V1 应完整保留 136 个练习区')
    return gate, result

def mapping(sources):
    data = {'schema_version': SCHEMA, 'course_id': 'backend-interview', 'language': 'Chinese',
            'source_courses': [], 'sections': [], 'tasks': [], 'support_projects': []}
    paths = {}
    for root, model, meta in sources:
        cid = root.name
        sections = {}
        for name in meta['content']:
            section = 'redis-course' if cid == 'redis-engineering' else name
            target = 'redis-course/redis' if cid == 'redis-engineering' else name
            sections[name] = target
            data['sections'].append({'path': section, 'source_course': cid, 'source_path': name})
        data['source_courses'].append({'id': cid, 'source': 'courses/' + next(n for n in COURSES if Path(n).name == cid), 'sections': sections})
        for task in model['tasks']:
            first, *tail = task['path'].split('/')
            unified = '/'.join([sections[first], *tail])
            require(len(unified.split('/')) == 3, '统一课程必须为 section/lesson/task：' + unified)
            # Official GradleConfiguratorBase.getGradleProjectName: sanitized section-lesson-task.
            project = ':' + '-'.join(unified.split('/'))
            data['tasks'].append({'source_course': cid, 'source_task': task['path'], 'path': unified,
                                  'gradle_project': project, 'original_module': old_module(cid, task['path']),
                                  'placeholders': task['placeholders']})
        for support in ('common', 'support', 'benchmark'):
            if (root / support).is_dir() and (support != 'support' or cid in ('redis-engineering', 'distributed-systems', 'messaging')):
                data['support_projects'].append({'source_course': cid, 'original_module': support,
                    'gradle_project': f':{cid}-{support}', 'path': f'materials/{cid}/{support}',
                    'optional_property': 'withJmh' if support == 'benchmark' else None})
        for source in sorted(root.rglob('*')):
            if not source.is_file(): continue
            rel = source.relative_to(root)
            if IGNORE.intersection(rel.parts) or source.name == '.env' or source.name.endswith(('.log', '.pyc')): continue
            require(not source.is_symlink(), '作者文件不能是符号链接：' + str(source))
            name = rel.as_posix()
            if name in WRAPPER or name == 'course-info.yaml': continue
            if name in ('settings.gradle', 'gradle.properties', 'build.gradle'):
                target = f'authoring/source-builds/{cid}/{name}.txt'
            elif name.startswith('shared/') and name.split('/')[-1] in ('versions.env', 'versions.env.sha256', 'source-manifest.json', 'versions.gradle', 'VersionLedger.java'):
                continue
            else:
                first, *tail = rel.parts
                target = '/'.join([sections[first], *tail]) if first in sections else f'materials/{cid}/{name}'
            paths[source.resolve()] = target
    require(len({t['gradle_project'] for t in data['tasks']}) == 84, 'Gradle 任务名冲突')
    require(len({s['path'] for s in data['sections']}) == 11, '顶层章节冲突')
    return data, paths

def gradle_adapter(source, cid, course_map, source_properties):
    tasks = [x for x in course_map['tasks'] if x['source_course'] == cid]
    supports = [x for x in course_map['support_projects'] if x['source_course'] == cid]
    entries = tasks + supports
    modules = {x['original_module']: x['gradle_project'] for x in entries}
    sections = next(x['sections'] for x in course_map['source_courses'] if x['id'] == cid)
    text = source
    require("plugins { id 'base' }" in text, f'{cid}: 未知 plugins 声明')
    text = text.replace("plugins { id 'base' }", '')
    # Root aggregators must not create duplicate tasks; the unified root owns them.
    text = '\n'.join(line for line in text.splitlines() if not (
        re.match(r"tasks\.(register|named)\('(test|unitTest|integrationTest|check|wrapper)'", line) or
        line == "apply from: 'shared/versions.gradle'")) + '\n'
    text = text.replace('allprojects {', 'configure(courseProjects) {').replace('subprojects {', 'configure(courseProjects) {')
    text = text.replace('rootProject.file(', 'courseFile(')
    text = text.replace('rootProject.projectDir.absolutePath', 'courseDirectory.absolutePath')
    text = text.replace("rootProject.providers.gradleProperty('courseVersion').get()", repr(source_properties.get('courseVersion', '1.0.0')))
    text = text.replace("rootProject.property('courseVersion')", repr(source_properties.get('courseVersion', '1.0.0')))
    text = text.replace("rootProject.property('springBootVersion')", "rootProject.property('springBootVersion')")
    # project.name at project scope must refer to the original task/module name.
    text = text.replace('project.name', 'originalNames[project.path]')
    text = text.replace("if(name!='common'&&name!='benchmark')", "if(originalNames[project.path]!='common'&&originalNames[project.path]!='benchmark')")
    text = text.replace("if (name != 'support')", "if (originalNames[project.path] != 'support')")
    def replace_project(match):
        name = match.group(1)
        require(name in modules, f'{cid}: 未映射的项目引用 {name}')
        return "project('" + modules[name] + "')"
    text = re.sub(r"project\(':([^']+)'\)", replace_project, text)
    # Source root application used project.name as the stage key; references stay isolated.
    imports = '\n'.join(line for line in text.splitlines() if line.startswith('import '))
    text = '\n'.join(line for line in text.splitlines() if not line.startswith('import '))
    header = f'''// 自动派生自 courses/{next(n for n in COURSES if Path(n).name == cid)}/build.gradle；不要手改。
{imports}
def courseDirectory = rootProject.file('materials/{cid}')
def courseProjects = {repr([x['gradle_project'] for x in entries])}.collect {{ rootProject.findProject(it) }}.findAll {{ it != null }}
def originalNames = {repr({x['gradle_project']: x['original_module'].split(':')[-1] for x in entries}).replace('{', '[').replace('}', ']')}
def sectionPaths = {repr(sections).replace('{', '[').replace('}', ']')}
def courseFile = {{ Object raw ->
    String value = raw.toString()
    if (new File(value).isAbsolute()) return new File(value)
    if (value in ['shared/versions.env', '../../infra/versions.env']) return rootProject.file('shared/versions.env')
    if (value.startsWith('materials/')) return rootProject.file(value)
    String first = value.tokenize('/')[0]
    if (sectionPaths.containsKey(first)) return rootProject.file(sectionPaths[first] + value.substring(first.length()))
    return new File(courseDirectory, value)
}}
'''
    require("project(':support')" not in text and "project(':common')" not in text, f'{cid}: 支撑项目未隔离')
    return header + text

def rewrite_markdown(source, target, paths, output):
    text = source.read_text(encoding='utf-8')
    # Rewrite only actual local Markdown link destinations. Code samples stay source evidence.
    pattern = r'(?P<open>!?\[[^\]\n]*\]\()(?P<url><[^>]+>|[^\s)]+)(?P<tail>(?:\s+"[^"\n]*")?\))'
    def rewrite(match):
        value = match['url']; enclosed = value.startswith('<'); url = value[1:-1] if enclosed else value
        parsed = urllib.parse.urlsplit(url)
        if parsed.scheme or parsed.netloc or not parsed.path or parsed.path.startswith('/'): return match[0]
        old = (source.parent / urllib.parse.unquote(parsed.path)).resolve()
        dest = paths.get(old)
        if dest is None: return match[0]
        relative = Path(os.path.relpath(output / dest, (output / target).parent)).as_posix()
        new = urllib.parse.quote(relative, safe='/.-_~') + ('?' + parsed.query if parsed.query else '') + ('#' + parsed.fragment if parsed.fragment else '')
        return match['open'] + ('<' + new + '>' if enclosed else new) + match['tail']
    return re.sub(pattern, rewrite, text).encode()

def root_build(course_map):
    adapters = '\n'.join(f"apply from: 'materials/{x['id']}/course.gradle'" for x in course_map['source_courses'])
    return '''import java.security.MessageDigest
plugins { id 'base' }
// Native Check requires section-lesson-task project names, mapped by settings.gradle.
def expectedJava = providers.gradleProperty('javaVersion').get().toInteger()
if (JavaVersion.current().majorVersion.toInteger() != expectedJava) throw new GradleException('请使用 JDK ' + expectedJava + ' 导入统一课程')
def courseMap = new groovy.json.JsonSlurper().parse(file('authoring/course-map.json'))
''' + adapters + '''
project(':environment-ledger') {
    apply plugin: 'java-library'
    sourceSets.main.java.setSrcDirs(['src'])
}
Properties imageVersions = new Properties()
def ledger = file('shared/versions.env')
if (!ledger.isFile()) throw new GradleException('缺少统一镜像台账 shared/versions.env')
ledger.withInputStream { imageVersions.load(it) }
def ledgerSha = MessageDigest.getInstance('SHA-256').digest(ledger.bytes).encodeHex().toString()
if (file('shared/versions.env.sha256').text.trim().split(/\\s+/)[0] != ledgerSha) throw new GradleException('统一镜像台账 SHA256 不一致，请重新生成课程')
def helperImages = [TESTCONTAINERS_RYUK_CONTAINER_IMAGE: imageVersions.getProperty('TESTCONTAINERS_RYUK_IMAGE'), TESTCONTAINERS_TINYIMAGE_CONTAINER_IMAGE: imageVersions.getProperty('TESTCONTAINERS_TINY_IMAGE')]
subprojects {
    plugins.withId('java') {
        java { toolchain { languageVersion = JavaLanguageVersion.of(expectedJava) } }
        if (project.name != 'environment-ledger') dependencies { implementation project(':environment-ledger') }
        dependencyLocking { lockAllConfigurations(); lockFile = rootProject.file("dependency-locks/${project.name}.lockfile"); lockMode = LockMode.STRICT }
        tasks.withType(JavaCompile).configureEach { options.release = expectedJava; options.encoding = 'UTF-8' }
        tasks.withType(Test).configureEach {
            systemProperty 'lab.versions', ledger.absolutePath
            maxParallelForks = 1
            jvmArgs '-XX:ActiveProcessorCount=2'
            helperImages.each { key, value -> environment key, value }
        }
        tasks.withType(JavaExec).configureEach {
            systemProperty 'lab.versions', ledger.absolutePath
            helperImages.each { key, value -> environment key, value }
        }
    }
}
def taskProjects = courseMap.tasks.collect { project(it.gradle_project) }
tasks.register('test') {
    description = '执行所有原生判题；数据库及分布式重点题要求真实 Docker'
    dependsOn taskProjects.collect { it.tasks.named('test') }
}
tasks.register('unitTest') {
    description = '低内存局部快测；不能代替完整判题或 Docker 验收'
    dependsOn taskProjects.collect { it.tasks.findByName('unitTest') ?: it.tasks.named('test') }
}
tasks.register('fullCheck') {
    description = '完整验收：全部原生判题、框架与综合项目集成、消息真实服务'
    if (!project.hasProperty('withDocker') && gradle.startParameter.taskNames.any { it in ['fullCheck', ':fullCheck', 'check', ':check'] }) throw new GradleException('完整验收须加 -PwithDocker，不能把消息快测算作服务验收')
    dependsOn tasks.named('test')
    dependsOn taskProjects.findAll { it.tasks.findByName('integrationTest') != null && !(it.name in ['distributed-course-services-06-transactions', 'distributed-course-services-07-outbox-cache']) }.collect { it.tasks.named('integrationTest') }
}
tasks.named('check') { dependsOn tasks.named('fullCheck') }
tasks.register('verifyCourseVersions') {
    description = '检查唯一镜像台账及所有 Java 测试的环境配置，不启动容器'
    doLast {
        println '镜像台账：' + ledger + '；SHA256：' + ledgerSha
        imageVersions.each { key, value ->
            if (!value || value.endsWith(':latest') || (!value.contains(':') && !value.contains('@'))) throw new GradleException('非固定镜像：' + key)
        }
        taskProjects.each { module -> module.tasks.withType(Test).each { test ->
            if (test.systemProperties['lab.versions'] != ledger.absolutePath) throw new GradleException('镜像台账未统一：' + test.path)
            helperImages.each { key, value -> if (test.environment[key] != value) throw new GradleException('辅助镜像未统一：' + test.path) }
        } }
    }
}
tasks.register('verifyDependencyLocks') {
    description = '核对当前所有模块都有统一依赖锁，不联网、不运行容器'
    doLast { subprojects.each { module ->
        def lock = rootProject.file("dependency-locks/${module.name}.lockfile")
        if (!lock.isFile()) throw new GradleException('缺少统一依赖锁：' + lock)
    } }
}
tasks.register('resolveAndLockAll') {
    description = '显式解析所有课程类路径；配合 --write-locks 生成完整锁，不运行测试/容器'
    doLast { subprojects.each { module -> module.configurations.findAll { it.canBeResolved }.each { it.resolve() } } }
}
tasks.register('validateTeachingCommands') {
    description = '按实际 Gradle 模型检查所有题面命令，不执行调用方或容器'
    doLast {
        def commands = new groovy.json.JsonSlurper().parse(file('authoring/teaching-command-map.json')).commands.values().flatten().unique()
        commands.each { command ->
            int separator = command.lastIndexOf(':')
            def module = findProject(command.substring(0, separator))
            if (module == null || module.tasks.findByName(command.substring(separator + 1)) == null) throw new GradleException('题面命令不存在：' + command)
        }
        println '已核对 ' + commands.size() + ' 条唯一题面 Gradle 命令；未执行运行目标'
    }
}
tasks.register('writeCourseModel') {
    description = '导出实际 Gradle 模型供路径、原生判题和重复类检查'
    doLast {
        def rows = courseMap.tasks.collect { item ->
            def module = project(item.gradle_project)
            def grading = module.tasks.named('test').get()
            [path: item.path, gradle_project: module.path,
             main_sources: module.sourceSets.main.java.files.collect { rootProject.relativePath(it) }.sort(),
             test_sources: module.sourceSets.test.java.files.collect { rootProject.relativePath(it) }.sort(),
             integration_sources: module.sourceSets.findByName('integrationTest')?.java?.files?.collect { rootProject.relativePath(it) }?.sort() ?: [],
             grading_classes: grading.testClassesDirs.files.collect { rootProject.relativePath(it) }.sort(),
             root: module.projectDir.absolutePath]
        }
        def destination = layout.buildDirectory.file('course-model.json').get().asFile
        destination.parentFile.mkdirs()
        destination.text = groovy.json.JsonOutput.prettyPrint(groovy.json.JsonOutput.toJson(rows)) + System.lineSeparator()
    }
}
tasks.named('wrapper') { gradleVersion = '8.10.2'; distributionType = Wrapper.DistributionType.BIN }
defaultTasks 'help'
'''

def build(repo, output, environment=None, locks_dir=None):
    output = validate_destinations(repo, output, environment, locks_dir)
    environment = environment or repo / 'scripts/unified-environment'
    locks_dir = locks_dir or repo / 'scripts/unified-dependency-locks'
    gate, sources = inspect_sources(repo)
    wrapper_source = sources[0][0] / 'gradle/wrapper/gradle-wrapper.properties'
    normalized_wrapper = normalize_wrapper_properties(wrapper_source.read_bytes())
    wrapper_baseline = properties(wrapper_source)
    for root, _, _ in sources:
        wrapper = properties(root / 'gradle/wrapper/gradle-wrapper.properties')
        for key in ('distributionUrl', 'distributionSha256Sum'):
            require(wrapper.get(key) == wrapper_baseline.get(key), '源课程 Wrapper 不一致：' + str(root))
    require(wrapper_baseline['distributionUrl'].endswith('gradle-8.10.2-bin.zip'), 'V1 Wrapper 基线发生变化，须显式升级合并合同')
    spring_boot = properties(repo / 'courses/java-frameworks/gradle.properties')['springBootVersion']
    require('spring-boot-dependencies:' + spring_boot in (repo / 'courses/backend-capstone/build.gradle').read_text(), '框架与综合项目的 Spring Boot 基线发生冲突')
    course_map, paths = mapping(sources)
    require(environment.is_dir(), '缺少统一环境模板目录：' + str(environment))
    for name in ('scripts/lab.py', 'scripts/lab.sh', 'scripts/gradle.sh', 'scripts/gradle_launcher.py', 'scripts/environment_profiles.py', 'scripts/generate_environment_docs.py', 'infra/compose.yaml', 'infra/capstone.compose.yaml', 'docs/统一环境.md'):
        require((environment / name).is_file(), '统一环境模板缺文件：' + name)
    expected_locks = [x['gradle_project'][1:] + '.lockfile' for x in course_map['tasks'] + course_map['support_projects']] + ['environment-ledger.lockfile']
    require(all((locks_dir / name).is_file() for name in expected_locks), '统一依赖锁必须完整包含所有 90 个模块（含可选 JMH）')
    output.mkdir(parents=True)
    provenance = []
    def write(name, data):
        path = output / name; path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data.encode() if isinstance(data, str) else data)
        if path.suffix == '.sh': path.chmod(0o755)
    for source, target in paths.items():
        data = rewrite_markdown(source, target, paths, output) if source.suffix == '.md' else source.read_bytes()
        source_root = next(root for root, _, _ in sources if source.is_relative_to(root))
        if source.suffix == '.md': data = migrate(data.decode(), source_root.name, source_root, course_map, source.relative_to(source_root).as_posix()).encode()
        if source.suffix == '.py' and source.parent.name == 'scripts':
            adapted = data.decode()
            for section in next(x['sections'] for x in course_map['source_courses'] if x['id'] == source_root.name):
                for variable in ('R', 'ROOT'):
                    adapted = adapted.replace(variable + "/'" + section, variable + ".parents[1]/'" + section)
            data = adapted.encode()
        write(target, data)
        provenance.append({'source': source.relative_to(repo).as_posix(), 'path': target,
                           'source_sha256': digest(source.read_bytes()), 'sha256': digest(data),
                           'transformation': ('teaching-command-and-path-migration' if source.suffix == '.md' else 'diagnostic-script-path-adapter') if data != source.read_bytes() else 'identity'})
    for name in WRAPPER:
        write(name, normalized_wrapper if name == 'gradle/wrapper/gradle-wrapper.properties'
              else (sources[0][0] / name).read_bytes())
    provenance.append({'source': wrapper_source.relative_to(repo).as_posix(),
                       'path': 'gradle/wrapper/gradle-wrapper.properties',
                       'source_sha256': digest(wrapper_source.read_bytes()),
                       'sha256': digest(normalized_wrapper),
                       'transformation': 'gradle-8.10.2-wrapper-property-line-order'})
    (output / 'gradlew').chmod(0o755)
    # One standalone ledger generated by the existing canonical source generator.
    version_generator = load_module(repo / 'scripts/sync_course_versions.py', 'unified_version_generator')
    generated = version_generator.generated((repo / 'infra/versions.env').read_bytes())
    for name, data in generated.items():
        if not name.endswith('versions.gradle'): write(name, data)
    write('shared/README.md', '''# 统一课程镜像台账

发行包只有本目录的 versions.env 一份可执行镜像台账，versions.env.sha256 检查传输或误改。统一 Gradle 和 scripts/lab.py 直接读取它；不会向父仓库查找另一个台账，也不支持用另一份环境变量配置静默覆盖。

Java 读取器保留原作者实现以保证课程代码兼容；通过本课 Gradle 启动的全部 Test/JavaExec 都显式传入这份统一文件及 Ryuk/tinyimage 辅助镜像。请使用 Gradle 委托检查。独立在IDE运行JUnit时必须显式配置同一文件和辅助镜像，不能把环境缺失算作答案错误。

维护版本属于作者工作：在完整仓库修改 infra/versions.env 后运行 scripts/unify_course.py 重新生成总课。该维护脚本不在本发行目录内；学习者不需要原作者仓库。SHA256不是发布者签名，也不是镜像安全、架构或真实容器验收证明。

源码和官方导入均可运行 bash scripts/gradle.sh verifyCourseVersions 和 bash scripts/lab.sh images；官方Academy归档可能移除Wrapper程序，导入后使用IDE的Check/Run或Gradle工具窗口。实际Docker与原生导入状态请看总课验收说明。
''')
    # Existing section/lesson/task contents retain their native hierarchy.
    write('redis-course/section-info.yaml', yaml.safe_dump({'custom_name': 'C07 Redis 与缓存一致性', 'content': ['redis']}, allow_unicode=True, sort_keys=False))
    for root, _, _ in sources:
        adapter = gradle_adapter((root / 'build.gradle').read_text(), root.name, course_map, properties(root / 'gradle.properties'))
        write(f'materials/{root.name}/course.gradle', adapter)
    benchmark = output / 'materials/java-foundations/benchmark/build.gradle'
    benchmark.write_text(benchmark.read_text().replace("project(':common')", "project(':java-foundations-common')"))
    # Its section-lesson-task name is already equal to its original name.
    projects = course_map['tasks'] + course_map['support_projects']
    settings = ["// 从统一映射生成。原生 Academy Check 使用 section-lesson-task 名。", "rootProject.name = 'backend-interview'", "include('environment-ledger')", "project(':environment-ledger').projectDir = file('shared')"]
    for project in projects:
        line = f"include('{project['gradle_project'][1:]}'); project('{project['gradle_project']}').projectDir = file('{project['path']}')"
        if project.get('optional_property'): line = "if (startParameter.projectProperties.containsKey('withJmh')) { " + line + " }"
        settings.append(line)
    write('settings.gradle', '\n'.join(settings) + '\n')
    write('gradle.properties', 'javaVersion=21\nspringBootVersion=' + spring_boot + '\ncourseVersion=1.0.0-unified-draft\norg.gradle.jvmargs=-Xmx384m -XX:ActiveProcessorCount=2 -Dfile.encoding=UTF-8\norg.gradle.workers.max=1\norg.gradle.parallel=false\norg.gradle.daemon=false\n')
    write('build.gradle', root_build(course_map))
    # Consolidate active locks at one root; original task files remain immutable provenance.
    for project in projects:
        source_lock = output / project['path'] / 'gradle.lockfile'
        lock_name = project['gradle_project'][1:] + '.lockfile'
        verified_lock = locks_dir / lock_name
        if verified_lock.is_file(): write('dependency-locks/' + lock_name, verified_lock.read_bytes())
        elif source_lock.is_file(): write('dependency-locks/' + lock_name, source_lock.read_bytes())
    env_lock = locks_dir / 'environment-ledger.lockfile'
    if env_lock.is_file(): write('dependency-locks/environment-ledger.lockfile', env_lock.read_bytes())
    for entry in provenance:
        current = (output / entry['path']).read_bytes()
        if digest(current) != entry['sha256']:
            entry['sha256'] = digest(current)
            entry['transformation'] = 'gradle-project-reference'
    commands = {}
    known = {x['gradle_project'] for x in course_map['tasks'] + course_map['support_projects']}
    for page in sorted(output.rglob('*.md')):
        if 'authoring' in page.relative_to(output).parts: continue
        commands[page.relative_to(output).as_posix()] = command_inventory(page.read_text())
        require(all(command.rsplit(':', 1)[0] in known for command in commands[page.relative_to(output).as_posix()]), '教学命令仍包含未知 Gradle 模块：' + str(page))
    write('authoring/teaching-command-map.json', dump_json({'schema_version': 1, 'commands': commands,
        'known_legacy_display_messages': ['messaging Usage.java 的原样输出', 'JVM Java25EvidenceUsage.java 的原样输出'],
        'native_execution': 'NOT_RUN'}))
    write('authoring/course-map.json', dump_json(course_map))
    write('authoring/source-provenance.json', dump_json({'schema_version': SCHEMA, 'generator': 'scripts/unify_course.py', 'files': provenance}))
    dependencies = []
    for root, _, _ in sources:
        for coordinate in sorted(set(re.findall(r"['\"]([\w.-]+:[\w.-]+:[\w.+-]+)['\"]", (root / 'build.gradle').read_text()))):
            dependencies.append({'source_course': root.name, 'coordinate': coordinate})
    locks = [{'path': p.relative_to(output).as_posix(), 'sha256': digest(p.read_bytes())} for p in sorted(output.rglob('gradle.lockfile'))]
    write('authoring/dependency-ledger.json', dump_json({'schema_version': SCHEMA, 'gradle': '8.10.2', 'jdk': 21,
          'spring_boot': spring_boot, 'declared_dependencies': dependencies, 'source_lockfiles': locks, 'active_lock_directory': 'dependency-locks',
          'resolution_verification': 'NOT_RUN', 'note': '保留原始锁；统一图及尚无锁的课程必须在 JDK21 窗口中实际解析并生成，不能凭静态检查宣称通过。'}))
    write('.gitignore', '.gradle/\n.idea/\n**/build/\n**/__pycache__/\ninfra/.env\n')
    write('.courseignore', '.gradle/**\n.idea/**\n**/build/**\n**/__pycache__/**\ninfra/.env\n')
    write('README.md', launcher_text(README))
    write('docs/合并设计与验收.md', launcher_text(DESIGN))
    # Include the proven metadata/UTF-16/materialization gate, without a second implementation.
    for name in ('academy_gate.py', 'process_runner.py'):
        write('authoring/quality/' + name, (repo / 'scripts/quality' / name).read_bytes())
    write('authoring/materialize_learner.py', MATERIALIZE)
    write('authoring/requirements.txt', 'PyYAML==6.0.2\n')
    if environment.is_dir():
        for asset in sorted(environment.rglob('*')):
            if not asset.is_file() or IGNORE.intersection(asset.relative_to(environment).parts) or asset.name == '.env': continue
            require(not asset.is_symlink(), '环境模板不能是符号链接：' + str(asset))
            write(asset.relative_to(environment).as_posix(), asset.read_bytes())
        subprocess.run([sys.executable, str(output / 'scripts/generate_environment_docs.py')], check=True, cwd=output)
        subprocess.run([sys.executable, str(output / 'scripts/lab.py'), 'verify'], check=True, cwd=output)
    active_locks = [{'path': p.relative_to(output).as_posix(), 'sha256': digest(p.read_bytes())} for p in sorted((output / 'dependency-locks').glob('*.lockfile'))]
    dep = json.loads((output / 'authoring/dependency-ledger.json').read_text())
    dep['active_lockfiles'] = active_locks
    dep['lock_inventory_complete'] = len(active_locks) == len(projects) + 1
    dep['resolution_verification'] = 'LOCKS_PRESENT_REVERIFY_REQUIRED' if dep['lock_inventory_complete'] else 'INCOMPLETE'
    write('authoring/dependency-ledger.json', dump_json(dep))
    # Every non-task file is explicit so native archive export cannot silently omit it.
    refresh_metadata(output, course_map)
    model = gate.inspect_course(output)
    require(len(model['tasks']) == 84 and sum(len(p) for p in model['placeholders'].values()) == 136, '生成后内容计数变化')
    protected = [p for p in provenance if p['path'].endswith(('.java', 'task-info.yaml', 'gradle.lockfile'))]
    require(all(p['source_sha256'] == p['sha256'] for p in protected), 'Java/占位/源依赖锁不允许静默变化')
    return {'status': 'PASS', 'kind': 'static-only', 'courses': 1, 'source_courses': 9,
            'sections': 11, 'tasks': 84, 'placeholders': 136, 'assets': len(model['assets']),
            'protected_files': len(protected), 'native_idea': 'NOT_RUN', 'gradle': 'NOT_RUN', 'docker': 'NOT_RUN'}

def refresh_metadata(output, course_map):
    task_dirs = [output / t['path'] for t in course_map['tasks']]
    additional = []
    for path in sorted(output.rglob('*')):
        if not path.is_file() or IGNORE.intersection(path.relative_to(output).parts): continue
        if path.name.endswith('-info.yaml') or path.name == 'course-info.yaml': continue
        if any(path.is_relative_to(t) for t in task_dirs): continue
        entry = {'name': path.relative_to(output).as_posix()}
        if path.suffix in ('.jar', '.png', '.jpg', '.zip'): entry['is_binary'] = True
        additional.append(entry)
    metadata = {'type': 'marketplace', 'title': 'Java 后端面试实验室：完整 V1 统一课程', 'language': 'Chinese',
        'summary': '一个入口、11 个章节、84 个编码任务与 136 个练习区；完整项目、调用方、测试、答案、源码路线和前端保留。环境按需启动，合并后的原生验收状态见说明。',
        'programming_language': 'Java', 'content': [s['path'] for s in course_map['sections']],
        'environment_settings': {'jvm_language_level': 'JDK_21'}, 'additional_files': additional, 'yaml_version': 2}
    (output / 'course-info.yaml').write_text(yaml.safe_dump(metadata, allow_unicode=True, sort_keys=False), encoding='utf-8')

README = '''# Java 后端面试实验室：完整 V1 统一课程

这是一个课程入口，包含原 9 份课程的 11 个章节、84 个任务和 136 个练习区。

## 使用方式

在 IntelliJ IDEA 2026.1.5、JetBrains Academy 2026.9-2026.1-1070 中打开本课程根，使用 JDK 21。
每次只打开当前任务并点击 Check。数据库、缓存、消息与分布式重点任务需要 Docker；环境按需启动，不要同时启动所有服务。

容器题首次运行或切换 Docker 配置后，先执行对应 profile 的 `bash scripts/lab.sh doctor <profile>`。本地 Docker 端点门禁只覆盖统一 CLI（含其 check）；直接 Gradle 或 Academy Check 仍按原 Testcontainers 配置解析，不能据此宣称所有入口均有远端隔离。

- 编码恢复和集合：c00、c01
- 并发与 JVM：juc、jvm
- Spring Boot 与 Spring：framework-course
- MySQL、Redis：mysql、redis-course
- 分布式、Kafka、RocketMQ：distributed-course、kafka、rocketmq
- 综合项目：capstone

所有原始调用方、公开测试、直接可读答案、源码指南、前端和诊断材料仍在本课程内。非任务材料按来源放在 materials 下。

## 一个构建入口

源码目录与官方 Academy 导入都使用随包的 `bash scripts/gradle.sh`，不依赖被官方剔除的 gradlew、gradlew.bat 或 wrapper.jar。首次可显式运行 `bash scripts/gradle.sh prepare --download`；已有官方发行ZIP可用 `prepare --zip /绝对路径/gradle-8.10.2-bin.zip`。运行时只从已校验缓存或明确的 LAB_GRADLE_BIN 取得，不搜索浮动PATH，也不会自动下载。缓存位于课程树外，不会打进课程包。LAB_GRADLE_BIN只核版本，来源仍须由你独立信任。Linux/macOS是本启动器目标；Windows CLI尚未实测。

- ./gradlew verifyCourseVersions：只读核对镜像台账，不启动容器
- ./gradlew :juc-01-publication-lab:test：只检查一道题；完整模块名见 authoring/course-map.json
- ./gradlew unitTest：全部局部快测，不能作为完整真实服务验收
- ./gradlew fullCheck -PwithDocker：完整判题与真实服务验收，按一个 Gradle worker 顺序执行
- ./gradlew resolveAndLockAll --write-locks -PwithJmh：显式解析全部依赖并生成锁，不启动测试/容器

源码作者版保留正确实现，由 Academy 占位生成学习者 TODO。普通目录可运行 `python authoring/materialize_learner.py ../backend-interview-learner` 生成学习副本；这不是官方 Academy 导出。

## 验证边界

本次静态合并不等于原生通过。JDK 21 构建、全部依赖图、单次官方导出/干净导入、Check/Reset 和 Docker 集成均须对统一课程重新验收，不能继承分课的旧绿结果。

参见 [统一环境与按题检查](docs/统一环境.md)、[题目环境映射](docs/题目环境映射.md)和[合并设计与验收](docs/合并设计与验收.md)。
'''
DESIGN = '''# 合并设计与验收

## 单一真源

原 9 个作者项目是维护真源。仓库 scripts/unify_course.py 复用既有 Academy 元数据检查器和镜像快照生成器，派生本目录。不要分别修改两份课程。
原作者构建脚本及版本配置留在 authoring/source-builds 供溯源；materials 内原作者脚本是来源资料，维护时应在原项目运行后重新生成，不应把其旧路径当作本课入口。

## 内容与项目隔离

采用官方 course → section → lesson → task 结构。Redis 原来是顶层 lesson，合并后用 redis-course section 包装。
每题独立 Java source set 和 Gradle module，不把重复的 labs.Usage、Exercise 或测试类合进一个类路径。Gradle 名按官方 section-lesson-task 算法生成。支撑模块使用来源前缀。
C14 每阶段仍只引用其余四份正确参考源，保留原来的五目录隔离修复。
C10 第 06、07 题的原生 test 仍包含真实服务 integrationTest 类，unitTest 仅供局部快测。

## 环境与依赖

JDK 版本统一写在根 gradle.properties，Wrapper 8.10.2 保留官方 SHA256。
发行内只保留 shared/versions.env 一份镜像台账，它来自仓库 infra/versions.env；所有测试使用同一路径和 Ryuk/tinyimage 辅助镜像。
各原项目的依赖约束与原始锁文件原样保留供溯源。实际构建统一从 dependency-locks 读取按模块隔离的锁，记录于 authoring/dependency-ledger.json。框架 BOM 与独立 JUnit 图按模块隔离，不能为了表面统一而强制改写已验证的依赖版本。
只用一个 Gradle worker，测试进程一个 fork；默认任务是帮助，不会自动启动任何容器。

## 合并门禁

1. 原始 Java、task-info 占位与依赖锁逐文件 SHA256 保真
2. 9 → 1 课程映射、11 sections、84 tasks、136 regions、全部 additional_files 完整性
3. 84 个唯一官方 Gradle 项目名，以及支撑依赖和原项目路径适配
4. JDK21 实际 Gradle projects/testClasses、解析全部配置并生成/核查锁；局部单测不替代真实集成
5. 官方 Academy 单个 ZIP 导出、干净导入、84 题与 136 区显示、Check 正反解/Reset、C10 Docker 缺失显式失败、C14 无重复类
6. 本课完整真实容器验收；最终报告保留未运行、环境失败与代码失败区别

当前 4–6 尚未运行；先前各分课验收不能替代本次统一包证据。
'''
MATERIALIZE = '''#!/usr/bin/env python3
"""生成普通学习目录，不冒充官方 Academy ZIP。"""
import argparse, shutil, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent / 'quality'))
from academy_gate import inspect_course, make_learner
p=argparse.ArgumentParser(description=__doc__);p.add_argument('destination',type=Path);a=p.parse_args()
r=Path(__file__).resolve().parents[1];d=a.destination.resolve()
if d.exists() or r.is_relative_to(d) or d.is_relative_to(r): p.error('目标必须是不存在且与课程根互不包含的独立新目录')
m=inspect_course(r)
shutil.copytree(r,d,ignore=shutil.ignore_patterns('build','.gradle','.idea','__pycache__'))
make_learner(m,d)
print('已生成普通学习目录：',d)
print('仍须独立执行官方导出、导入、Check 与 Reset 验收。')
'''

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--repo', type=Path, default=Path(__file__).resolve().parents[1])
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--report', type=Path)
    p.add_argument('--environment-template-dir', type=Path)
    p.add_argument('--dependency-locks-dir', type=Path)
    a=p.parse_args()
    validate_destinations(a.repo, a.output, a.environment_template_dir, a.dependency_locks_dir, a.report)
    result=build(a.repo.resolve(),a.output.resolve(),a.environment_template_dir,a.dependency_locks_dir)
    if a.report:
        a.report.parent.mkdir(parents=True, exist_ok=True)
        with a.report.open('x', encoding='utf-8') as stream: stream.write(dump_json(result))
    print(dump_json(result))
if __name__=='__main__': main()
