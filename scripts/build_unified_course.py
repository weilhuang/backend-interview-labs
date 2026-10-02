#!/usr/bin/env python3
"""Build the reviewed 100-task course from maintained V1 sources and a sealed overlay.

Static files only: no Java, Go, Docker, network, dependency resolution or IDE.
The output must be a new directory. Every input, overlay and result is verified.
"""
from __future__ import annotations
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import sys

sys.dont_write_bytecode = True
os.environ['PYTHONDONTWRITEBYTECODE'] = '1'
import unify_course

CONTRACT = 'authoring/public-build-contract.json'
COUNTS = {'courses': 1, 'sections': 15, 'tasks': 100, 'placeholders': 159}

def require(condition, message):
    if not condition:
        raise ValueError(message)

def digest(data):
    return hashlib.sha256(data).hexdigest()

def canonical(value):
    return digest(json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False).encode('utf-8'))

def read_regular(path):
    require(path.is_file() and not path.is_symlink(), 'Expected a regular non-symlink file: ' + str(path))
    return path.read_bytes()

def safe_name(name):
    p = PurePosixPath(name)
    require(isinstance(name, str) and name and not p.is_absolute() and '\\' not in name
            and all(part not in ('', '.', '..') for part in name.split('/')),
            'Invalid manifest path: ' + repr(name))
    return name

def manifest(root):
    result = {}
    require(root.is_dir() and not root.is_symlink(), 'Invalid source directory: ' + str(root))
    for path in sorted(root.rglob('*')):
        require(not path.is_symlink(), 'Symlink is not a source asset: ' + str(path))
        if path.is_dir():
            continue
        require(path.is_file(), 'Special file is not a source asset: ' + str(path))
        result[safe_name(path.relative_to(root).as_posix())] = digest(read_regular(path))
    return result

def load_inputs(repo):
    root = repo / 'authoring/unified-course'
    value = json.loads(read_regular(root / 'manifest.json'))
    require(value.get('schema_version') == 1 and value.get('counts') == COUNTS, 'Unknown course input contract')
    for key in ('base_generated_manifest', 'overlay_manifest', 'expected_manifest'):
        require(isinstance(value.get(key), dict) and value[key], 'Missing manifest: ' + key)
        for name, sha in value[key].items():
            safe_name(name)
            require(isinstance(sha, str) and len(sha) == 64 and all(c in '0123456789abcdef' for c in sha), 'Invalid SHA256')
    require(manifest(root / 'overlay') == value['overlay_manifest'], 'Overlay differs from its exact allowlist')
    require(canonical(value['expected_manifest']) == value['full_manifest_sha256'], 'Expected full manifest is not sealed')
    reduced = dict(value['expected_manifest']); reduced.pop(CONTRACT)
    require(canonical(reduced) == value['source_manifest_sha256'], 'Expected payload manifest is not sealed')
    for name, sha in value['overlay_manifest'].items():
        require(value['expected_manifest'].get(name) == sha, 'Overlay/output hash mismatch: ' + name)
    return root, value

def validate_metadata(output):
    # Reuse the original public metadata/UTF-16 gate; independently compare task map.
    sys.path.insert(0, str(output / 'authoring/quality'))
    spec = importlib.util.spec_from_file_location('public_course_metadata_gate', output / 'authoring/quality/academy_gate.py')
    academy_gate = importlib.util.module_from_spec(spec); spec.loader.exec_module(academy_gate)
    model = academy_gate.inspect_course(output)
    mapping = json.loads(read_regular(output / 'authoring/course-map.json'))
    tasks = mapping['tasks']; support = mapping['support_projects']
    require(len(tasks) == COUNTS['tasks'] and len(mapping['sections']) == COUNTS['sections'], 'Course map counts differ')
    require(len(model['tasks']) == COUNTS['tasks'], 'Native task inventory differs')
    require(sum(len(regions) for regions in model['placeholders'].values()) == COUNTS['placeholders'], 'UTF-16 region count differs')
    require(len({t['path'] for t in tasks}) == len(tasks), 'Duplicate task path')
    require(len({t['gradle_project'] for t in tasks + support}) == len(tasks + support), 'Duplicate Gradle project')
    actual = {p.parent.relative_to(output).as_posix() for p in output.rglob('task-info.yaml')}
    require(actual == {t['path'] for t in tasks}, 'Undeclared or missing task')
    for task in tasks + support:
        require((output / 'dependency-locks' / (task['gradle_project'][1:] + '.lockfile')).is_file(), 'Final-path strict lock missing')
    return model

def build(repo, output, report=None):
    repo = repo.resolve(); output = output.resolve()
    root, inputs = load_inputs(repo)
    require(not output.exists(), 'Output must not exist; learner work is never overwritten')
    require(not output.is_relative_to(repo / 'authoring') and not repo.is_relative_to(output), 'Output overlaps maintained authoring inputs')
    if report is not None:
        report = report.resolve()
        require(not report.exists() and not report.is_relative_to(output), 'Report must be a new file outside the course output')
        require(not report.is_relative_to(repo) or report.is_relative_to(repo / 'build'), 'In-repository reports belong under build/')
    base_report = unify_course.build(repo, output)
    require(manifest(output) == inputs['base_generated_manifest'], 'V1 generator or authoring source drift; update/review the sealed overlay explicitly')
    for name in inputs['overlay_manifest']:
        target = output / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(root / 'overlay' / name, target)
        if target.suffix == '.sh':
            target.chmod(0o755)
    actual = manifest(output)
    require(actual == inputs['expected_manifest'], 'Generated course differs from sealed expected output')
    contract_bytes = read_regular(output / CONTRACT)
    contract = json.loads(contract_bytes)
    reduced = dict(actual); reduced.pop(CONTRACT)
    require(contract.get('counts') == COUNTS, 'Public contract count mismatch')
    require(contract.get('source_manifest_sha256') == canonical(reduced) == inputs['source_manifest_sha256'], 'Public contract payload binding mismatch')
    require(contract.get('course_map_sha256') == digest(read_regular(output / 'authoring/course-map.json')), 'Public contract map binding mismatch')
    model = validate_metadata(output)
    docs_spec = importlib.util.spec_from_file_location('unified_public_docs', repo / 'scripts/ci/validate_docs.py')
    docs_module = importlib.util.module_from_spec(docs_spec); docs_spec.loader.exec_module(docs_module)
    docs = docs_module.validate(output, list(actual))
    require(docs['status'] == 'passed' and not docs['errors'], 'Generated course documentation links or anchors differ: ' + repr(docs['errors']))
    result = {'status': 'PASS', 'kind': 'static-only', **COUNTS, 'counts': COUNTS,
              'assets': len(model['assets']), 'source_files': len(actual), 'documentation_links': docs['checked_links'],
              'source_manifest_sha256': canonical(reduced), 'full_manifest_sha256': canonical(actual),
              'course_map_sha256': contract['course_map_sha256'], 'public_contract_sha256': digest(contract_bytes),
              'reviewed_source_manifest_sha256': inputs['reviewed_source_manifest_sha256'],
              'v1_generation': base_report, 'native_idea': 'NOT_RUN', 'gradle': 'NOT_RUN',
              'go': 'NOT_RUN', 'docker': 'NOT_RUN', 'full_course_runtime': 'NOT_RUN'}
    if report is not None:
        report.parent.mkdir(parents=True, exist_ok=True)
        with report.open('x', encoding='utf-8') as stream:
            json.dump(result, stream, ensure_ascii=False, indent=2); stream.write('\n')
    return result

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo', type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--report', type=Path)
    args = parser.parse_args()
    print(json.dumps(build(args.repo, args.output, args.report), ensure_ascii=False, indent=2))

if __name__ == '__main__':
    main()
