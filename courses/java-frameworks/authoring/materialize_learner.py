#!/usr/bin/env python3
"""导出普通Gradle学生副本；不是插件原生归档，全部测试/调用方/标准解保留。"""
from pathlib import Path
import argparse,shutil,json,yaml
from validate_course import ROOT,student,validate
p=argparse.ArgumentParser();p.add_argument('destination',type=Path);a=p.parse_args();dest=a.destination.resolve()
if dest.exists():raise SystemExit('目标已存在，不覆盖已有练习')
validate();dest.mkdir(parents=True)
for name in ['README.md','中文阶段报告.md','build.gradle','settings.gradle','gradle.properties','gradlew','gradlew.bat','gradle','docs','scripts','THIRD_PARTY_NOTICES.md','LICENSE-JetBrains-template']:
 path=ROOT/name
 if path.is_dir():shutil.copytree(path,dest/name)
 else:shutil.copy2(path,dest/name)
for item in json.loads((ROOT/'authoring/manifest.json').read_text()):
 root=ROOT/item['path'];out=dest/item['path'];out.mkdir(parents=True)
 for name in ['task-info.yaml','task.md']:shutil.copy2(root/name,out/name)
 for file in yaml.safe_load((root/'task-info.yaml').read_text())['files']:
  content=(root/file['name']).read_text()
  if file.get('placeholders'):content=student(content,file['placeholders'])
  target=out/file['name'];target.parent.mkdir(parents=True,exist_ok=True);target.write_text(content)
(dest/'README.md').write_text('这是学生练习副本，保留待实现区域；每节标准解仍公开。这里是普通Gradle项目，不是Academy原生归档。教师参考实现的验收结果不代表你的未完成实现已通过。\n\n'+(dest/'README.md').read_text())
(dest/'学生副本说明.txt').write_text('本目录是普通Gradle练习副本，尚非Academy导出归档。所有测试、调用方与每节标准解公开；待实现区域会导致检查失败，按题目完成后重试。\n')
print(dest)
