#!/usr/bin/env python3
"""Four exact, independent distributed TODO regions against real-service JUnit.

Preparation is the default and never starts Java, Gradle, or Docker. --execute
requires a real Docker server; every reference/candidate has a new source tree,
fresh compilation and fresh XML. It does not modify the author course.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import time
import xml.etree.ElementTree as ET

from academy_gate import (REPO, GateError, collect_results, digest, inspect_course,
                          local_file, pack_fixture, replace_placeholders, require,
                          unpack_fixture)
from process_runner import TERMINATION_GRACE, check_support, run_logged

COURSE = 'courses/distributed-systems'
BASE = 'distributed-course/services/'
XA_TEST = '两个MySQL资源准备后无决策回滚有决策提交()'
SAGA_TEST = 'TCC与Saga参与者跨数据库持久化恢复()'
OUTBOX_TEST = '发布后标记前崩溃产生重复但读模型收敛并拒绝旧缓存回填()'
TODO = '请按本步骤合同完成实现'
CASES = (
    ('DS-17', '06-transactions', 'transactions/XaTransfer.java', 0, 'transfer',
     ('ra.prepare(xa)', 'decision(id)', 'ra.commit(xa, false)', 'rb.commit(xb, false)')),
    ('DS-19', '07-outbox-cache', 'outbox/OutboxStore.java', 1, 'publishOne',
     ('sender.send(event)', 'failurePoint.afterSend()', 'published=1')),
    ('DS-21', '07-outbox-cache', 'outbox/VersionedCache.java', 0, 'fill',
     ("redis.call('HSET'", "redis.call('PEXPIRE'")),
    ('DS-22', '07-outbox-cache', 'outbox/VersionedCache.java', 1, 'invalidate',
     ("if v>f then", "if c<v then redis.call('DEL'")),
)


def plan(model):
    result = []
    for region, module, java, index, method, anchors in CASES:
        task = BASE + module
        file = task + '/src/labs/distributed/' + java
        placeholders = model['placeholders'].get(file, [])
        require(index < len(placeholders), f'{region}: missing declared file-local region {index}')
        ph = placeholders[index]
        source = local_file(model['root'], file).read_text(encoding='utf-8')
        learner, answers = replace_placeholders(source, [ph])
        require(all(token in answers[0] for token in anchors), f'{region}: YAML region no longer matches intended behavior')
        require(ph['placeholder_text'].count('throw new UnsupportedOperationException("' + TODO + '")') == 1,
                f'{region}: unexpected learner TODO; review attribution before extending')
        prefix = source.encode('utf-16-le')[:ph['offset'] * 2].decode('utf-16-le')
        throw_offset = ph['placeholder_text'].index('throw new UnsupportedOperationException')
        todo_line = (prefix + ph['placeholder_text'][:throw_offset]).count('\n') + 1
        test_class = 'labs.distributed.' + ('MySqlTransactionTest' if module == '06-transactions' else 'OutboxIntegrationTest')
        test_cases = [XA_TEST, SAGA_TEST] if module == '06-transactions' else [OUTBOX_TEST]
        result.append({'region': region, 'mutation_kind': 'TODO', 'task': task, 'module': module, 'file': file,
                       'index_zero_based': index, 'offset_utf16': ph['offset'], 'length_utf16': ph['length'],
                       'source_sha256': digest(source.encode()), 'learner_sha256': digest(learner.encode()),
                       'region_sha256': digest(answers[0].encode()), 'todo_line': todo_line,
                       'owner': 'labs.distributed.' + java[:-5].replace('/', '.'), 'method': method,
                       'test_class': test_class, 'test_cases': test_cases,
                       'rejecting_test': XA_TEST if module == '06-transactions' else OUTBOX_TEST})
    return result


def learner_source(model, case):
    source = local_file(model['root'], case['file']).read_text(encoding='utf-8')
    ph = model['placeholders'][case['file']][case['index_zero_based']]
    if case['mutation_kind'] == 'TODO':
        return replace_placeholders(source, [ph])[0]
    require(case['mutation_kind'] == 'OMIT_COMMIT', 'unknown mutation kind')
    raw = source.encode('utf-16-le')
    start, end = ph['offset'] * 2, (ph['offset'] + ph['length']) * 2
    answer = raw[start:end].decode('utf-16-le')
    statement = case['omitted_statement']
    require(answer.count(statement) == 1, 'commit control must remove exactly one declared-region statement')
    return (raw[:start] + answer.replace(statement, '', 1).encode('utf-16-le') + raw[end:]).decode('utf-16-le')


def commit_controls(model, cases):
    controls = []
    test = model['root'] / cases[0]['task'] / 'integration-test/labs/distributed/MySqlTransactionTest.java'
    source = test.read_text(encoding='utf-8')
    for resource, branch, database, message in [('ra', 'xa', 'first', '转出分支未完成'),
                                                 ('rb', 'xb', 'second', '转入分支未完成')]:
        marker = 'assertEquals(0, preparedBranches(Images.database(' + database + ')'
        require(source.count(marker) == 1, 'missing unique normal-XA branch completion assertion')
        case = dict(cases[0], region='DS-17-omit-' + resource + '-commit', mutation_kind='OMIT_COMMIT',
                    omitted_statement=resource + '.commit(' + branch + ', false);',
                    assertion_message=message, assertion_line=source[:source.index(marker)].count('\n') + 1)
        case.pop('todo_line')
        case['learner_sha256'] = digest(learner_source(model, case).encode())
        controls.append(case)
    return controls


class ExecutionBudget:
    def __init__(self, seconds):
        self.deadline = time.monotonic() + seconds

    def allowance(self, cap, phase, reserve=0):
        remaining = self.deadline - time.monotonic()
        require(remaining > reserve, f'total execution budget exhausted before {phase}; no further process started')
        return min(cap, remaining)


def report_destination(path, author_course):
    target = path.resolve()
    require(not target.is_relative_to(author_course.resolve()), 'report must be outside author course')
    require(not target.exists(), f'refusing existing report destination: {target}')
    return target


def validate_xml(directory, case, changed, exit_code):
    expected_code = 1 if changed else 0
    require(exit_code == expected_code, f'unexpected Gradle exit {exit_code}; expected {expected_code}')
    folder = directory / case['task'] / 'build/test-results/test'
    files = sorted(folder.glob('TEST-*.xml'))
    expected = folder / ('TEST-' + case['test_class'] + '.xml')
    require(files == [expected], 'missing or unexpected integration class XML')
    root = ET.parse(expected).getroot()
    require(root.tag == 'testsuite' and root.get('name') == case['test_class'], 'unexpected JUnit suite')
    cases = root.findall('testcase')
    require(len(cases) == len(case['test_cases']) == int(root.get('tests', '0')),
            'missing/zero/duplicate testcase evidence')
    require({c.get('name') for c in cases} == set(case['test_cases']), 'unexpected or missing selected test')
    require(all(c.get('classname') == case['test_class'] for c in cases), 'unexpected testcase class')
    require(not root.findall('.//skipped'), 'skipped tests are not acceptance evidence')
    results = collect_results(directory, [{'path': case['task'], 'xml_classes': [case['test_class']]}],
                              'test', not changed)
    attributed = []
    if changed:
        for c in cases:
            for failure in c.findall('failure'):
                evidence = ' '.join([failure.get('type', ''), failure.get('message', ''), failure.text or ''])
                require(c.get('name') == case['rejecting_test'], 'failure in unrelated test is not region rejection')
                kind = failure.get('type', '')
                if case['mutation_kind'] == 'OMIT_COMMIT':
                    frame = (r'at (?:app//)?labs\.distributed\.MySqlTransactionTest\.lambda\$'
                             + re.escape(case['rejecting_test'].removesuffix('()')) + r'\$\d+'
                             + r'\(MySqlTransactionTest\.java:' + str(case['assertion_line']) + r'\)')
                    trace = failure.text or ''
                    assertion = ('org.opentest4j.AssertionFailedError: ' + case['assertion_message']
                                 + ' ==> expected: <0> but was: <1>')
                    require(kind == 'org.opentest4j.MultipleFailuresError'
                            and results[0]['failures'] == 1
                            and trace.splitlines()[:1] == ['org.opentest4j.MultipleFailuresError: Multiple Failures (1 failure)']
                            and assertion in trace and re.search(frame, trace)
                            and 'UnsupportedOperationException' not in evidence,
                            'commit control must fail its exact no-prepared-branch assertion, not setup or recovery')
                    chains = list(re.finditer(r'(?m)^[ \t]*(Suppressed|Caused by):[ \t]*([^\n]+)', trace))
                    # Gradle may repeat the ONE assertAll failure as its cause.
                    # Each representation needs its own exact branch and frame;
                    # an unrelated assertion or cleanup exception cannot borrow it.
                    require([node[1] for node in chains] in (['Suppressed'], ['Suppressed', 'Caused by']),
                            'commit control includes unexpected nested or cleanup exception')
                    for index, node in enumerate(chains):
                        end = chains[index + 1].start() if index + 1 < len(chains) else len(trace)
                        require(node[2].strip() == assertion and re.search(frame, trace[node.end():end]),
                                'commit control nested assertion has the wrong branch or source frame')
                    attributed.append({'test': c.get('name'), 'type': kind,
                                       'assertion_line': case['assertion_line']})
                    continue
                frame = (r'at ' + re.escape(case['owner']) + r'\.(?:' + re.escape(case['method']) +
                         r'|lambda\$' + re.escape(case['method']) + r'\$\d+)\(' +
                         re.escape(Path(case['file']).name) + ':' + str(case['todo_line']) + r'\)')
                direct = kind == 'java.lang.UnsupportedOperationException'
                wrapped = (case['region'] == 'DS-19' and kind == 'org.opentest4j.AssertionFailedError'
                           and 'Unexpected exception type thrown' in evidence
                           and 'java.lang.IllegalStateException' in evidence)
                require(direct or wrapped, 'not the expected direct TODO or narrow assertThrows wrapper')
                require('Suppressed:' not in evidence, 'suppressed cleanup failure is not TODO rejection')
                nested = re.findall(r'Caused by: ([\w.$]+)', evidence)
                require(all(kind == 'java.lang.UnsupportedOperationException' for kind in nested),
                        'unexpected nested runtime or cleanup failure is not TODO rejection')
                require('java.lang.UnsupportedOperationException: ' + TODO in evidence and re.search(frame, evidence),
                        'failure is not attributable to this exact learner TODO source line')
                attributed.append({'test': c.get('name'), 'type': kind, 'todo_line': case['todo_line']})
        require(len(attributed) == results[0]['failures'] > 0, 'not every failure is region-attributed')
    return {'counts': results[0], 'attributed': attributed, 'xml': str(expected),
            'xml_sha256': digest(expected.read_bytes())}


def run_process(command, cwd, env, log, timeout):
    try:
        return run_logged(command, cwd=cwd, env=env, log=log, timeout=timeout)
    except subprocess.TimeoutExpired as error:
        raise GateError(f'timeout ({timeout:.2f}s including cleanup), never accepted as rejection; see {log}') from error


def verify_inputs(root, manifest, changed=None):
    for file, sha in manifest.items():
        expected = changed['learner_sha256'] if changed and file == changed['file'] else sha
        require(digest(local_file(root, file).read_bytes()) == expected, f'fixture source drift: {file}')


def run_case(model, archive, manifest, versions, args, case, changed, location):
    check_support()
    directory = location / COURSE
    unpack_fixture(archive, directory, manifest)
    image_file = location / 'infra/versions.env'
    image_file.parent.mkdir(parents=True)
    shutil.copyfile(versions, image_file)
    if changed:
        file = directory / case['file']
        file.write_text(learner_source(model, case), encoding='utf-8')
    verify_inputs(directory, manifest, case if changed else None)
    require(not any(directory.rglob('test-results')) and not any(directory.rglob('*.class')),
            'fresh fixture must not contain XML or compiled classes')
    launcher = [str(args.gradle.resolve())] if args.gradle else ['bash', str(directory / 'gradlew')]
    command = launcher + ['--no-daemon', '--console=plain', '--max-workers=1', '--no-build-cache',
                          '--rerun-tasks', 'clean', ':' + case['module'] + ':test',
                          '--tests', case['test_class']]
    if args.offline:
        command.append('--offline')
    env = os.environ.copy()
    require(env.get('TESTCONTAINERS_RYUK_DISABLED', '').lower() != 'true',
            'disabled Ryuk is unsupported: interrupted integration needs session-scoped cleanup')
    env['TESTCONTAINERS_RYUK_DISABLED'] = 'false'
    env['JAVA_HOME'] = str(args.java_home.resolve())
    env['PATH'] = env['JAVA_HOME'] + '/bin' + os.pathsep + env.get('PATH', '')
    if args.gradle_user_home:
        env['GRADLE_USER_HOME'] = str(args.gradle_user_home.resolve())
    log = location / 'gradle.log'
    started = time.monotonic()
    allowance = args.budget.allowance(args.timeout, location.name, reserve=TERMINATION_GRACE)
    code = run_process(command, directory, env, log, allowance)
    args.budget.allowance(args.total_timeout, location.name + ' result verification')
    verify_inputs(directory, manifest, case if changed else None)
    require(digest(image_file.read_bytes()) == digest(versions.read_bytes()), 'image ledger drift')
    try:
        evidence = validate_xml(directory, case, changed, code)
    except GateError as error:
        raise GateError(f'{location.name}: {error}; see {log}') from error
    class_roots = [directory / 'support/build/classes/java/main',
                   directory / case['task'] / 'build/classes/java/main',
                   directory / case['task'] / 'build/classes/java/integrationTest']
    compiled = {p.relative_to(directory).as_posix(): digest(p.read_bytes())
                for root in class_roots for p in sorted(root.rglob('*.class'))}
    target = case['task'] + '/build/classes/java/main/' + case['owner'].replace('.', '/') + '.class'
    integration = case['task'] + '/build/classes/java/integrationTest/' + case['test_class'].replace('.', '/') + '.class'
    require(target in compiled and integration in compiled, 'missing fresh target/integration bytecode')
    return {'status': 'PASS', 'changed': changed, 'command': command, 'exit_code': code,
            'process_budget_seconds': round(allowance, 3),
            'seconds': round(time.monotonic() - started, 2), 'log': str(log),
            'compiled_class_sha256': compiled, **evidence}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo', type=Path, default=REPO)
    parser.add_argument('--execute', action='store_true', help='explicitly run sequential real-Docker integration checks')
    parser.add_argument('--xa-commit-controls', action='store_true', help='also independently omit each normal XA commit (2 extra runs, same total budget)')
    parser.add_argument('--java-home', type=Path, default=Path(os.environ.get('JAVA_HOME', '')))
    parser.add_argument('--gradle', type=Path)
    parser.add_argument('--gradle-user-home', type=Path)
    parser.add_argument('--offline', action='store_true')
    parser.add_argument('--timeout', type=int, default=300, help='per Gradle process budget including cleanup, seconds')
    parser.add_argument('--total-timeout', type=int, default=900, help='whole execution sequence budget, seconds')
    parser.add_argument('--work-dir', type=Path, required=True, help='must not exist')
    parser.add_argument('--report', type=Path, required=True, help='new file outside author course; never overwritten')
    args = parser.parse_args(argv)
    if args.execute:
        try:
            check_support()
        except OSError as error:
            print(f'FAIL: {error}')
            return 1
    repo = args.repo.resolve()
    # A rejected destination must never become the error-report output either.
    try:
        output = report_destination(args.report, repo / COURSE)
    except (GateError, OSError) as error:
        print(f'FAIL: unsafe report destination; no file written: {error}')
        return 1
    report = {'schema_version': 1, 'status': 'NOT_RUN', 'native_idea': 'NOT_RUN',
              'docker_integration': 'NOT_RUN', 'scope': 'four independent declared TODO regions through the default test task',
              'grading_task': 'test', 'class_filter': 'existing real-service JUnit class',
              'regions': [], 'semantic_controls': [], 'reference_runs': [], 'mutation_runs': [],
              'semantic_control_runs': [],
              'runtime': {'execution_requested': args.execute, 'status': 'NOT_RUN', 'completed_runs': 0}}
    started = time.monotonic()
    execution_started = None
    try:
        require(args.timeout > TERMINATION_GRACE and args.total_timeout > TERMINATION_GRACE,
                'process and total budgets must exceed the 15-second cleanup reserve')
        model = inspect_course(repo / COURSE)
        cases = plan(model)
        controls = commit_controls(model, cases) if args.xa_commit_controls else []
        work = args.work_dir.resolve()
        require(not work.exists(), f'refusing existing work directory: {work}')
        require(not work.is_relative_to(model['root']), 'work directory must be outside author course')
        require(work != output and not work.is_relative_to(output), 'report cannot be the work directory or its parent')
        work.mkdir(parents=True)
        archive = work / 'reference-source.zip'
        manifest = pack_fixture(model, archive)
        versions = local_file(repo, 'infra/versions.env')
        report.update(regions=cases, semantic_controls=controls, inputs_sha256=manifest,
                      versions_sha256=digest(versions.read_bytes()),
                      fixture_sha256=digest(archive.read_bytes()), fixture=str(archive),
                      limits={'gradle_process_seconds': args.timeout, 'total_execution_seconds': args.total_timeout,
                              'termination_grace_seconds': TERMINATION_GRACE, 'grace_reserved_within_budget': True,
                              'gradle_workers': 1, 'test_forks': 1, 'gradle_runs': 6 + len(controls),
                              'test_task_seconds': 600, 'docker_preflight_seconds': 30},
                      container_cleanup='Testcontainers 1.20.6 Ryuk explicitly enabled; isolated test fixtures use close(); no global prune')
        report['runtime']['planned_runs'] = 6 + len(controls)
        if args.execute:
            require(os.environ.get('TESTCONTAINERS_RYUK_DISABLED', '').lower() != 'true',
                    'disabled Ryuk is unsupported: interrupted integration needs session-scoped cleanup')
            execution_started = time.monotonic()
            args.budget = ExecutionBudget(args.total_timeout)
            report['runtime']['status'] = 'RUNNING'
            java = subprocess.run([str(args.java_home.resolve() / 'bin/java'), '-version'],
                                  capture_output=True, text=True,
                                  timeout=args.budget.allowance(20, 'JDK preflight'))
            require(java.returncode == 0 and re.search(r'version "21(?:\.|\")', java.stdout + java.stderr), 'full JDK 21 required')
            report['jdk'] = (java.stdout + java.stderr).strip()
            docker = subprocess.run(['docker', 'info', '--format', '{{.ServerVersion}}'],
                                    capture_output=True, text=True,
                                    timeout=args.budget.allowance(30, 'Docker preflight'))
            require(docker.returncode == 0 and docker.stdout.strip(), 'Docker server unavailable; no rejection evidence')
            report.update(status='RUNNING', docker_integration='RUNNING', docker_server=docker.stdout.strip())

            def execute(case, changed, section, name):
                args.budget.allowance(args.timeout, name + ' fixture staging', reserve=TERMINATION_GRACE)
                entry = {'region': case['region'], 'module': case['module'], 'status': 'RUNNING',
                         'log': str(work / name / 'gradle.log')}
                report[section].append(entry)
                try:
                    entry.update(run_case(model, archive, manifest, versions, args, case, changed, work / name))
                except (GateError, OSError, ValueError, ET.ParseError, subprocess.SubprocessError, KeyboardInterrupt) as error:
                    entry.update(status='FAIL', error=str(error) or 'interrupted')
                    raise
                report['runtime']['completed_runs'] += 1

            references = set()
            for case in cases:
                if case['module'] not in references:
                    execute(case, False, 'reference_runs', 'reference-' + case['module'])
                    references.add(case['module'])
            # Establish both accepted references before any negative run.
            for case in cases:
                execute(case, True, 'mutation_runs', case['region'])
            for case in controls:
                execute(case, True, 'semantic_control_runs', case['region'])
            verify_inputs(model['root'], manifest)
            require(digest(versions.read_bytes()) == report['versions_sha256'], 'author image ledger changed')
            args.budget.allowance(args.total_timeout, 'final acceptance')
            require(report['runtime']['completed_runs'] == report['runtime']['planned_runs'], 'incomplete execution sequence')
            report.update(status='PASS', docker_integration='PASS')
            report['runtime']['status'] = 'PASS'
        else:
            verify_inputs(model['root'], manifest)
            report['preparation'] = 'PASS (YAML selectors, exact source hashes and clean fixture only); exit 2, not a runtime pass'
    except (GateError, OSError, ValueError, ET.ParseError, subprocess.SubprocessError, KeyboardInterrupt) as error:
        report.update(status='FAIL', error=str(error) or 'interrupted')
        if args.execute:
            report['runtime']['status'] = 'FAIL'
        if report['docker_integration'] == 'RUNNING':
            report['docker_integration'] = 'FAIL'
    report['seconds'] = round(time.monotonic() - started, 2)
    report['runtime']['seconds'] = round(time.monotonic() - execution_started, 2) if execution_started is not None else 0
    try:
        output.parent.mkdir(parents=True, exist_ok=True)
        with output.open('x', encoding='utf-8') as stream:
            stream.write(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
    except OSError as error:
        print(f'FAIL: report not written (existing files are preserved): {error}')
        return 1
    print(f'{report["status"]}: {output}; real-service integration: {report["docker_integration"]}')
    return 0 if report['status'] == 'PASS' else (2 if report['status'] == 'NOT_RUN' else 1)


if __name__ == '__main__':
    raise SystemExit(main())
