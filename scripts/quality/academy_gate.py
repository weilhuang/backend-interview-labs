#!/usr/bin/env python3
"""Repository-specific Academy authoring contract and real Gradle round-trip gate.

The ZIP created here is a test fixture, NOT a JetBrains Academy archive. No IDE
is launched. The native exporter/importer, Check UI and Reset UI remain separate.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import stat
import subprocess
import sys
import time
import tempfile
import xml.etree.ElementTree as ET
import zipfile

import yaml

from process_runner import check_support, run_logged

REPO = Path(__file__).resolve().parents[2]
IGNORED = {'build', '.gradle', '.idea', '__pycache__', '.git'}
SCHEMA = 1
CONTRACT_INTEGRATION_REQUIRED = {
    'redis-engineering': {
        'redis/04-consistency': 'Editable consistency publication uses real Redis/MySQL; unit tests do not reject its empty body',
        'redis/05-replication': 'Editable replica promotion calls Redis; pure INFO parsing tests do not reject its empty body',
        'redis/06-leases': 'Editable lease operations call Redis; pure fencing model tests do not reject its empty body',
    }
}
CONTRACT_UNCOVERED_REGIONS = {
    'distributed-systems': {
        'distributed-course/services/06-transactions': ['DS-17'],
        'distributed-course/services/07-outbox-cache': ['DS-19', 'DS-21', 'DS-22'],
    }
}
INTEGRATION_OBSERVATIONS = {
    'backend-capstone': {
        'capstone/stages/04-recovery':
            'RecoveryIntegrationTest restarts MySQL through RealServices; it does not call the editable RecoveryPolicy. The contract/unit gate owns rejection.'
    }
}


class GateError(Exception):
    """An unmet release contract, never an expected learner failure."""


class UniqueLoader(yaml.SafeLoader):
    """Reject duplicate YAML keys rather than silently keeping the last one."""


def unique_mapping(loader, node, deep=False):
    result = {}
    for key, value in node.value:
        name = loader.construct_object(key, deep=deep)
        if name in result:
            raise GateError(f'duplicate YAML key: {name}')
        result[name] = loader.construct_object(value, deep=deep)
    return result


UniqueLoader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, unique_mapping)


def require(condition, message):
    if not condition:
        raise GateError(message)


def read_yaml(path):
    with path.open(encoding='utf-8') as stream:
        value = yaml.load(stream, Loader=UniqueLoader)
    require(isinstance(value, dict), f'{path}: expected YAML mapping')
    return value


def digest(data):
    return hashlib.sha256(data).hexdigest()


def relative_path(name):
    require(isinstance(name, str) and bool(name), f'invalid path: {name!r}')
    path = PurePosixPath(name)
    require(not path.is_absolute() and '\\' not in name and ':' not in name
            and all(part not in ('', '.', '..') for part in name.split('/')),
            f'unsafe or noncanonical path: {name!r}')
    return path


def local_file(root, name):
    path = root / relative_path(name)
    require(path.resolve().is_relative_to(root.resolve()), f'path escapes root: {name}')
    require(not any(p.is_symlink() for p in [path, *path.parents] if p != root.parent),
            f'symlinks are unsupported in course assets: {name}')
    require(path.is_file(), f'missing declared asset: {path}')
    return path


def replace_placeholders(source, placeholders):
    """IntelliJ offsets count UTF-16 code units, not Python Unicode code points."""
    raw = source.encode('utf-16-le')
    previous_end = 0
    spans = []
    for p in placeholders:
        start, length, text = p.get('offset'), p.get('length'), p.get('placeholder_text')
        require(type(start) is int and type(length) is int and length > 0,
                'placeholder offset/length must be integers with positive length')
        end = start + length
        require(start >= previous_end and end * 2 <= len(raw), 'overlapping, unsorted or out-of-range placeholder')
        require(isinstance(text, str) and bool(text.strip()), 'placeholder_text must be nonempty text')
        try:
            answer = raw[start * 2:end * 2].decode('utf-16-le')
            raw[:start * 2].decode('utf-16-le')
            raw[end * 2:].decode('utf-16-le')
        except UnicodeDecodeError as error:
            raise GateError('placeholder splits a UTF-16 surrogate pair') from error
        require(answer != text, 'learner placeholder is identical to reference answer')
        spans.append((start, end, text, answer))
        previous_end = end
    for start, end, text, _ in reversed(spans):
        raw = raw[:start * 2] + text.encode('utf-16-le') + raw[end * 2:]
    return raw.decode('utf-16-le'), [span[3] for span in spans]


def inspect_course(root):
    root = root.resolve()
    meta = read_yaml(root / 'course-info.yaml')
    require(meta.get('programming_language') == 'Java', 'this gate currently supports Java courses only')
    require(meta.get('environment_settings', {}).get('jvm_language_level') == 'JDK_21', 'JDK_21 metadata required')
    assets = {'course-info.yaml'}
    tasks = []
    all_ph = {}

    def walk(directory, config):
        content = config.get('content')
        require(isinstance(content, list) and content, f'{directory}: empty/missing content')
        require(all(isinstance(name, str) for name in content) and len(content) == len(set(content)),
                f'{directory}: duplicate/non-string content')
        for name in content:
            relative_path(name)
            require('/' not in name, f'content child must be one directory: {name}')
            child = directory / name
            found = [child / (kind + '-info.yaml') for kind in ('section', 'lesson', 'task')
                     if (child / (kind + '-info.yaml')).is_file()]
            require(len(found) == 1, f'{child}: missing or ambiguous section/lesson/task metadata')
            file = found[0]
            local_file(root, file.relative_to(root).as_posix())
            assets.add(file.relative_to(root).as_posix())
            data = read_yaml(file)
            if file.name != 'task-info.yaml':
                require(data.get('type') != 'framework', f'{child}: framework lessons require a dedicated stateful gate')
                walk(child, data)
                continue
            require(data.get('type') == 'edu', f'{child}: unsupported task type {data.get("type")!r}')
            desc = child / 'task.md'
            local_file(root, desc.relative_to(root).as_posix())
            assets.add(desc.relative_to(root).as_posix())
            description = desc.read_text(encoding='utf-8')
            require(description.strip(), f'{child}: empty task description')
            entries = data.get('files', [])
            names = [f.get('name') for f in entries]
            require(names and all(isinstance(n, str) for n in names) and len(names) == len(set(names)),
                    f'{child}: missing or duplicate task files')
            visible_answers = [description]
            for entry in entries:
                file_path = local_file(child, entry['name'])
                require(entry.get('visible') is True, f'{file_path}: public course task asset must be visible')
                assets.add(file_path.relative_to(root).as_posix())
                if any(token in entry['name'].lower() for token in ('answer', 'solution')):
                    visible_answers.append(file_path.read_text(encoding='utf-8'))
            placeholders = 0
            for entry in entries:
                ph = entry.get('placeholders', [])
                if not ph:
                    continue
                file_path = child / entry['name']
                require(entry['name'].startswith('src/') and entry['name'].endswith('.java'),
                        f'{file_path}: only editable Java source placeholders supported')
                source = file_path.read_text(encoding='utf-8')
                learner, answers = replace_placeholders(source, ph)
                require(learner != source, f'{file_path}: learner source unchanged')
                require(any(all(a.strip() in answer for a in answers) for answer in visible_answers),
                        f'{file_path}: exact reference segments missing from public task description/answer asset')
                all_ph[file_path.relative_to(root).as_posix()] = ph
                placeholders += len(ph)
            require(placeholders > 0, f'{child}: edu task has no learner placeholders')
            require(any(n.startswith('test/') and n.endswith('.java') for n in names), f'{child}: no declared tests')
            for path in child.rglob('*'):
                rel = path.relative_to(child)
                if path.is_file() and not IGNORED.intersection(rel.parts):
                    require(rel.as_posix() in names or rel.as_posix() in ('task.md', 'task-info.yaml', 'task-remote-info.yaml'),
                            f'{path}: undeclared task asset would disappear from the package')
            tasks.append({'path': child.relative_to(root).as_posix(), 'placeholders': placeholders})

    walk(root, meta)
    additional = [entry.get('name') for entry in meta.get('additional_files', [])]
    require(all(isinstance(n, str) for n in additional) and len(additional) == len(set(additional)),
            'duplicate or invalid additional_files')
    for name in additional:
        local_file(root, name)
        require(name not in assets, f'additional file duplicates task/metadata asset: {name}')
        assets.add(name)
    required = ('build.gradle', 'settings.gradle', 'gradle.properties', 'gradlew',
                'gradle/wrapper/gradle-wrapper.jar', 'gradle/wrapper/gradle-wrapper.properties')
    require(all(name in assets for name in required), 'Gradle runtime/wrapper files are not fully declared')
    # Reject orphan tasks that a manifest-only validator would silently omit.
    actual_tasks = {p.parent.relative_to(root).as_posix() for p in root.rglob('task-info.yaml')
                    if not IGNORED.intersection(p.relative_to(root).parts)}
    require(actual_tasks == {t['path'] for t in tasks}, 'orphan or multiply referenced task metadata')
    return {'root': root, 'tasks': tasks, 'assets': sorted(assets), 'placeholders': all_ph}


def discover(repo, names):
    base = repo / 'courses'
    if names:
        roots = [base / relative_path(name) for name in names]
    else:
        roots = sorted(p.parent for p in base.rglob('course-info.yaml')
                       if not IGNORED.intersection(p.relative_to(base).parts))
    require(bool(roots), 'no courses found')
    require(len(roots) == len(set(roots)), 'duplicate course selector')
    for root in roots:
        require(root.resolve().is_relative_to(base.resolve()), 'course selector escapes courses/')
    return roots


def pack_fixture(model, output):
    """A deterministic, explicit-source fixture; deliberately no course.json."""
    manifest = {}
    with zipfile.ZipFile(output, 'x', zipfile.ZIP_DEFLATED) as archive:
        for name in model['assets']:
            data = local_file(model['root'], name).read_bytes()
            entry = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            entry.external_attr = (stat.S_IFREG | 0o644) << 16
            archive.writestr(entry, data, compress_type=zipfile.ZIP_DEFLATED)
            manifest[name] = digest(data)
    return manifest


def unpack_fixture(archive_path, destination, expected):
    require(not destination.exists(), f'refusing to overwrite import destination: {destination}')
    with zipfile.ZipFile(archive_path) as archive:
        files = archive.infolist()
        require(len(files) == len({f.filename for f in files}), 'duplicate archive member')
        require({f.filename for f in files} == set(expected), 'archive asset manifest mismatch')
        require(sum(f.file_size for f in files) <= 128 * 1024 * 1024, 'fixture exceeds 128 MiB uncompressed limit')
        for entry in files:
            relative_path(entry.filename)
            require(stat.S_IFMT(entry.external_attr >> 16) in (0, stat.S_IFREG), 'non-regular archive member')
            require(digest(archive.read(entry)) == expected[entry.filename], f'archive content mismatch: {entry.filename}')
        destination.mkdir(parents=True)
        for entry in files:
            target = destination / entry.filename
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(archive.read(entry))
    (destination / 'gradlew').chmod(0o755)


def make_learner(model, directory):
    hashes = {}
    for name, ph in model['placeholders'].items():
        file = directory / name
        learner, _ = replace_placeholders(file.read_text(encoding='utf-8'), ph)
        file.write_text(learner, encoding='utf-8')
        hashes[name] = digest(file.read_bytes())
    return hashes


def suite_plan(model, suite):
    name = model['root'].name
    if suite == 'contract':
        goal = 'unitTest' if name in ('mysql-engineering', 'redis-engineering', 'distributed-systems') else 'test'
        tasks = []
        for task in model['tasks']:
            item = dict(task)
            reason = CONTRACT_INTEGRATION_REQUIRED.get(name, {}).get(task['path'])
            if reason:
                item['integration_required'] = reason
            regions = CONTRACT_UNCOVERED_REGIONS.get(name, {}).get(task['path'])
            if regions:
                item['outside_contract_regions'] = regions
            tasks.append(item)
        return goal, tasks, [], []
    require(name in ('mysql-engineering', 'redis-engineering', 'messaging',
                     'distributed-systems', 'java-frameworks', 'backend-capstone'),
            f'{name}: no integration suite is defined; use --suite contract')
    goal = 'test' if name in ('mysql-engineering', 'messaging') else 'integrationTest'
    extra = ['-PwithDocker'] if name == 'messaging' else []
    selected, uncovered = [], []
    for task in model['tasks']:
        root = model['root'] / task['path']
        item = dict(task)
        observation = INTEGRATION_OBSERVATIONS.get(name, {}).get(task['path'])
        if observation:
            item['observation_only'] = observation
        if name in ('mysql-engineering', 'messaging'):
            tag = 'integration' if name == 'mysql-engineering' else 'docker'
            classes = []
            for file in (root / 'test').rglob('*.java'):
                text = file.read_text(encoding='utf-8')
                if re.search(r'@Tag\(\s*"' + tag + r'"\s*\)', text):
                    package = re.search(r'package\s+([\w.]+)\s*;', text)
                    classes.append((package.group(1) + '.' if package else '') + file.stem)
            require(classes, f'{task["path"]}: no explicitly tagged integration test class')
            item['xml_classes'] = classes
            selected.append(item)
        elif name == 'redis-engineering' or list((root / 'integration-test').rglob('*Test.java')):
            selected.append(item)
        else:
            uncovered.append({'path': task['path'], 'status': 'NOT_APPLICABLE',
                              'reason': 'No dedicated integration test source; contract gate still required'})
    require(selected, f'{name}: no integration tasks found')
    if name == 'java-frameworks':
        goal = ':03-transactions:integrationTest'
    return goal, selected, extra, uncovered


def expected_todo_exception(evidence):
    # Audited placeholder messages in these ten courses. A platform/framework
    # UnsupportedOperationException without a course TODO marker is not evidence.
    markers = r'TODO|请按题目实现本步骤|请按本步骤合同完成实现|请实现本阶段学习区|请按题目完成这一阶段'
    return re.search(r'java\.lang\.UnsupportedOperationException[^\n]{0,180}(?:' + markers + r')', evidence) is not None


def inspect_todo_chain(evidence, file, task_path):
    """No cleanup/runtime exception may borrow another branch's valid TODO."""
    if not expected_todo_exception(evidence):
        return
    wrappers = {'java.util.concurrent.ExecutionException', 'java.util.concurrent.CompletionException'}
    # Existing real XML contains these transport/context wrappers. Scope each to
    # its actual course; every terminal/suppressed exception still needs its own TODO.
    if task_path.startswith('framework-course/'):
        wrappers.update({'org.springframework.beans.factory.BeanCreationException',
                         'org.springframework.beans.BeanInstantiationException'})
    if task_path in ('distributed-course/services/03-dubbo', 'distributed-course/services/08-capacity'):
        wrappers.add('org.apache.dubbo.remoting.RemotingException')
    for relation, line in re.findall(r'(Caused by:|Suppressed:)\s+([^\n]+)', evidence):
        kind = line.split(':', 1)[0].split(' ', 1)[0]
        own_todo = kind == 'java.lang.UnsupportedOperationException' and expected_todo_exception(line)
        if relation == 'Suppressed:':
            require(own_todo,
                    f'{file}: suppressed runtime/cleanup exception lacks its own recognized TODO')
        else:
            require(own_todo or kind in wrappers,
                    f'{file}: unexpected nested runtime/cleanup exception alongside TODO: {kind}')


def inspect_junit_failures(root, file, task_path=""):
    """Require actual test failures; dependency/runner/container errors fail closed."""
    attributed = 0
    blocked = ('labs.support.RedisLab$FixtureReadinessException',
               'NoClassDefFoundError', 'ClassNotFoundException', 'UnsupportedClassVersionError',
               'ContainerLaunchException', 'Could not find a valid Docker environment',
               'DockerClientProviderStrategy', 'TestEngine with ID', 'Gradle Test Executor',
               'OutOfMemoryError', 'unable to create native thread', 'java.net.BindException', 'PortInUseException')
    require(not root.findall('.//error') and int(root.get('errors', '0')) == 0,
            f'{file}: JUnit errors are infrastructure/runner failures, not learner rejection')
    failures = root.findall('.//testcase/failure')
    require(len(failures) == int(root.get('failures', '0')), f'{file}: failure count lacks matching testcase evidence')
    for case in root.findall('.//testcase'):
        require(not any(token in case.get('name', '').lower() for token in ('initializationerror', 'initialization error')),
                f'{file}: test initialization failure is not learner rejection')
        for failure in case.findall('failure'):
            evidence = ' '.join([failure.get('type', ''), failure.get('message', ''), failure.text or ''])
            require(not any(token in evidence for token in blocked), f'{file}: infrastructure failure is not learner rejection')
            inspect_todo_chain(evidence, file, task_path)
            kind = failure.get('type', '')
            if kind in ('java.lang.AssertionError', 'org.opentest4j.AssertionFailedError',
                        'org.opentest4j.MultipleFailuresError', 'org.junit.ComparisonFailure'):
                attributed += 1
            elif expected_todo_exception(evidence):
                attributed += 1
            else:
                # Narrow adapters for observed Spring TODO propagation. An
                # unrelated failure never inherits another testcase's rejection.
                output = (root.findtext('system-out') or '') + (root.findtext('system-err') or '')
                require(not any(token in output for token in blocked), f'{file}: infrastructure error in test output')
                server_todo = ('java.lang.UnsupportedOperationException: 请按题目实现本步骤' in output
                               and 'labs.frameworks.Lab' in output)
                http_todo = (task_path == 'framework-course/01-boot/04-test-layers'
                             and file.name == 'TEST-labs.frameworks.HttpIntegrationTest.xml'
                             and case.get('name') == '真实HTTP与应用装配()'
                             and kind == 'org.springframework.web.client.RestClientException'
                             and 'labs.frameworks.Lab$Quotes.total' in output and server_todo)
                repeated_context = (task_path == 'framework-course/01-boot/05-security'
                                    and kind == 'java.lang.IllegalStateException'
                                    and 'ApplicationContext failure threshold' in evidence
                                    and any('java.lang.UnsupportedOperationException: 请按题目实现本步骤' in (f.text or '')
                                            for f in failures) and server_todo)
                require(http_todo or repeated_context, f'{file}: unclassified failure is not learner rejection: {kind}')
                attributed += 1
    return attributed


def collect_results(directory, tasks, goal, expected_pass):
    results = []
    for task in tasks:
        folder = directory / task['path'] / 'build' / 'test-results' / goal.split(':')[-1]
        files = sorted(folder.glob('TEST-*.xml'))
        if task.get('xml_classes'):
            expected_files = {f'TEST-{name}.xml' for name in task['xml_classes']}
            files = [f for f in files if f.name in expected_files]
            require({f.name for f in files} == expected_files, f'{task["path"]}: integration class XML missing')
        require(files, f'{task["path"]}: no fresh JUnit XML; compilation/environment failure is not learner rejection')
        counts = {'tests': 0, 'failures': 0, 'errors': 0, 'skipped': 0}
        attributable = 0
        for file in files:
            root = ET.parse(file).getroot()
            require(root.tag == 'testsuite', f'unexpected JUnit XML root in {file}')
            attributable += inspect_junit_failures(root, file, task['path'])
            for key in counts:
                counts[key] += int(root.get(key, '0'))
        require(all(value >= 0 for value in counts.values()) and counts['failures'] + counts['errors'] + counts['skipped'] <= counts['tests'], f'{task["path"]}: inconsistent JUnit counts')
        require(counts['tests'] - counts['skipped'] > 0, f'{task["path"]}: zero executed tests')
        require(counts['skipped'] == 0, f'{task["path"]}: skipped selected tests are not acceptance evidence')
        failed = counts['failures'] + counts['errors']
        task_pass_expected = expected_pass or bool(task.get('observation_only')) or bool(task.get('integration_required'))
        require((failed == 0) if task_pass_expected else (failed > 0 and attributable > 0), f'{task["path"]}: unexpected test outcome {counts}')
        results.append({'path': task['path'], **counts,
                        'attributable_failures': attributable,
                        **({'outside_contract_regions': task['outside_contract_regions'],
                            'coverage_scope': 'task-start rejection only; real-service regions require the default-test audit'}
                           if task.get('outside_contract_regions') else {}),
                        'rejection_contract': ('INTEGRATION_REQUIRED' if task.get('integration_required') else
                                               'OBSERVATION_ONLY' if task.get('observation_only') else 'REQUIRED'),
                        **({'reason': task.get('integration_required') or task.get('observation_only')}
                           if task.get('integration_required') or task.get('observation_only') else {})})
    return results


def run_gradle(directory, model, args, phase, logs, expected_pass):
    # Prevent stale XML from satisfying assertions even if Gradle fails before clean.
    for path in directory.rglob('test-results'):
        if path.is_dir() and path.parent.name == 'build':
            shutil.rmtree(path)
    goal, selected, suite_args, uncovered = suite_plan(model, args.suite)
    launcher = [str(args.gradle.resolve())] if args.gradle else ['bash', str(directory / 'gradlew')]
    command = launcher + ['--no-daemon', '--console=plain', '--max-workers=1', '--no-build-cache',
                          '--rerun-tasks', '--continue', 'clean', goal] + suite_args + args.gradle_arg
    if args.offline:
        command.append('--offline')
    env = os.environ.copy()
    env['JAVA_HOME'] = str(args.java_home.resolve())
    env['PATH'] = str(args.java_home.resolve() / 'bin') + os.pathsep + env.get('PATH', '')
    if args.gradle_user_home:
        env['GRADLE_USER_HOME'] = str(args.gradle_user_home.resolve())
    log = logs / (phase + '.log')
    start = time.monotonic()
    try:
        code = run_logged(command, cwd=directory, env=env, log=log, timeout=args.timeout)
    except subprocess.TimeoutExpired as error:
        raise GateError(f'{phase}: exceeded {args.timeout}s including group cleanup; see {log}') from error
    require((code == 0) if expected_pass else (code == 1), f'{phase}: unexpected Gradle exit {code}; see {log}')
    results = collect_results(directory, selected, goal, expected_pass)
    return {'phase': phase, 'status': 'PASS', 'goal': goal, 'command': command, 'exit_code': code,
            'seconds': round(time.monotonic() - start, 2), 'log': str(log), 'tasks': results,
            'outside_integration_scope': uncovered}


def legacy_metadata(root, repo):
    """Run the established static validators in a disposable repository-shaped copy.

    Never import arbitrary new courses or run the mixed runtime verification main.
    The explicit allowlist must be reviewed when another course is introduced.
    """
    name = root.relative_to(repo / 'courses').as_posix()
    import_validators = {'java-foundations', 'java-concurrency', 'java-jvm'}
    script_validators = {'java-recovery-collections', 'java-frameworks', 'distributed-systems',
                         'backend-capstone', 'messaging', 'data-storage/mysql-engineering',
                         'data-storage/redis-engineering'}
    require(name in import_validators | script_validators, f'{name}: no reviewed legacy static validator')
    with tempfile.TemporaryDirectory(prefix='academy-static-') as temp:
        clone_repo = Path(temp) / 'repo'
        destination = clone_repo / 'courses' / name
        # Keep relative path contracts used by validators, without build caches,
        # IDE state, or rewriting authoring/metadata-report.json in the checkout.
        shutil.copytree(root, destination, ignore=shutil.ignore_patterns(*IGNORED))
        if (repo / 'infra/versions.env').is_file():
            (clone_repo / 'infra').mkdir(parents=True)
            shutil.copy2(repo / 'infra/versions.env', clone_repo / 'infra/versions.env')
        env = os.environ.copy()
        env.pop('PYTHONOPTIMIZE', None)
        env['PYTHONDONTWRITEBYTECODE'] = '1'
        if name in import_validators:
            code = "import importlib.util; s=importlib.util.spec_from_file_location('legacy_static', 'authoring/verify.py'); m=importlib.util.module_from_spec(s); s.loader.exec_module(m); print(m.validate())"
            command = [sys.executable, '-B', '-c', code]
            validator = 'authoring/verify.py:validate()'
        else:
            command = [sys.executable, '-B', 'authoring/validate_course.py']
            validator = 'authoring/validate_course.py'
        result = subprocess.run(command, cwd=destination, env=env, text=True, capture_output=True, timeout=90)
        output = result.stdout + result.stderr
        require(result.returncode == 0, f'{name}: legacy validator failed: {output}')
        return {'validator': validator, 'status': 'PASS', 'output': output.strip(),
                'execution': 'disposable author tree; no JDK, Gradle, Docker or IDE launched'}


def course_summary(model, repo):
    return {'course': model['root'].relative_to(repo / 'courses').as_posix(), 'status': 'PASS',
            'tasks': len(model['tasks']), 'placeholders': sum(t['placeholders'] for t in model['tasks']),
            'declared_assets': len(model['assets']), 'answer_content': 'PASS', 'utf16_offsets': 'PASS'}


def roundtrip(model, args, summary):
    check_support()
    work = args.work_dir.resolve() / summary['course'].replace('/', '__')
    require(not work.exists(), f'work directory already exists; choose a new --work-dir: {work}')
    work.mkdir(parents=True)
    archive = work / 'source-fixture.zip'
    manifest = pack_fixture(model, archive)
    (work / 'source-manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
    summary.update({'fixture_sha256': digest(archive.read_bytes()), 'fixture': str(archive), 'phases': []})
    first = work / 'first-import'
    unpack_fixture(archive, first, manifest)
    # Re-parse metadata and asset declarations from unpacked bytes, not author tree.
    imported = inspect_course(first)
    learner_hashes = make_learner(imported, first)
    summary['phases'].append(run_gradle(first, model, args, 'learner-rejected', work, False))
    with zipfile.ZipFile(archive) as z:
        for name in imported['placeholders']:
            (first / name).write_bytes(z.read(name))
    require(all(digest((first / name).read_bytes()) == value for name, value in manifest.items()),
            'reference restoration changed or lost packaged assets')
    summary['phases'].append(run_gradle(first, model, args, 'reference-accepted', work, True))
    rebuilt = work / 'second-import'
    unpack_fixture(archive, rebuilt, manifest)
    reimported = inspect_course(rebuilt)
    require(make_learner(reimported, rebuilt) == learner_hashes, 'rebuilt learner differs from first clean start')
    summary['phases'].append(run_gradle(rebuilt, model, args, 'rebuilt-learner-rejected', work, False))
    summary['rebuild'] = 'PASS (fresh directory, not native Reset)'
    current_model = inspect_course(model['root'])
    require(current_model['assets'] == model['assets'] and current_model['tasks'] == model['tasks'],
            'author asset/task set changed during verification; evidence is stale')
    require(all(digest(local_file(model['root'], name).read_bytes()) == value for name, value in manifest.items()),
            'author source changed during verification; evidence is stale')


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode', choices=['metadata', 'legacy-metadata', 'roundtrip'])
    parser.add_argument('--repo', type=Path, default=REPO)
    parser.add_argument('--suite', choices=['contract', 'integration'], default='contract',
                        help='Integration requires real Docker and checks dedicated integration XML only')
    parser.add_argument('--course', action='append', default=[])
    parser.add_argument('--report', type=Path, default=REPO / 'build/quality/academy-report.json')
    parser.add_argument('--work-dir', type=Path, default=REPO / 'build/quality/roundtrip')
    parser.add_argument('--java-home', type=Path, default=Path(os.environ.get('JAVA_HOME', '/usr/lib/jvm/default-java')))
    parser.add_argument('--gradle', type=Path, help='Existing trusted Gradle executable; default uses packaged wrapper')
    parser.add_argument('--gradle-user-home', type=Path)
    parser.add_argument('--gradle-arg', action='append', default=[], help='Extra Gradle argument; use --gradle-arg=--offline syntax')
    parser.add_argument('--offline', action='store_true')
    parser.add_argument('--timeout', type=int, default=900, help='Per-phase Gradle timeout in seconds')
    args = parser.parse_args(argv)
    if args.mode == 'roundtrip':
        try:
            check_support()
        except OSError as error:
            print(f'FAIL: {error}')
            return 1
    report = {'schema_version': SCHEMA, 'mode': args.mode, 'suite': args.suite, 'status': 'PASS', 'native_idea': 'NOT_RUN',
              'native_archive_export_import': 'NOT_RUN', 'native_reset': 'NOT_RUN',
              'docker_integration': 'NOT_RUN', 'fixture_kind': 'repository source fixture, not Academy course archive',
              'courses': []}
    try:
        args.repo = args.repo.resolve()
        roots = discover(args.repo, args.course)
        if args.mode == 'roundtrip':
            java = args.java_home / 'bin/java'
            require(java.is_file() and (args.java_home / 'bin/javac').is_file(), 'full JDK 21 required')
            version = subprocess.run([str(java), '-version'], capture_output=True, text=True, timeout=20)
            require(version.returncode == 0 and re.search(r'version "21(?:\.|\")', version.stdout + version.stderr), 'full JDK 21 required')
            report['jdk'] = (version.stdout + version.stderr).strip()
            if args.suite == 'integration':
                docker = subprocess.run(['docker', 'info', '--format', '{{.ServerVersion}}'], capture_output=True, text=True, timeout=30)
                require(docker.returncode == 0 and docker.stdout.strip(), 'Docker server unavailable: integration is FAIL, never learner rejection')
                report['docker_server'] = docker.stdout.strip()
                report['docker_integration'] = 'RUNNING'

        for root in roots:
            entry = {'course': root.relative_to(args.repo / 'courses').as_posix(), 'status': 'FAIL'}
            report['courses'].append(entry)
            try:
                model = inspect_course(root)
                entry.update(course_summary(model, args.repo))
                if args.mode == 'legacy-metadata':
                    entry['legacy'] = legacy_metadata(root, args.repo)
                if args.mode == 'roundtrip':
                    if args.suite == 'contract' and CONTRACT_UNCOVERED_REGIONS.get(root.name):
                        entry['outside_contract_regions'] = CONTRACT_UNCOVERED_REGIONS[root.name]
                        entry['coverage_scope'] = 'pure task-start contract only; not full default Check or independent-region acceptance'
                    roundtrip(model, args, entry)
                    if args.suite == 'contract' and CONTRACT_INTEGRATION_REQUIRED.get(root.name):
                        entry['status'] = 'INTEGRATION_REQUIRED'
                        entry['required_integration_tasks'] = CONTRACT_INTEGRATION_REQUIRED[root.name]
                        if report['status'] == 'PASS':
                            report['status'] = 'INTEGRATION_REQUIRED'
                print(f'{entry["course"]}: {entry["status"]} ({entry["tasks"]} tasks)', flush=True)
            except Exception as error:
                entry.update(status='FAIL', error=str(error))
                report['status'] = 'FAIL'
                print(f'{entry["course"]}: FAIL: {error}', file=sys.stderr, flush=True)
    except KeyboardInterrupt:
        report.update(status='FAIL', error='Interrupted; no success claim')
    except Exception as error:
        report.update(status='FAIL', error=str(error))
    if args.mode == 'roundtrip' and args.suite == 'integration':
        report['docker_integration'] = report['status']
    report['totals'] = {'courses': len(report['courses']), 'tasks': sum(c.get('tasks', 0) for c in report['courses']),
                        'placeholders': sum(c.get('placeholders', 0) for c in report['courses'])}
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(f'{report["status"]}: {args.report}; native IDEA: NOT_RUN', flush=True)
    return 0 if report['status'] == 'PASS' else 1


if __name__ == '__main__':
    sys.exit(main())
