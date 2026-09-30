#!/usr/bin/env python3
"""静态检查课程可见性、UTF-16占位和标准解同步；不能替代Academy导入。"""
from pathlib import Path
import json
import yaml
ROOT = Path(__file__).resolve().parents[1]
course = yaml.safe_load((ROOT/'course-info.yaml').read_text())
assert course['language'] == 'Chinese'
assert course['environment_settings']['jvm_language_level'] == 'JDK_21'
manifest = json.loads((ROOT/'authoring/manifest.json').read_text())
assert len(manifest) in {6, 12}
found=[]
for section in course['content']:
    for lesson in yaml.safe_load((ROOT/section/'section-info.yaml').read_text())['content']:
        task = ROOT/section/lesson/'practice'
        doc = (task/'task.md').read_text()
        assert doc.count('```') % 2 == 0
        for heading in ['## 标准答案与逐步解析','## 完整调用示例','## 真实源码阅读与断点路线','## 面试问题、标准回答与追问','```text']:
            assert heading in doc, (task, heading)
        config = yaml.safe_load((task/'task-info.yaml').read_text())
        actual = {str(p.relative_to(task)) for p in task.rglob('*.java')}
        if (task/'gradle.lockfile').is_file(): actual.add('gradle.lockfile')
        assert actual == {f['name'] for f in config['files']}, task
        count=0
        for entry in config['files']:
            assert entry['visible'] is True
            source = (task/entry['name']).read_text()
            if entry['name'].startswith('src/'):
                assert '```java\n'+source+'```' in doc, task
            for placeholder in entry.get('placeholders',[]):
                raw = source.encode('utf-16-le')
                start = placeholder['offset']*2; end = start+placeholder['length']*2
                assert 0 <= start < end <= len(raw)
                selected = raw[start:end].decode('utf-16-le')
                assert selected.strip() and '学习区' not in selected and 'TODO' not in selected
                replaced = raw[:start]+placeholder['placeholder_text'].encode('utf-16-le')+raw[end:]
                assert 'TODO' in replaced.decode('utf-16-le')
                count+=1
        assert count == 1, task
        found.append(str(task.relative_to(ROOT)))
assert set(found) == {item['task'] for item in manifest}
assert 'Images.get("KAFKA_IMAGE")' in (ROOT/'support/src/labs/messaging/KafkaSupport.java').read_text()
assert 'Images.get("ROCKETMQ_IMAGE")' in (ROOT/'support/src/labs/messaging/RocketSupport.java').read_text()
assert all('disabledWithoutDocker' not in p.read_text() for p in ROOT.glob('*/**/test/*.java'))
for item in course['additional_files']:
    assert (ROOT/item['name']).is_file(), item
print('静态检查通过：', len(manifest), '节、全部源码测试可见、UTF-16占位与标准解同步')
