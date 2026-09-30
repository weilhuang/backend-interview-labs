#!/usr/bin/env python3
"""从作者占位区生成完整、可读答案并存的普通学习者目录，不冒充Academy归档。"""
from pathlib import Path
import argparse,shutil,yaml
from verify import R,M,student,validate
p=argparse.ArgumentParser();p.add_argument('destination',type=Path);a=p.parse_args();dest=a.destination.resolve()
assert not dest.exists(),'目标必须是不存在的新目录'
assert not R.is_relative_to(dest),'不能覆盖课程父目录'
validate()
shutil.copytree(R,dest,ignore=shutil.ignore_patterns('build','authoring','.gradle','.idea','__pycache__'))
for item in M:
 task=dest/item['task'];config=yaml.safe_load((task/'task-info.yaml').read_text())
 for f in config['files']:
  if f.get('placeholders'):
   file=task/f['name'];file.write_text(student(file.read_text(),f['placeholders']))
print('已生成普通学习者目录：',dest)
print('这不是插件生成的课程归档；Academy预览、导入、重置仍须独立验收。')
