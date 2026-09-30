#!/usr/bin/env python3
"""检查全部公开文件、UTF-16编码区、标准解同步、目录覆盖与固定源码。"""
from pathlib import Path
import json,re,yaml
R=Path(__file__).resolve().parents[1]
def validate():
 tasks=json.loads((R/'authoring/manifest.json').read_text());holders=0;files=0
 assert len(tasks)==8 and {t['unit'] for t in tasks}=={f'C10-{i:02}' for i in range(1,9)}
 for task in tasks:
  root=R/task['path'];meta=yaml.safe_load((root/'task-info.yaml').read_text());listed=set()
  for entry in meta['files']:
   assert entry['visible'] is True,(task['name'],entry['name'])
   file=root/entry['name'];assert file.is_file(),file;listed.add(entry['name']);files+=1
   data=file.read_text().encode('utf-16-le');last=0
   for holder in entry.get('placeholders',[]):
    start=holder['offset']*2;end=start+holder['length']*2
    assert start>=last and end<=len(data) and data[start:end].decode('utf-16-le').strip()
    assert entry['name'].startswith('src/');holders+=1;last=end
  actual={str(p.relative_to(root)) for p in root.rglob('*') if p.is_file() and 'build' not in p.relative_to(root).parts and p.name not in ['task-info.yaml','task.md']}
  assert listed==actual,(task['name'],actual-listed,listed-actual)
  assert 'src/labs/distributed/Usage.java' in listed
  assert any(p.startswith('test/') for p in listed)
  for answer in (root/'solutions').rglob('*.java'):
   original=root/'src'/answer.relative_to(root/'solutions');assert original.read_bytes()==answer.read_bytes(),answer
  md=(root/'task.md').read_text()
  for heading in ['企业场景','概念逐层建立','实际操作与逐步编码','正确性合同与保证边界','固定版本源码阅读','公开完整标准解','面试机制、边界与深入追问']:
   assert '## '+heading in md,(task['name'],heading)
  assert md.count('```')%2==0
  assert '```text' in md
  assert '/blob/main/' not in md and '/blob/master/' not in md
 sources=json.loads((R/'authoring/source-verification.json').read_text())
 assert all(x['status']=='verified' for x in sources),sources
 assert all(re.fullmatch('[a-f0-9]{40}',x['commit']) for x in sources)
 course=yaml.safe_load((R/'course-info.yaml').read_text())
 for item in course['additional_files']:assert (R/item['name']).is_file(),item
 for java in (R/'distributed-course').rglob('*.java'):
  if 'build' in java.parts:continue
  text=java.read_text();assert not re.search(r'(?:mysql|redis|apache/kafka):\d',text),java
 result={'units':len(tasks),'files_visible':files,'coding_regions':holders,'source_files_verified':sum(len(x['files']) for x in sources),'status':'通过','academy_gui':'未执行，静态检查不代替GUI'}
 (R/'authoring/metadata-report.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
 print(json.dumps(result,ensure_ascii=False))
if __name__=='__main__':validate()
