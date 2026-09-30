#!/usr/bin/env python3
"""Read-only audit of a real Academy archive against its author source.

Does not generate an official archive, decrypt answers, invoke IDEA or import it.
Supports the observed version-23, regular-lesson Java archive format only.
"""
import argparse
import json
from pathlib import Path
import stat
import sys
import zipfile

from academy_gate import REPO, digest, inspect_course, relative_path, replace_placeholders, require

# The native Java importer generates these. Their absence is expected in the
# observed official exports; verifying their regeneration still requires IDEA.
GENERATED_WRAPPERS = {'gradlew', 'gradlew.bat', 'gradle/wrapper/gradle-wrapper.jar'}


def inspect_archive(source, archive, imported=None):
    model = inspect_course(source)
    result = {'schema_version': 1, 'status': 'PASS', 'native_idea': 'NOT_RUN',
              'native_archive_import': 'NOT_RUN', 'kind': 'read-only real archive content comparison',
              'archive_sha256': digest(archive.read_bytes()), 'course': source.name, 'tasks': [],
              'archive_payload': 'OPAQUE: native encryption, not decrypted by this gate',
              'imported_plaintext': 'NOT_RUN' if imported is None else 'RUNNING'}
    with zipfile.ZipFile(archive) as z:
        infos = z.infolist()
        require(len(infos) == len({f.filename for f in infos}), 'duplicate archive members')
        require(sum(f.file_size for f in infos) < 128 * 1024 * 1024, 'archive exceeds inspection limit')
        for f in infos:
            relative_path(f.filename.rstrip('/'))
            require(stat.S_IFMT(f.external_attr >> 16) in (0, stat.S_IFREG, stat.S_IFDIR), 'unsupported archive member type')
        names = set(z.namelist())
        data = json.loads(z.read('course.json'))
        require(data.get('version') == 23, f'unsupported archive format: {data.get("version")}')
        require(data.get('environment_settings', {}).get('jvm_language_level') == 'JDK_21', 'archive JDK must be 21')
        result['archive_format'] = data['version']
        result['exporter_version'] = data.get('edu_plugin_version')
        found = {}

        def walk(container, prefix=''):
            for item in container.get('items', []):
                title = item.get('title')
                relative_path(title)
                walk(item, prefix + title + '/')
            for task in container.get('task_list', []):
                name = task.get('name')
                relative_path(name)
                path = prefix + name
                require(path not in found, f'duplicate exported task: {path}')
                found[path] = task

        walk(data)
        require(set(found) == {t['path'] for t in model['tasks']}, 'exported task set differs from author hierarchy')
        expected_contents = set()
        for task in model['tasks']:
            path = task['path']
            exported = found[path]
            require(exported.get('task_type') == 'edu', f'{path}: wrong task type')
            description = (source / path / 'task.md').read_text(encoding='utf-8')
            require(exported.get('description_text') == description, f'{path}: exported task description differs')
            from academy_gate import read_yaml
            meta = read_yaml(source / path / 'task-info.yaml')
            require(set(exported['files']) == {f['name'] for f in meta['files']}, f'{path}: exported file set differs')
            for f in meta['files']:
                name = f['name']
                entry = exported['files'][name]
                require(entry.get('is_visible') is True, f'{path}/{name}: hidden in official archive')
                content_path = f'contents/{path}/{name}'
                expected_contents.add(content_path)
                original = (source / path / name).read_bytes()
                ph = f.get('placeholders', [])
                require(len(entry.get('placeholders', [])) == len(ph), f'{path}/{name}: placeholder count mismatch')
                if ph:
                    learner, _ = replace_placeholders(original.decode('utf-8'), ph)
                    expected = learner.encode('utf-8')
                    delta = 0
                    for src_ph, exported_ph in zip(ph, entry['placeholders']):
                        length = len(src_ph['placeholder_text'].encode('utf-16-le')) // 2
                        require(exported_ph.get('offset') == src_ph['offset'] + delta and exported_ph.get('length') == length,
                                f'{path}/{name}: shifted learner UTF-16 offset/length mismatch')
                        require(exported_ph.get('placeholder_text') == src_ph['placeholder_text'] and isinstance(exported_ph.get('possible_answer'), str) and bool(exported_ph['possible_answer'].strip()),
                                f'{path}/{name}: missing placeholder text/answer payload')
                        delta += length - src_ph['length']
                else:
                    expected = original
                require(content_path in names and bool(z.read(content_path)), f'{content_path}: missing or empty encrypted payload')
                if imported is not None:
                    from academy_gate import local_file
                    require(local_file(imported, path + '/' + name).read_bytes() == expected,
                            f'{path}/{name}: native-imported plaintext differs from expected learner source')
            result['tasks'].append({'path': path, 'status': 'PASS', 'placeholders': task['placeholders']})
        additional = data.get('additional_files', [])
        extra_names = [f['name'] for f in additional]
        require(len(extra_names) == len(set(extra_names)), 'duplicate exported additional file')
        declared = {f['name'] for f in read_yaml(source / 'course-info.yaml').get('additional_files', [])}
        require(set(extra_names) == declared - GENERATED_WRAPPERS, 'exported additional asset set differs (apart from native-generated wrappers)')
        for name in extra_names:
            relative_path(name)
            content_path = f'contents/{name}'
            expected_contents.add(content_path)
            require(content_path in names and bool(z.read(content_path)), f'{content_path}: missing or empty encrypted payload')
            if imported is not None:
                require(local_file(imported, name).read_bytes() == (source / name).read_bytes(),
                        f'{name}: native-imported additional asset differs from source')
        require({n for n in names if n.startswith('contents/') and not n.endswith('/')} == expected_contents,
                'unexpected contents asset in official archive')
        allowed = expected_contents | {'course.json', 'courseIcon.svg'}
        require({n for n in names if not n.endswith('/')} <= allowed,
                'unexpected root asset in official archive')
        result['assets'] = len(expected_contents)
        if imported is not None:
            result['imported_plaintext'] = 'PASS (read existing native import only; no IDE operation)'
            result['imported_directory'] = str(imported)
        result['native_generated_wrappers'] = 'NOT_RUN: regeneration is the IDEA importer responsibility'
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--course', required=True)
    parser.add_argument('--archive', type=Path, required=True)
    parser.add_argument('--report', type=Path, required=True)
    parser.add_argument('--imported-dir', type=Path, help='Existing untouched native learner import to compare read-only')
    args = parser.parse_args(argv)
    try:
        result = inspect_archive(REPO / 'courses' / relative_path(args.course), args.archive.resolve(), args.imported_dir.resolve() if args.imported_dir else None)
    except Exception as error:
        result = {'schema_version': 1, 'status': 'FAIL', 'native_idea': 'NOT_RUN', 'error': str(error)}
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(f'{result["status"]}: {args.report}; native IDEA: NOT_RUN')
    if result.get('error'):
        print(result['error'], file=sys.stderr)
    return 0 if result['status'] == 'PASS' else 1


if __name__ == '__main__':
    sys.exit(main())
