#!/usr/bin/env python3
"""C11-01 visible structural contract. Never builds or runs Docker or Java.

This deliberately supports the two teaching forms (direct Java exec, or the
shared exec script), not the complete Dockerfile language. A pass is evidence
about source structure only: actual layers, PID 1, signals, HTTP, Redis, image
availability, and Academy execution still require their separate checks.
"""
import argparse
import json
import pathlib
import re
import shlex
import sys

PASS_MARKER = 'C11_DOCKERFILE_CONTRACT_PASS'
SCOPE = 'STRUCTURAL_ONLY'
EXPECTED_CASES = (
    'explicit_version_arguments', 'separate_build_runtime',
    'bounded_build_instructions', 'minimal_runtime_copies',
    'non_root_runtime', 'declared_port_and_signal', 'exec_entrypoint',
    'build_context_allowlist',
)
MAX_SOURCE_BYTES = 128 * 1024


class InvalidEnvironment(Exception):
    """A missing or unusable grading input must never become a passing check."""


class ContractViolation(Exception):
    def __init__(self, case_id, detail):
        super().__init__(case_id + ': ' + detail)
        self.case_id = case_id


def require(condition, case_id, detail):
    if not condition:
        raise ContractViolation(case_id, detail)


def read_input(path):
    try:
        if not path.is_file() or path.stat().st_size > MAX_SOURCE_BYTES:
            raise InvalidEnvironment('Missing or oversized input: ' + str(path))
        return path.read_text(encoding='utf-8')
    except (OSError, UnicodeError) as error:
        raise InvalidEnvironment('Unreadable UTF-8 input: ' + str(path)) from error


def instructions(source):
    """Small, conservative parser for this lab's supported instruction subset."""
    result = []
    pending = ''
    for raw in source.splitlines():
        line = raw.strip()
        if not line or line.startswith('#'):
            continue
        pending += line[:-1] + ' ' if line.endswith('\\') else line
        if line.endswith('\\'):
            continue
        match = re.fullmatch(r'([A-Za-z]+)\s+(.+)', pending)
        require(match is not None, 'dockerfile_syntax', 'Unrecognized instruction: ' + pending)
        result.append((match.group(1).upper(), match.group(2).strip()))
        pending = ''
    require(not pending, 'dockerfile_syntax', 'Unterminated continuation')
    require(bool(result), 'dockerfile_syntax', 'Empty Dockerfile')
    return result


def words(value, case_id):
    try:
        return shlex.split(value, comments=False, posix=True)
    except ValueError as error:
        raise ContractViolation(case_id, 'Malformed quoted instruction') from error


def copies(value):
    tokens = words(value, 'minimal_runtime_copies')
    flags = {}
    while tokens and tokens[0].startswith('--'):
        key, sep, val = tokens.pop(0)[2:].partition('=')
        require(sep and key in {'from', 'chown', 'chmod'} and key not in flags,
                'minimal_runtime_copies', 'Unknown or duplicate COPY flag')
        flags[key] = val
    require(len(tokens) == 2 and not any(token.startswith('[') for token in tokens),
            'minimal_runtime_copies', 'Use the two-path COPY teaching form')
    return flags, tokens[0].rstrip('/'), tokens[1].rstrip('/')


def validate(dockerfile, dockerignore, entrypoint):
    """Return nonempty named evidence; no assertions that python -O can erase."""
    parsed = instructions(dockerfile)
    from_positions = [i for i, (key, _) in enumerate(parsed) if key == 'FROM']
    require(len(from_positions) == 2, 'separate_build_runtime', 'Exactly two teaching stages are required')
    first, second = from_positions
    global_args = parsed[:first]
    require(sorted(global_args) == sorted([('ARG', 'JAVA_BUILD_IMAGE'), ('ARG', 'JAVA_RUNTIME_IMAGE')]),
            'explicit_version_arguments', 'Declare both image ARGs globally without default values')
    build_from = words(parsed[first][1], 'separate_build_runtime')
    run_from = words(parsed[second][1], 'separate_build_runtime')
    require(len(build_from) == 3 and build_from[0] == '${JAVA_BUILD_IMAGE}'
            and build_from[1].upper() == 'AS' and re.fullmatch(r'[A-Za-z][A-Za-z0-9_-]*', build_from[2]),
            'separate_build_runtime', 'Name the build stage and use ${JAVA_BUILD_IMAGE}')
    require(run_from == ['${JAVA_RUNTIME_IMAGE}'] or
            (len(run_from) == 3 and run_from[0] == '${JAVA_RUNTIME_IMAGE}'
             and run_from[1].upper() == 'AS' and re.fullmatch(r'[A-Za-z][A-Za-z0-9_-]*', run_from[2])
             and run_from[2].lower() != build_from[2].lower()),
            'separate_build_runtime', 'The final stage must use ${JAVA_RUNTIME_IMAGE}')
    build = parsed[first + 1:second]
    require(len(build) == 3 and build[0] == ('WORKDIR', '/build')
            and build[1][0] == 'COPY' and words(build[1][1], 'bounded_build_instructions') == ['src/', 'src/']
            and build[2][0] == 'RUN' and words(build[2][1], 'bounded_build_instructions') == [
                'mkdir', '-p', 'classes', '&&', 'javac', '--release', '21', '-encoding', 'UTF-8',
                '-d', 'classes', 'src/labs/*.java'],
            'bounded_build_instructions', 'Use the visible /build, src-only, javac --release 21 build recipe')
    runtime = parsed[second + 1:]
    allowed = {'WORKDIR', 'COPY', 'USER', 'EXPOSE', 'STOPSIGNAL', 'ENTRYPOINT'}
    require(all(key in allowed for key, _ in runtime), 'minimal_runtime_copies',
            'The runtime stage may not install tools, ADD content, or change launch behavior')
    require([value for key, value in runtime if key == 'WORKDIR'] == ['/opt/app']
            and runtime and runtime[0] == ('WORKDIR', '/opt/app'),
            'minimal_runtime_copies', 'Runtime WORKDIR must be /opt/app before relative copies')
    copied = [copies(value) for key, value in runtime if key == 'COPY']
    classes = ({'from': build_from[2], 'chown': '10001:10001'}, '/build/classes', './classes')
    web = ({'chown': '10001:10001'}, 'web', './web')
    script = ({'chown': '10001:10001', 'chmod': '0555'}, 'container/entrypoint.sh', '/opt/app/entrypoint.sh')
    normalized = [(flags, src, {'/opt/app/classes': './classes', '/opt/app/web': './web'}.get(dst, dst))
                  for flags, src, dst in copied]
    require(normalized == [classes, web] or normalized == [classes, web, script],
            'minimal_runtime_copies', 'Copy only owned classes, web, and optionally the shared executable entrypoint')
    require([value for key, value in runtime if key == 'USER'] == ['10001:10001'],
            'non_root_runtime', 'Set numeric non-root USER 10001:10001 exactly once')
    require([value for key, value in runtime if key == 'EXPOSE'] in (['8080'], ['8080/tcp'])
            and [value for key, value in runtime if key == 'STOPSIGNAL'] in (['SIGTERM'], ['15']),
            'declared_port_and_signal', 'Declare port 8080 and TERM')
    entries = [value for key, value in runtime if key == 'ENTRYPOINT']
    require(len(entries) == 1, 'exec_entrypoint', 'Provide exactly one JSON ENTRYPOINT')
    try:
        command = json.loads(entries[0])
    except (ValueError, TypeError) as error:
        raise ContractViolation('exec_entrypoint', 'ENTRYPOINT must be a JSON array, not shell form') from error
    direct = command in (["java", "-cp", "/opt/app/classes", "labs.CloudNativeApp"],
                         ["java", "-XX:MaxRAMPercentage=65.0", "-cp", "/opt/app/classes", "labs.CloudNativeApp"])
    via_script = command == ['/opt/app/entrypoint.sh'] and normalized == [classes, web, script]
    require(direct or via_script, 'exec_entrypoint', 'Launch Java directly or use the shared exec script')
    if via_script:
        script_lines = [line.strip() for line in entrypoint.splitlines()
                        if line.strip() and not line.strip().startswith('#')]
        require(script_lines == ['set -eu',
                'exec java -XX:MaxRAMPercentage=65.0 -cp /opt/app/classes labs.CloudNativeApp "$@"'],
                'exec_entrypoint', 'The shared script must replace the shell with Java using exec')
    ignore_rules = [line.strip() for line in dockerignore.splitlines()
                    if line.strip() and not line.strip().startswith('#')]
    require(ignore_rules == ['*', '!src/', '!src/**', '!web/', '!web/**', '!container/',
                             '!container/Dockerfile', '!container/entrypoint.sh'],
            'build_context_allowlist', 'Keep the shared context allowlist; never admit secrets, answers, or tests')
    return list(EXPECTED_CASES)


def run(task, task_dir, materials_dir):
    if task != 'C11-01':
        raise InvalidEnvironment('This checker only grades C11-01')
    if not task_dir.is_dir() or not materials_dir.is_dir():
        raise InvalidEnvironment('Explicit task and materials directories must exist')
    cases = validate(read_input(task_dir / 'Dockerfile'), read_input(materials_dir / '.dockerignore'),
                     read_input(materials_dir / 'container/entrypoint.sh'))
    if cases != list(EXPECTED_CASES) or len(cases) == 0:
        raise InvalidEnvironment('Incomplete or zero-case structural result')
    return {'status': 'PASS', 'scope': SCOPE, 'docker_runtime': 'NOT_RUN', 'cases': cases}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--task', required=True)
    parser.add_argument('--task-dir', required=True, type=pathlib.Path)
    parser.add_argument('--materials-dir', required=True, type=pathlib.Path)
    args = parser.parse_args(argv)
    try:
        result = run(args.task, args.task_dir, args.materials_dir)
    except InvalidEnvironment as error:
        print(json.dumps({'status': 'INVALID_ENV', 'scope': SCOPE, 'detail': str(error)}))
        return 2
    except ContractViolation as error:
        print(json.dumps({'status': 'FAIL', 'scope': SCOPE, 'case_id': error.case_id, 'detail': str(error)}))
        return 1
    print(json.dumps(result))
    print('{} cases={} scope={} docker_runtime=NOT_RUN'.format(PASS_MARKER, len(result['cases']), SCOPE))
    return 0


if __name__ == '__main__':
    sys.exit(main())
