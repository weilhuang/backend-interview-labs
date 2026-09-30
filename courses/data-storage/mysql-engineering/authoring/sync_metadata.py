#!/usr/bin/env python3
"""格式调整后同步占位区与公开答案；不改变教学正文或隐藏任何测试。"""
from pathlib import Path
import re,yaml
r=Path(__file__).resolve().parents[1]
for info in (r/'mysql').glob('*/*/task-info.yaml'):
 d=yaml.safe_load(info.read_text());base=info.parent
 for f in d['files']:
  if 'placeholders' not in f:continue
  text=(base/f['name']).read_text();begin=re.search(r'(?m)^[ \t]*// BEGIN_STUDENT\n',text);end=re.search(r'(?m)^[ \t]*// END_STUDENT',text)
  assert begin and end
  f['placeholders'][0]['offset']=begin.end();f['placeholders'][0]['length']=end.start()-begin.end()
 listed={f['name'] for f in d['files']}
 for p in sorted(base.glob('src/labs/*.java'))+sorted(base.glob('test/*.java')):
  name=str(p.relative_to(base))
  if name not in listed:d['files'].append({'name':name,'visible':True})
 info.write_text(yaml.safe_dump(d,allow_unicode=True,sort_keys=False))
 answer=base/'answer.md';s=answer.read_text()
 target=next(f for f in d['files'] if 'placeholders' in f)
 code=(base/target['name']).read_text();s=re.sub(r'```java\n.*?```',lambda _: '```java\n'+code+'```',s,count=1,flags=re.S)
 # 调用端是第二个Java代码块；额外实现直接追加公开代码。
 blocks=list(re.finditer(r'```java\n.*?```',s,re.S))
 if len(blocks)>=2:
  block=blocks[1];s=s[:block.start()]+'```java\n'+(base/'src/labs/Usage.java').read_text()+'```'+s[block.end():]
 s=s.split('\n## 其他完整实现')[0]
 extra=[p for p in (base/'src/labs').glob('*.java') if p.name not in [Path(target['name']).name,'Usage.java']]
 if extra:s+='\n## 其他完整实现\n\n'+''.join('### '+p.name+'\n\n```java\n'+p.read_text()+'```\n\n' for p in sorted(extra))
 answer.write_text(s)
course=r/'course-info.yaml';d=yaml.safe_load(course.read_text())
extra=[p for p in r.rglob('*') if p.is_file() and not any(x in p.relative_to(r).parts for x in ['build','.gradle','__pycache__','mysql']) and p.name!='course-info.yaml']
d['additional_files']=[dict(name=str(p.relative_to(r)),**({'is_binary':True} if p.suffix=='.jar' else {})) for p in sorted(extra)]
course.write_text(yaml.safe_dump(d,allow_unicode=True,sort_keys=False))
print('已同步7题字符偏移、标准解和全部可见文件')
