#!/usr/bin/env python3
"""检查学院元数据、全部可见测试、答案与字符偏移；不冒充IDE导入或数据库执行。"""
from pathlib import Path
import json
import yaml
ROOT=Path(__file__).resolve().parents[1]
course=yaml.safe_load((ROOT/'course-info.yaml').read_text())
count=0
for info in sorted((ROOT/'mysql').glob('*/*/task-info.yaml')):
    data=yaml.safe_load(info.read_text()); base=info.parent
    assert data['type']=='edu'
    listed={f['name'] for f in data['files']}
    actual={str(p.relative_to(base)) for p in base.rglob('*') if p.is_file() and (p.suffix=='.java' or p.name=='answer.md')}
    assert actual <= listed,(info,actual-listed)
    for f in data['files']:
        assert f.get('visible') is True
        text=(base/f['name']).read_text()
        for p in f.get('placeholders',[]):
            assert 0<=p['offset']<len(text) and p['length']>0
            answer=text[p['offset']:p['offset']+p['length']]
            assert answer.strip() and 'UnsupportedOperationException' not in answer
            assert p['offset']+p['length']<=len(text)
    body=(base/'task.md').read_text()
    for marker in ['企业','```text','标准答案','源码','面试','逐步','独立迁移']:
        assert marker in body,(info,marker)
    count+=1
for f in course['additional_files']:
    assert (ROOT/f['name']).is_file(),f
assert count==7
print(json.dumps({'任务':count,'结果':'静态结构与可见性通过，非IDE或集成验收'},ensure_ascii=False))
