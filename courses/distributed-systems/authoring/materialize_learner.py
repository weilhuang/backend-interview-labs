#!/usr/bin/env python3
"""按真实UTF-16占位生成独立学习者工程，不覆盖公开标准解。"""
from pathlib import Path
import sys,shutil,json,yaml
R=Path(__file__).resolve().parents[1]
target=Path(sys.argv[1]).resolve() if len(sys.argv)>1 else R/'build/learner'
if target.exists():raise SystemExit('目标已存在，避免覆盖学习者修改，请使用新目录')
shutil.copytree(R,target,ignore=shutil.ignore_patterns('build','.gradle','*.log','__pycache__'))
count=0
for task in json.loads((target/'authoring/manifest.json').read_text()):
 base=target/task['path']
 for entry in yaml.safe_load((base/'task-info.yaml').read_text())['files']:
  if not entry.get('placeholders'):continue
  file=base/entry['name'];data=file.read_text().encode('utf-16-le')
  for holder in sorted(entry['placeholders'],key=lambda p:p['offset'],reverse=True):
   start=holder['offset']*2;end=start+holder['length']*2
   data=data[:start]+holder['placeholder_text'].encode('utf-16-le')+data[end:];count+=1
  file.write_text(data.decode('utf-16-le'))
print('已生成学习者工程，编码区数量：',count,'目标：',target)
