#!/usr/bin/env python3
"""src是标准实现单一来源：同步可见答案、正文代码和UTF-16占位区。"""
from pathlib import Path
import json,re,yaml
R=Path(__file__).resolve().parents[1]
for item in json.loads((R/'authoring/manifest.json').read_text()):
 task=R/item['task'];s=(task/item['source']).read_text();(task/f'solutions/{item["class"]}.java.txt').write_text(s)
 text=(task/'task.md').read_text();marker='## 标准解与逐步解释';before,after=text.split(marker,1)
 after=re.sub(r'```java\n.*?\n```',lambda _: '```java\n'+s.strip()+'\n```',after,count=1,flags=re.S);(task/'task.md').write_text(before+marker+after)
 cfg=yaml.safe_load((task/'task-info.yaml').read_text())
 for f in cfg['files']:
  if f['name']!=item['source']:continue
  ph=[];start=0
  while True:
   a=s.find('        // 作答开始\n',start)
   if a<0:break
   a+=len('        // 作答开始\n');b=s.index('        // 作答结束',a)
   ph.append({'offset':len(s[:a].encode('utf-16-le'))//2,'length':len(s[a:b].encode('utf-16-le'))//2,'placeholder_text':'        throw new UnsupportedOperationException("TODO：请按合同完成实现");\n'});start=b+1
  f['placeholders']=ph
 (task/'task-info.yaml').write_text(yaml.safe_dump(cfg,allow_unicode=True,sort_keys=False))
 usage=(task/f'src/labs/jvm/{item["class"]}Usage.java').read_text()
 doc=(task/'task.md').read_text();head,tail=doc.split('## 完整调用示例',1)
 tail=re.sub(r'```java\n.*?\n```',lambda _: '```java\n'+usage.strip()+'\n```',tail,count=1,flags=re.S)
 (task/'task.md').write_text(head+'## 完整调用示例'+tail)

print('已同步7题标准解、正文与占位区')
