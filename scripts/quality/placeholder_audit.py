#!/usr/bin/env python3
"""Independently replace EACH editable block in dependency-light courses.

Uses real javac --release 21 and pinned JUnit. This is neither Gradle nor native
Academy verification. Rich dependency courses deliberately fail as unsupported.
"""
import argparse
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time
import xml.etree.ElementTree as ET
import copy

from process_runner import check_support, run_logged

from academy_gate import (REPO, GateError, digest, discover, inspect_course,
                          replace_placeholders, require, inspect_junit_failures, expected_todo_exception)

SUPPORTED = {'java-foundations', 'java-concurrency', 'java-jvm', 'java-recovery-collections'}
JUNIT_SHA = 'b016ef6b1c3454d6d7c2c88ce081dabf289699686af6622d6e4e2e1b54b4a2fc'


def run_case(model, task, java_home, junit, directory, changed=None):
    check_support()
    directory.mkdir(parents=True)
    source_root = directory / 'sources'
    classes = directory / 'classes'
    classes.mkdir()
    paths = [name for name in model['assets'] if name.endswith('.java') and
             (name.startswith(task['path'] + '/src/') or name.startswith(task['path'] + '/test/')
              or name.startswith('common/src/'))]
    require(paths, f'{task["path"]}: no Java sources')
    sources = []
    for name in paths:
        target = source_root / name
        target.parent.mkdir(parents=True, exist_ok=True)
        source = (model['root'] / name).read_text(encoding='utf-8')
        if changed and name == changed['file']:
            source, _ = replace_placeholders(source, [model['placeholders'][name][changed['index']]])
        target.write_text(source, encoding='utf-8')
        sources.append(str(target))
    command = [str(java_home / 'bin/javac'), '--release', '21', '-encoding', 'UTF-8',
               '-parameters', '-cp', str(junit), '-d', str(classes)] + sources
    compile_code = run_logged(command, log=directory / 'compile.log', timeout=60)
    require(compile_code == 0, f'{directory}: compilation error is not mutation rejection')
    command = [str(java_home / 'bin/java'), '-Xmx192m', '-XX:ActiveProcessorCount=2',
               '-jar', str(junit), 'execute', '--class-path', str(classes), '--scan-class-path',
               '--disable-banner', '--disable-ansi-colors', '--details=summary', '--fail-if-no-tests',
               '--reports-dir', str(directory / 'xml')]
    exit_code = run_logged(command, log=directory / 'junit.log', timeout=90)
    output = (directory / 'junit.log').read_text(encoding='utf-8')
    counts = {}
    for key in ('found', 'started', 'successful', 'failed', 'skipped', 'aborted'):
        match = re.search(r'\[\s*(\d+) tests ' + key + r'\s*\]', output)
        require(match is not None, f'{directory}: JUnit summary missing {key}')
        counts[key] = int(match.group(1))
    require(counts['started'] > 0 and counts['skipped'] == 0 and counts['aborted'] == 0,
            f'{directory}: no/aborted/skipped tests cannot prove coverage')
    xml_files = sorted((directory / 'xml').glob('TEST-*.xml'))
    require(xml_files, f'{directory}: no fresh JUnit XML')
    xml_tests, xml_failures, attributed = 0, 0, 0
    for file in xml_files:
        root = ET.parse(file).getroot()
        require(root.tag == 'testsuite', f'{file}: unsupported JUnit XML shape')
        xml_tests += int(root.get('tests', '0'))
        xml_failures += int(root.get('failures', '0')) + int(root.get('errors', '0'))
        normalized = copy.deepcopy(root)
        # Console Launcher reports thrown TODO exceptions as <error>, whereas
        # Gradle reports them as <failure>. Normalize ONLY recognized TODO chains.
        errors = normalized.findall('.//testcase/error')
        require(len(errors) == int(normalized.get('errors', '0')), f'{file}: inconsistent JUnit errors')
        for error in errors:
            evidence = ' '.join([error.get('type', ''), error.get('message', ''), error.text or ''])
            require(expected_todo_exception(evidence),
                    f'{file}: runtime/infrastructure error is not placeholder rejection')
            error.tag = 'failure'
        normalized.set('failures', str(int(normalized.get('failures', '0')) + len(errors)))
        normalized.set('errors', '0')
        attributed += inspect_junit_failures(normalized, file, task['path'])
    require(xml_tests == counts['found'] and xml_failures == counts['failed'],
            f'{directory}: XML/console summary mismatch')
    expected = (exit_code == 1 and counts['failed'] > 0 and attributed == counts['failed']) if changed else exit_code == 0 and counts['failed'] == 0
    return {'status': 'PASS' if expected else 'FAIL', 'tests': counts, 'exit_code': exit_code,
            'log': str(directory / 'junit.log'), 'changed': changed}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--course', action='append', required=True)
    parser.add_argument('--java-home', type=Path, default=Path(os.environ.get('JAVA_HOME', '')))
    parser.add_argument('--junit-console', type=Path, required=True)
    parser.add_argument('--report', type=Path, default=REPO / 'build/quality/placeholder-audit.json')
    parser.add_argument('--work-dir', type=Path, default=REPO / 'build/quality/placeholder-audit')
    args = parser.parse_args(argv)
    if True:
        try:
            check_support()
        except OSError as error:
            print(f'FAIL: {error}')
            return 1
    report = {'schema_version': 1, 'status': 'PASS', 'native_idea': 'NOT_RUN', 'gradle': 'NOT_RUN',
              'docker_integration': 'NOT_RUN', 'kind': 'independent placeholder rejection via javac/JUnit', 'courses': []}
    start = time.monotonic()
    try:
        junit = args.junit_console.resolve()
        home = args.java_home.resolve()
        require(digest(junit.read_bytes()) == JUNIT_SHA, 'expected official JUnit Platform standalone 1.11.4 digest')
        version = subprocess.run([str(home / 'bin/java'), '-version'], text=True, capture_output=True, timeout=20)
        require(re.search(r'version "21(?:\.|\")', version.stdout + version.stderr), 'full JDK 21 required')
        report['jdk'] = (version.stdout + version.stderr).strip()
        report['junit_sha256'] = JUNIT_SHA
        work = args.work_dir.resolve()
        require(not work.exists(), f'refusing existing work directory: {work}')
        for root in discover(REPO, args.course):
            require(root.name in SUPPORTED, f'{root.name}: unsupported dependency graph; use Gradle roundtrip plus course-specific mutation validator')
            model = inspect_course(root)
            snapshot = {name: digest((root / name).read_bytes()) for name in model['assets']}
            entry = {'course': root.name, 'status': 'PASS', 'tasks': [], 'inputs_sha256': snapshot}
            report['courses'].append(entry)
            for task in model['tasks']:
                task_result = {'path': task['path'], 'status': 'PASS', 'mutations': []}
                entry['tasks'].append(task_result)
                directory = work / root.name / task['path']
                task_result['reference'] = run_case(model, task, home, junit, directory / 'reference')
                require(task_result['reference']['status'] == 'PASS', f'{task["path"]}: reference does not pass')
                for file, ph in model['placeholders'].items():
                    if not file.startswith(task['path'] + '/'):
                        continue
                    for index in range(len(ph)):
                        changed = {'file': file, 'index': index, 'offset_utf16': ph[index]['offset']}
                        result = run_case(model, task, home, junit, directory / f'mutation-{len(task_result["mutations"]):03}', changed)
                        task_result['mutations'].append(result)
                        if result['status'] != 'PASS':
                            task_result['status'] = entry['status'] = report['status'] = 'FAIL'
                print(f'{root.name}/{task["path"]}: {task_result["status"]} ({len(task_result["mutations"])} independent blocks)', flush=True)
            current = inspect_course(root)
            require(current['assets'] == model['assets'] and all(digest((root / name).read_bytes()) == sha for name, sha in snapshot.items()),
                    f'{root.name}: author inputs changed during placeholder audit')
    except Exception as error:
        report.update(status='FAIL', error=str(error))
    report['seconds'] = round(time.monotonic() - start, 2)
    report['totals'] = {'courses': len(report['courses']), 'tasks': sum(len(c['tasks']) for c in report['courses']),
                        'mutations': sum(len(t['mutations']) for c in report['courses'] for t in c['tasks']),
                        'survivors': sum(m['status'] != 'PASS' for c in report['courses'] for t in c['tasks'] for m in t['mutations'])}
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(f'{report["status"]}: {args.report}; native IDEA: NOT_RUN', flush=True)
    return 0 if report['status'] == 'PASS' else 1


if __name__ == '__main__':
    sys.exit(main())
