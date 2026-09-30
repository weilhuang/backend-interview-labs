#!/usr/bin/env python3
"""导出普通Gradle学员副本；不是Academy插件归档。"""
from pathlib import Path
import argparse,shutil
from verify import ROOT,load,student,validate
p=argparse.ArgumentParser();p.add_argument('destination',type=Path);a=p.parse_args();dest=a.destination.resolve()
if dest.exists():raise SystemExit('目的地必须尚不存在，不能覆盖已有学习内容')
if dest.is_relative_to(ROOT) and not dest.is_relative_to(ROOT/'build'):raise SystemExit('课程根内只允许build目录作为临时导出目的地')
validate()
shutil.copytree(ROOT,dest,ignore=shutil.ignore_patterns('build','.gradle','.idea','authoring','__pycache__'))
for meta in dest.glob('juc/*/lab/task-info.yaml'):
 for file in load(meta)['files']:
  if file.get('placeholders'):
   path=meta.parent/file['name'];path.write_text(student(path.read_text(),file['placeholders']))
(dest/'course-info.yaml').unlink()
(dest/'学员副本说明.txt').write_text('这是普通Gradle练习副本，不是Academy归档。占位区初始可编译但测试失败；每节完整标准解仍在task.md。\n')
print(dest)
