#!/usr/bin/env python3
"""框架课程专用结构检查：全部项目文件可见、UTF-16占位与标准解齐备。"""
from pathlib import Path
import json,re,yaml
ROOT=Path(__file__).resolve().parents[1]
def student(content,places):
 data=content.encode('utf-16-le')
 for p in sorted(places,key=lambda x:x['offset'],reverse=True):
  start=p['offset']*2;end=start+p['length']*2
  data=data[:start]+p['placeholder_text'].encode('utf-16-le')+data[end:]
 return data.decode('utf-16-le')
def replace_fragment(source,old,new):
 positions=[i for i,c in enumerate(source) if not c.isspace()]
 compact=''.join(source[i] for i in positions);needle=''.join(c for c in old if not c.isspace())
 assert compact.count(needle)==1,('变体片段必须唯一',old)
 start=compact.index(needle);return source[:positions[start]]+new+source[positions[start+len(needle)-1]+1:]
def validate():
 manifest=json.loads((ROOT/'authoring/manifest.json').read_text());count=0
 for task in manifest:
  root=ROOT/task['path'];meta=yaml.safe_load((root/'task-info.yaml').read_text());listed=set()
  for f in meta['files']:
   assert f.get('visible') is True,(task['name'],f['name'],'文件不可见')
   p=(root/f['name']).resolve();assert p.is_relative_to(root.resolve()) and p.is_file(),p
   listed.add(f['name']);text=p.read_text();last=-1
   for holder in f.get('placeholders',[]):
    a=holder['offset'];b=a+holder['length'];assert a>=last and b<=len(text.encode('utf-16-le'))//2,(p,holder)
    body=text.encode('utf-16-le')[a*2:b*2].decode('utf-16-le');assert body.strip(),p
    last=b;count+=1
   if f.get('placeholders'):student(text,f['placeholders'])
  actual={str(p.relative_to(root)) for p in root.rglob('*') if p.is_file() and p.name not in ['task-info.yaml','task.md'] and 'build' not in p.relative_to(root).parts}
  assert actual==listed,(task['name'],actual-listed,listed-actual)
  assert any(x.startswith('test/') for x in listed),task['name']
  assert 'src/labs/frameworks/Usage.java' in listed,task['name']
  md=(root/'task.md').read_text()
  for heading in ['## 企业场景','## 实际操作与逐步编码','## 正确性合同','## 固定版本源码阅读','## 公开标准解','## 面试机制 边界与取舍']:
   assert heading in md,(task['name'],heading)
  assert md.count('```')%2==0,task['name']
  assert '```mermaid' not in md,task['name']
  code=(root/'src/labs/frameworks/Lab.java').read_text()
  for old,new in task['mutations']:replace_fragment(code,old,new)
 result={'tasks':len(manifest),'placeholders':count,'all_files_visible':True,'metadata':'passed','idea_academy':'未执行，静态有效不等于插件验收'}
 (ROOT/'authoring/metadata-report.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
 return result
if __name__=='__main__':print(validate())
