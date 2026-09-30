#!/usr/bin/env python3
"""Conservative offline checks of our author-mode metadata, not an Academy importer."""
from pathlib import Path
import argparse, hashlib, json
import yaml

ROOT = Path(__file__).resolve().parents[1]

def read_yaml(path):
    class UniqueKeys(yaml.SafeLoader):
        pass
    def mapping(loader, node, deep=False):
        result = {}
        for key, value in node.value:
            key = loader.construct_object(key, deep=deep)
            if key in result:
                raise ValueError(f'{path}: duplicate YAML key {key}')
            result[key] = loader.construct_object(value, deep=deep)
        return result
    UniqueKeys.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, mapping)
    return yaml.load(path.read_text(encoding='utf-8'), Loader=UniqueKeys)

def safe_file(root, relative):
    p = (root / relative).resolve()
    if not p.is_relative_to(root.resolve()) or not p.is_file():
        raise ValueError(f'Unsafe or missing file: {relative}')
    return p

def student_source(source, placeholders):
    # Academy offsets are Java UTF-16 code units, not UTF-8 byte offsets.
    raw = source.encode('utf-16-le')
    for p in sorted(placeholders, key=lambda p: p['offset'], reverse=True):
        start, end = p['offset'] * 2, (p['offset'] + p['length']) * 2
        raw = raw[:start] + p['placeholder_text'].encode('utf-16-le') + raw[end:]
    return raw.decode('utf-16-le')

def validate():
    course = read_yaml(ROOT / 'course-info.yaml')
    assert course['yaml_version'] == 2
    assert course['language'] == 'Chinese' and course['programming_language'] == 'Java'
    assert course['environment_settings']['jvm_language_level'] == 'JDK_17'
    found, placeholders_count = [], 0
    for section_name in course['content']:
        section = ROOT / section_name
        for lesson_name in read_yaml(section / 'section-info.yaml')['content']:
            lesson = section / lesson_name
            for task_name in read_yaml(lesson / 'lesson-info.yaml')['content']:
                task = lesson / task_name
                config = read_yaml(task / 'task-info.yaml')
                assert config['type'] == 'edu'
                assert (task / 'task.md').is_file()
                assert '<div class="hint"' in (task / 'task.md').read_text()
                assert 'jdk-17%2B35' in (task / 'task.md').read_text()
                assert len(config['files']) == len({f['name'] for f in config['files']})
                task_placeholders = 0
                for file in config['files']:
                    path = safe_file(task, file['name'])
                    source = path.read_text(encoding='utf-8')
                    prev_end = 0
                    for p in file.get('placeholders', []):
                        assert set(p) == {'offset','length','placeholder_text'}, (path,p)
                        assert p['offset'] >= prev_end and p['length'] > 0, path
                        prev_end = p['offset'] + p['length']
                        assert prev_end <= len(source.encode('utf-16-le')) // 2, path
                        assert 'TODO' in p['placeholder_text']
                        task_placeholders += 1
                    if file['name'].startswith('src/'):
                        assert file['visible'] is True
                        assert 'TODO' not in source
                        assert 'TODO' in student_source(source,file.get('placeholders',[]))
                    if file['name'].startswith('test/'):
                        assert file['visible'] is file['name'].endswith('ExamplesTest.java')
                assert task_placeholders > 0
                placeholders_count += task_placeholders
                found.append(str(task.relative_to(ROOT)))
    actual = {str(p.parent.relative_to(ROOT)) for p in (ROOT/'java-pilot').rglob('task-info.yaml')}
    assert set(found) == actual and len(found) == len(set(found)) == 12
    manifest = json.loads((ROOT/'authoring/manifest.json').read_text())
    assert set(found) == {x['task'] for x in manifest}
    for file in course['additional_files']:
        safe_file(ROOT, file['name'])
        assert 'instructor' not in file['name'] and 'authoring' not in file['name']
    wrapper = ROOT/'gradle/wrapper/gradle-wrapper.jar'
    assert hashlib.sha256(wrapper.read_bytes()).hexdigest() == 'a8451eeda314d0568b5340498b36edf147a8f0d692c5ff58082d477abe9146e4'
    ignored=(ROOT/'.courseignore').read_text().splitlines()
    assert '/authoring' in ignored and '/build' in ignored
    result={'tasks':len(found),'placeholders':placeholders_count,'metadata':'passed','placeholder_offsets':'UTF-16 checked','academy_importer':'not run'}
    print(json.dumps(result,ensure_ascii=False,indent=2))
    return result

if __name__ == '__main__':
    validate()
