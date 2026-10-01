#!/usr/bin/env python3
"""Select real suites from a cumulative PR diff; never cache or reuse test results."""
from __future__ import annotations
import argparse
import json
import os
from pathlib import Path, PurePosixPath
import subprocess

SUITES = {
    'java-pilot': ['courses/java-recovery-collections/', 'instructor/java-pilot/'],
    'java-foundations': ['courses/java-foundations/'],
    'java-advanced': ['courses/java-concurrency/', 'courses/java-jvm/'],
    'java-frameworks': ['courses/java-frameworks/'],
    'data-storage': ['courses/data-storage/'],
    'messaging': ['courses/messaging/'],
    'distributed': ['courses/distributed-systems/'],
    'backend-capstone': ['courses/backend-capstone/'],
    'lab-environment': [],
}
SERVICE_SUITES = {'java-frameworks', 'data-storage', 'messaging', 'distributed',
                  'backend-capstone', 'lab-environment'}
REAL_JOBS = {
    'java-pilot': ['real-java-pilot'], 'java-foundations': ['real-java-foundations'],
    'java-advanced': ['real-java-concurrency', 'real-java-jvm'],
    'java-frameworks': ['real-java-frameworks-backend', 'real-java-frameworks-ui'],
    'data-storage': ['real-mysql', 'real-redis'], 'messaging': ['real-messaging'],
    'distributed': ['real-distributed'], 'backend-capstone': ['real-backend-capstone'],
    'lab-environment': ['real-lab-environment'],
}
COURSE_ROOTS = {
    'java-recovery-collections', 'java-foundations', 'java-concurrency', 'java-jvm',
    'java-frameworks', 'data-storage/mysql-engineering', 'data-storage/redis-engineering',
    'messaging', 'distributed-systems', 'backend-capstone',
}
LAB_SCRIPTS = {'scripts/lab.py', 'scripts/lab.sh', 'scripts/ci_smoke.py',
               'scripts/tests/test_lab.py', 'scripts/tests/test_ci_smoke.py',
               'scripts/tests/test_rocketmq.py'}
SYNC_SCRIPTS = {'scripts/sync_course_versions.py', 'scripts/course-versions-report.json',
                'scripts/tests/test_course_versions.py'}


def affected_suites(path: str) -> set[str]:
    """Unknown non-prose files fan out. Markdown is covered by all legacy validators."""
    path = str(PurePosixPath(path))
    if path.endswith('.md'):
        return set()
    if path.startswith('scripts/quality/'):
        return set(SUITES)  # Static and real three-phase grading share these scripts.
    if path.startswith('scripts/ci/') or path == '.github/workflows/ci.yml':
        return set(SUITES)
    for suite in SUITES:
        if path == f'.github/workflows/{suite}.yml':
            return {suite}
    result = {suite for suite, roots in SUITES.items() if any(path.startswith(root) for root in roots)}
    if path.startswith('courses/java-recovery-collections/'):
        result.add('lab-environment')  # Shared-image acceptance also builds the pilot.
    if result:
        return result
    if path.startswith('infra/'):
        return set(SERVICE_SUITES)
    if path in SYNC_SCRIPTS:
        return {'data-storage', 'java-frameworks', 'lab-environment'}
    if path in LAB_SCRIPTS:
        return {'lab-environment'}
    # New shared scripts, workflows, lock files or unclassified runtime assets.
    return set(SUITES)


def git(*args: str, root: Path) -> bytes:
    return subprocess.check_output(['git', *args], cwd=root)


def event_range(event_name: str, event: dict, root: Path) -> tuple[list[str], bool]:
    if event_name in {'workflow_dispatch', 'release', 'push'}:
        # Main is an independent full acceptance baseline, including docs pushes.
        return [], True
    if event_name != 'pull_request':
        raise ValueError(f'Unsupported event: {event_name}')
    pr = event['pull_request']
    base = git('merge-base', pr['base']['sha'], pr['head']['sha'], root=root).decode().strip()
    # IMPORTANT: never compare synchronize.before with head. A later docs commit
    # cannot erase a previous failing code change still present in this PR.
    raw = git('diff', '--name-only', '--no-renames', '-z', base, pr['head']['sha'], root=root)
    return [path.decode() for path in raw.split(b'\0') if path], False


def make_plan(*, changed: list[str], event_name: str, event: dict, repository: str,
              tested_sha: str, force_full: bool = False) -> dict:
    full = (force_full or event_name in {'workflow_dispatch', 'release', 'push'}
            or (event_name == 'pull_request' and
                (event.get('label', {}).get('name') == 'ci:full'
                 or any(label.get('name') == 'ci:full' for label in event['pull_request'].get('labels', [])))))
    required = set(SUITES) if full else set().union(*(affected_suites(path) for path in changed))
    return {'schema_version': 1, 'repository': repository, 'tested_sha': tested_sha,
            'head_sha': event.get('pull_request', {}).get('head', {}).get('sha', tested_sha),
            'event': event_name, 'full': full, 'changed_files': changed,
            'suites': {suite: {'decision': 'run' if suite in required else 'not-required',
                              'reason': ('全量验收' if full else 'PR累计变更影响本模块') if suite in required
                                        else '本PR累计差异不影响此模块；未运行'} for suite in SUITES}}


def validate_inventory(files: list[str]) -> list[str]:
    actual = {path.removeprefix('courses/').removesuffix('/course-info.yaml')
              for path in files if path.startswith('courses/') and path.endswith('/course-info.yaml')}
    return ([f'新增课程尚未配置真实CI与旧静态约束：{name}' for name in sorted(actual - COURSE_ROOTS)]
            + [f'已配置课程元数据缺失：{name}' for name in sorted(COURSE_ROOTS - actual)])


def write_outputs(plan: dict, output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(plan, ensure_ascii=False, indent=2) + '\n')
    if os.environ.get('GITHUB_OUTPUT'):
        compact = {key: value for key, value in plan.items() if key != 'changed_files'}
        with open(os.environ['GITHUB_OUTPUT'], 'a') as stream:
            stream.write('plan=' + json.dumps(compact, ensure_ascii=False, separators=(',', ':')) + '\n')
            for suite, row in plan['suites'].items():
                stream.write(f"{suite}={'true' if row['decision'] == 'run' else 'false'}\n")
    lines = ['## 验收计划（未运行不等于通过）', f"测试树：`{plan['tested_sha']}`"]
    lines += [f"- {suite}: **{row['decision']}** · {row['reason']}" for suite, row in plan['suites'].items()]
    print('\n'.join(lines))
    if os.environ.get('GITHUB_STEP_SUMMARY'):
        with open(os.environ['GITHUB_STEP_SUMMARY'], 'a') as stream:
            stream.write('\n'.join(lines) + '\n')


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=Path('.'))
    parser.add_argument('--output', type=Path, default=Path('build/ci/plan.json'))
    parser.add_argument('--check-inventory', action='store_true')
    parser.add_argument('--files-json', type=Path, help='Tracked path inventory for snapshots without .git')
    args = parser.parse_args()
    if args.check_inventory:
        files = json.loads(args.files_json.read_text()) if args.files_json else [p.decode() for p in git('ls-files','-z',root=args.root).split(b'\0') if p]
        errors = validate_inventory(files)
        print('\n'.join(errors) if errors else '10门课程均有显式真实CI/静态校验映射')
        return int(bool(errors))
    event_name = os.environ['GITHUB_EVENT_NAME']
    event = json.loads(Path(os.environ['GITHUB_EVENT_PATH']).read_text())
    tested_sha = git('rev-parse', 'HEAD', root=args.root).decode().strip()
    try:
        changed, force = event_range(event_name, event, args.root)
    except (subprocess.CalledProcessError, KeyError, ValueError):
        print('::warning::无法证明变更范围，保守执行全量')
        changed, force = [], True
    plan = make_plan(changed=changed, event_name=event_name, event=event,
                     repository=os.environ['GITHUB_REPOSITORY'], tested_sha=tested_sha, force_full=force)
    write_outputs(plan, args.output)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
