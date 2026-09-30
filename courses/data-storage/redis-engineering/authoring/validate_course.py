#!/usr/bin/env python3
"""检查文件可见性、实现区、镜像同源和完整教学段落。"""
from pathlib import Path
import yaml
ROOT=Path(__file__).resolve().parents[1]
course=yaml.safe_load((ROOT/'course-info.yaml').read_text()); assert course['type']=='marketplace'
count=0
for path in sorted((ROOT/'redis').glob('*/task-info.yaml')):
    task=path.parent; meta=yaml.safe_load(path.read_text()); assert meta['type']=='edu';count+=1
    declared={f['name'] for f in meta['files']}
    actual={str(p.relative_to(task)) for p in task.rglob('*.java')}; assert actual<=declared,(task,actual-declared)
    placeholders=0
    for item in meta['files']:
        target=task/item['name'];assert target.is_file(),target;assert item.get('visible',False),target
        for place in item.get('placeholders',[]):
            text=target.read_text();start=place['offset'];end=start+place['length'];assert 0<=start<end<=len(text)
            assert '学员实现开始' in text[:start] and text[end:].lstrip().startswith('// 学员实现结束'); assert 'UnsupportedOperationException' in place['placeholder_text'];placeholders+=1
            assert '```java\n'+text+'```' in (task/'solution.md').read_text(), (task,'标准解未同步')
    assert placeholders==1
    body=(task/'task.md').read_text(); assert len(body)>2800,(task,'教案过短')
    for heading in ['企业场景','ASCII','编码步骤','标准解','真实源码','面试','独立迁移']:assert heading in body,(task,heading)
    assert '```' in body;assert '不' in body
for item in course['additional_files']:assert (ROOT/item['name']).is_file(),item
for path in (ROOT/'redis').rglob('*.java'):
    text=path.read_text();assert 'FLUSHALL' not in text and 'flushAll(' not in text
    assert 'redis:7' not in text and 'mysql:8' not in text
assert count==7,count
print('PASS：7个完整Academy任务；全部源码/测试/标准解可见；镜像引用无重复常量')
