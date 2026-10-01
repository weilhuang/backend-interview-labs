#!/usr/bin/env python3
"""Offline integrity/drift check of recorded official exports, never a native GUI run.

Opaque ZIP payloads are not decrypted. Native-import hashes are recorded evidence,
not cryptographic proof of exporter origin or a fresh import of the archive.
"""
import argparse
import json
import os
from pathlib import Path
import shutil
import stat
import sys
import tempfile
import zipfile

import yaml

from academy_gate import digest, inspect_course, local_file, read_yaml, replace_placeholders, require
from archive_contract import GENERATED_WRAPPERS, inspect_archive

COURSES = {
    'java-foundations': ('java-foundations', 16, 29),
    'java-concurrency': ('java-concurrency', 8, 17),
    'java-jvm': ('java-jvm', 7, 10),
    'java-frameworks': ('java-frameworks', 14, 20),
    'mysql': ('data-storage/mysql-engineering', 7, 7),
    'redis': ('data-storage/redis-engineering', 7, 7),
    'messaging': ('messaging', 12, 12),
    'distributed': ('distributed-systems', 8, 25),
    'capstone': ('backend-capstone', 5, 9),
}
OMISSIONS = {'mysql': {'.courseignore'}, 'messaging': {'.courseignore'}}
OVERLAYS = {
    'messaging': {'README.md': 'replace', 'shared/versions.env': 'add',
                  'shared/source-manifest.json': 'add'},
    'distributed': {'shared/versions.env': 'add', '中文阶段报告.md': 'replace'},
    'capstone': {'中文阶段报告.md': 'replace'},
}
RUNTIME = {name: 'NOT_RUN' for name in
           ('native_idea', 'native_archive_import', 'native_reset', 'docker', 'java', 'gradle')}


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        require(key not in result, f'duplicate JSON key: {key}')
        result[key] = value
    return result


def read_json(path):
    return json.loads(path.read_text(encoding='utf-8'), object_pairs_hook=unique_object)


def verify_file(root, record):
    path = local_file(root, record['path'])
    data = path.read_bytes()
    require(len(data) == record['bytes'] and digest(data) == record['sha256'],
            f'integrity mismatch: {record["path"]}')
    return path


def learner_assets(root, model):
    """Exact plaintext inventory expected after native import, excluding metadata."""
    assets = {}
    for task in model['tasks']:
        for entry in read_yaml(root / task['path'] / 'task-info.yaml')['files']:
            name = task['path'] + '/' + entry['name']
            data = local_file(root, name).read_bytes()
            if entry.get('placeholders'):
                data = replace_placeholders(data.decode('utf-8'), entry['placeholders'])[0].encode('utf-8')
            assets[name] = digest(data)
    for entry in read_yaml(root / 'course-info.yaml')['additional_files']:
        name = entry['name']
        if name not in GENERATED_WRAPPERS:
            assets[name] = digest(local_file(root, name).read_bytes())
    return assets


def check_archive_metadata(source, archive):
    with zipfile.ZipFile(archive) as zipped:
        for member in zipped.infolist():
            kind = stat.S_IFMT(member.external_attr >> 16)
            expected_kind = stat.S_IFDIR if member.is_dir() else stat.S_IFREG
            require(kind in (0, expected_kind), 'archive member filename/type mismatch')
        exported = json.loads(zipped.read('course.json'), object_pairs_hook=unique_object)
    metadata = read_yaml(source / 'course-info.yaml')
    require(metadata['type'] == 'marketplace' and metadata['language'] == 'Chinese'
            and metadata['programming_language'] == 'Java', 'unsupported course identity mapping')
    expected = {'title': metadata['title'], 'summary': metadata['summary'], 'language': 'zh',
                'programming_language_id': 'JAVA', 'course_type': 'Marketplace'}
    require(all(exported.get(key) == value for key, value in expected.items()), 'exported course identity differs')

    def source_tree(directory, data):
        tree = []
        for name in data['content']:
            child = directory / name
            config = next(child / (kind + '-info.yaml') for kind in ('section', 'lesson', 'task')
                          if (child / (kind + '-info.yaml')).is_file())
            tree.append(('task', name) if config.name == 'task-info.yaml'
                        else ('container', name, source_tree(child, read_yaml(config))))
        return tree

    def archive_tree(data):
        return [('container', child['title'], archive_tree(child)) for child in data.get('items', [])] + [
            ('task', task['name']) for task in data.get('task_list', [])]

    require(source_tree(source, metadata) == archive_tree(exported), 'exported hierarchy/order differs')


def check_course(course_id, record, repo, release):
    course_path, tasks, regions = COURSES[course_id]
    require(record['source_root'] == 'courses/' + course_path, 'wrong source mapping')
    require(record['tasks'] == tasks and record['placeholders'] == regions, 'wrong release counts')
    source = repo / record['source_root']
    model = inspect_course(source)
    require(len(model['tasks']) == tasks and sum(t['placeholders'] for t in model['tasks']) == regions,
            'source task/placeholder count drift')
    current = {name: digest(local_file(source, name).read_bytes()) for name in model['assets']}
    require(current == record['current_source_assets'], 'current declared source inventory/hash drift')
    if record['status'] == 'NOT_READY':
        require('archive' not in record and 'native_import_inventory' not in record,
                'NOT_READY course must not masquerade as a recorded ready export')
        return {'course': course_id, 'status': 'NOT_READY', 'reason': record['reason'], **RUNTIME}
    require(record['status'] == 'READY', 'unknown course readiness status')
    archive = verify_file(release, record['archive'])
    inventory_path = verify_file(release, record['native_import_inventory'])
    inventory = read_json(inventory_path)
    require(inventory['schema_version'] == 1, 'unsupported native import inventory schema')
    require(inventory['fresh_native_execution'] == RUNTIME, 'recorded inventory must not claim fresh native/runtime execution')
    require(inventory['kind'] == 'recorded-existing-native-import-plaintext', 'wrong provenance kind')
    require(inventory['archive_sha256'] == record['archive']['sha256'], 'import inventory/archive mismatch')
    require(bool(inventory['observed_at_utc']) and bool(inventory['evidence_reference']),
            'missing recorded import provenance')
    require(set(record['omitted_additional_files']) == OMISSIONS.get(course_id, set()),
            'unapproved exporter omission')
    overlays = record['packaging_overlays']
    require(len(overlays) == len({entry['target'] for entry in overlays}), 'duplicate overlay')
    require({entry['target']: entry['operation'] for entry in overlays} == OVERLAYS.get(course_id, {}),
            'unapproved packaging overlay')
    # A temporary projection preserves canonical files and the actual official ZIP.
    with tempfile.TemporaryDirectory(prefix='official-release-') as directory:
        projected = Path(directory)
        for name in model['assets']:
            target = projected / name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(local_file(source, name), target)
        metadata = read_yaml(projected / 'course-info.yaml')
        declared = {entry['name'] for entry in metadata['additional_files']}
        for entry in overlays:
            target = entry['target']
            original = current.get(target)
            require(entry['source_sha256'] == original, f'{target}: overlay source hash mismatch')
            require((target in declared) == (entry['operation'] == 'replace'), 'invalid overlay operation')
            payload = verify_file(release, entry)
            if target == 'shared/versions.env':
                require(payload.read_bytes() == local_file(repo, 'infra/versions.env').read_bytes(),
                        'staged ledger differs from canonical infra/versions.env')
            destination = projected / target
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(payload, destination)
            if entry['operation'] == 'add':
                metadata['additional_files'].append({'name': target})
        if course_id == 'messaging':
            ledger_record = read_json(projected / 'shared/source-manifest.json')
            require(ledger_record['SHA256'] == digest((projected / 'shared/versions.env').read_bytes()),
                    'staged ledger provenance hash mismatch')
        omitted = set(record['omitted_additional_files'])
        require(omitted <= declared, 'omission is not a declared source asset')
        metadata['additional_files'] = [entry for entry in metadata['additional_files'] if entry['name'] not in omitted]
        (projected / 'course-info.yaml').write_text(yaml.safe_dump(metadata, allow_unicode=True), encoding='utf-8')
        projected_model = inspect_course(projected)
        report = inspect_archive(projected, archive)
        check_archive_metadata(projected, archive)
        require(report['exporter_version'] == record['exporter_version'], 'exporter version mismatch')
        require(learner_assets(projected, projected_model) == inventory['assets'],
                'recorded native-import plaintext inventory differs from projected learner/assets')
    return {'course': course_id, 'status': 'PASS', 'tasks': tasks, 'placeholders': regions,
            'assets': report['assets'], 'archive_sha256': report['archive_sha256'],
            'recorded_import_inventory': 'MATCH: recorded evidence only, not a fresh import', **RUNTIME}


def check_release(repo, manifest_path):
    manifest = read_json(manifest_path)
    require(manifest['schema_version'] == 1, 'unsupported release manifest schema')
    require(manifest['source_base_commit'] == 'f5b0d493573f241bf6ea2bad3318911debd7f74f',
            'unexpected tested source base; review before changing the release baseline')
    records = manifest['courses']
    require(set(records) == set(COURSES), 'release must contain exactly nine full courses, excluding pilot')
    release = manifest_path.parent
    expected_archives = {r['archive']['path'] for r in records.values() if r['status'] == 'READY'}
    require(len(expected_archives) == sum(r['status'] == 'READY' for r in records.values()), 'duplicate archive path')
    actual_archives = {p.relative_to(release).as_posix() for p in (release / 'archives').rglob('*')
                       if p.is_file() or p.is_symlink()}
    require(actual_archives == expected_archives, 'release ZIP inventory differs from manifest')
    rows = []
    for course_id, record in records.items():
        try:
            rows.append(check_course(course_id, record, repo, release))
        except Exception as error:
            rows.append({'course': course_id, 'status': 'FAIL', 'error': str(error), **RUNTIME})
    status = 'FAIL' if any(r['status'] == 'FAIL' for r in rows) else (
        'NOT_READY' if any(r['status'] == 'NOT_READY' for r in rows) else 'PASS')
    return {'schema_version': 1, 'status': status, **RUNTIME,
            'scope': 'Offline recorded-export integrity, declared assets and current-source drift',
            'limitations': 'No decryption, cryptographic exporter-origin proof, fresh native import, Check or Reset',
            'source_base_commit': manifest['source_base_commit'],
            'source_snapshot': 'Current declared source hashes plus explicit post-base source/packaging provenance; the recorded base is not a claim that every current file existed at that commit',
            'expected_courses': len(COURSES), 'expected_tasks': sum(c[1] for c in COURSES.values()),
            'expected_placeholders': sum(c[2] for c in COURSES.values()), 'courses': rows}


def preflight_report(repo, manifest, report):
    """Only new build/quality or external temporary outputs; never clobber inputs."""
    require('..' not in report.parts, 'report path traversal is unsupported')
    target = report.absolute()
    require(not target.exists() and not target.is_symlink(), 'report already exists')
    require(not any(parent.is_symlink() for parent in target.parents), 'report has a symlink parent')
    resolved = target.resolve()
    require(not resolved.is_relative_to(manifest.parent), 'report is inside protected release inputs')
    build_reports = repo / 'build/quality'
    temporary = Path(tempfile.gettempdir()).resolve()
    allowed_build = resolved.is_relative_to(build_reports) and resolved != build_reports
    allowed_temp = resolved.is_relative_to(temporary) and not resolved.is_relative_to(repo)
    require(allowed_build or allowed_temp, 'report must be a new build/quality or external temporary file')
    return target


def write_report_exclusive(output, report):
    """Pin each parent directory, so late symlinks cannot redirect report writes."""
    require(hasattr(os, 'O_DIRECTORY') and hasattr(os, 'O_NOFOLLOW')
            and os.open in os.supports_dir_fd and os.mkdir in os.supports_dir_fd,
            'safe descriptor-relative report writing is unsupported on this platform')
    directory_flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
    parent_fd = os.open(output.anchor, directory_flags)
    try:
        for component in output.parts[1:-1]:
            try:
                next_fd = os.open(component, directory_flags, dir_fd=parent_fd)
            except FileNotFoundError:
                try:
                    os.mkdir(component, dir_fd=parent_fd)
                except FileExistsError:
                    pass
                next_fd = os.open(component, directory_flags, dir_fd=parent_fd)
            os.close(parent_fd)
            parent_fd = next_fd
        fd = os.open(output.name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                     0o600, dir_fd=parent_fd)
        with os.fdopen(fd, 'w', encoding='utf-8') as stream:
            stream.write(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
            expected = os.fstat(stream.fileno())
        require(not any(parent.is_symlink() for parent in output.parents), 'report parent changed during write')
        actual = output.stat(follow_symlinks=False)
        require((actual.st_dev, actual.st_ino) == (expected.st_dev, expected.st_ino), 'report path changed during write')
    finally:
        os.close(parent_fd)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo', type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument('--manifest', type=Path, required=True)
    parser.add_argument('--report', type=Path, required=True)
    args = parser.parse_args(argv)
    repo, manifest = args.repo.resolve(), args.manifest.resolve()
    try:
        output = preflight_report(repo, manifest, args.report)
    except Exception as error:
        print(f'FAIL: unsafe report destination; no report written: {error}', file=sys.stderr)
        return 1
    try:
        report = check_release(repo, manifest)
    except Exception as error:
        report = {'schema_version': 1, 'status': 'FAIL', 'error': str(error), **RUNTIME}
    try:
        preflight_report(repo, manifest, output)
        write_report_exclusive(output, report)
    except Exception as error:
        print(f'FAIL: report output failed: {error}', file=sys.stderr)
        return 1
    print(f'{report["status"]}: {output}; native/Docker execution: NOT_RUN')
    return {'PASS': 0, 'FAIL': 1, 'NOT_READY': 2}[report['status']]


if __name__ == '__main__':
    sys.exit(main())
