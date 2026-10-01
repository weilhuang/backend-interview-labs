#!/usr/bin/env python3
"""在全新目录生成可检查的学员起点，不覆盖现有目录。"""
from pathlib import Path
import sys, shutil, yaml
root=Path(__file__).resolve().parents[1];dest=Path(sys.argv[1]).resolve()
if dest.exists():raise SystemExit('目标已存在；请选择新的学员副本目录')
shutil.copytree(root,dest,ignore=shutil.ignore_patterns('build','.gradle','__pycache__'))
for info in (dest/'mysql').glob('*/*/task-info.yaml'):
    for item in yaml.safe_load(info.read_text())['files']:
        if 'placeholders' not in item:continue
        path=info.parent/item['name'];text=path.read_text()
        for p in sorted(item['placeholders'],key=lambda p:p['offset'],reverse=True):
            text=text[:p['offset']]+p['placeholder_text']+text[p['offset']+p['length']:]
        path.write_text(text)
print('学员副本已生成；answer.md与全部测试仍然公开：'+str(dest))
