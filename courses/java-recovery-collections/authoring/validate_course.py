#!/usr/bin/env python3
"""离线检查作者课程元数据；不替代真正的Academy导入器。"""
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
    # Academy偏移按Java UTF-16代码单元计数，不是UTF-8字节数。
    raw = source.encode('utf-16-le')
    for p in sorted(placeholders, key=lambda p: p['offset'], reverse=True):
        start, end = p['offset'] * 2, (p['offset'] + p['length']) * 2
        raw = raw[:start] + p['placeholder_text'].encode('utf-16-le') + raw[end:]
    return raw.decode('utf-16-le')

def validate():
    course = read_yaml(ROOT / 'course-info.yaml')
    assert course['yaml_version'] == 2
    assert course['language'] == 'Chinese' and course['programming_language'] == 'Java'
    assert course['environment_settings']['jvm_language_level'] == 'JDK_21'
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
                assert '## 标准答案与逐步解析' in (task / 'task.md').read_text()
                assert '## 完整调用示例' in (task / 'task.md').read_text()
                assert all('### 提示'+str(i) in (task / 'task.md').read_text() for i in [1,2,3])
                assert 'jdk-21%2B35' in (task / 'task.md').read_text()
                assert len(config['files']) == len({f['name'] for f in config['files']})
                task_placeholders = 0
                for file in config['files']:
                    path = safe_file(task, file['name'])
                    source = path.read_text(encoding='utf-8')
                    assert file['visible'] is True, path
                    if file['name'].startswith('src/'):
                        assert '```java\n' + source + '```' in (task / 'task.md').read_text(), f'题面代码不同步: {path}'
                    prev_end = 0
                    for p in file.get('placeholders', []):
                        assert set(p) == {'offset','length','placeholder_text'}, (path,p)
                        assert p['offset'] >= prev_end and p['length'] > 0, path
                        prev_end = p['offset'] + p['length']
                        assert prev_end <= len(source.encode('utf-16-le')) // 2, path
                        assert 'TODO' in p['placeholder_text']
                        task_placeholders += 1
                    if file['name'].startswith('src/') and file.get('placeholders'):
                        assert file['visible'] is True
                        assert 'TODO' not in source
                        assert 'TODO' in student_source(source,file.get('placeholders',[]))
                    if file['name'].startswith('test/'):
                        assert file['visible'] is True
                assert task_placeholders > 0
                assert {f['name'] for f in config['files']} == {str(p.relative_to(task)) for p in task.rglob('*.java')}, task
                assert (task / 'task.md').read_text().count('```') % 2 == 0, task
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
    assert 'README.md' not in ignored
    assert 'jvmVersion=21' in (ROOT/'gradle.properties').read_text()
    assert 'options.release = 21' in (ROOT/'build.gradle').read_text()
    result={'tasks':len(found),'placeholders':placeholders_count,'metadata':'passed','placeholder_offsets':'UTF-16 checked','academy_importer':'not run'}
    print(json.dumps(result,ensure_ascii=False,indent=2))
    return result

if __name__ == '__main__':
    validate()
