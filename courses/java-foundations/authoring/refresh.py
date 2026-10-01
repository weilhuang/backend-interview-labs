#!/usr/bin/env python3
"""作者src为单一真源，同步标准解、页面代码、占位与可见文件。"""
from pathlib import Path
import json,re,yaml
R=Path(__file__).resolve().parents[1]
M=json.loads((R/'authoring/manifest.json').read_text())
for item in M:
 task=R/item['task'];source=(task/item['source']).read_text();ph=[];start=0
 while True:
  match=re.search(r'(?m)^([ \t]*)// 作答开始\n',source[start:])
  if not match:break
  a=start+match.end();b=source.index('// 作答结束',a);b=source.rfind('\n',a,b)+1
  ph.append({'offset':len(source[:a].encode('utf-16-le'))//2,'length':len(source[a:b].encode('utf-16-le'))//2,'placeholder_text':match.group(1)+'throw new UnsupportedOperationException("TODO：按公开合同完成实现");\n'})
  start=source.index('// 作答结束',a)+len('// 作答结束')
 if item['class']=='DebugRepairs':
  pattern=r'(?m)^([ \t]*)// 作答开始\n(.*?)^[ \t]*// 作答结束'
  for index,(old,new) in enumerate(item['mutations']):
   variant=source.replace(old,new)
   region=list(re.finditer(pattern,variant,re.S))[index]
   ph[index]['placeholder_text']=region.group(1)+'// TODO：定位并修复这个独立缺陷\n'+region.group(2)
   bug=task/'bugs'/['01-boundary','02-alias','03-suppressed'][index]/'DebugRepairs.java.txt'
   bug.parent.mkdir(parents=True,exist_ok=True);bug.write_text(variant)
 item['placeholders']=len(ph);(task/f'solutions/{item["class"]}.java.txt').write_text(source)
 files=[]
 for path in sorted(task.rglob('*')):
  if not path.is_file() or 'build' in path.relative_to(task).parts or path.name in ['task-info.yaml','task.md']:continue
  file={'name':str(path.relative_to(task)),'visible':True}
  if file['name']==item['source']:file['placeholders']=ph
  files.append(file)
 (task/'task-info.yaml').write_text(yaml.safe_dump({'type':'edu','custom_name':item['title'],'files':files},allow_unicode=True,sort_keys=False))
 p=task/'task.md'
 if p.exists():
  text=p.read_text();head,tail=text.split('## 标准解与逐步解释',1)
  tail=re.sub(r'```java\n.*?\n```',lambda _:'```java\n'+source.strip()+'\n```',tail,count=1,flags=re.S)
  text=head+'## 标准解与逐步解释'+tail;head,tail=text.split('## 完整调用示例',1)
  usage=(task/f'src/labs/foundation/{item["class"]}Usage.java').read_text();tail=re.sub(r'```java\n.*?\n```',lambda _:'```java\n'+usage.strip()+'\n```',tail,count=1,flags=re.S)
  p.write_text(head+'## 完整调用示例'+tail)
(R/'authoring/manifest.json').write_text(json.dumps(M,ensure_ascii=False,indent=2)+'\n')
