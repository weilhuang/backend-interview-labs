#!/usr/bin/env python3
"""创建普通Gradle学员工作副本；不是Academy可导入归档。"""
from pathlib import Path
import argparse, shutil
from validate_course import ROOT, read_yaml, student_source, validate
p=argparse.ArgumentParser()
p.add_argument('destination',type=Path)
a=p.parse_args(); dest=a.destination.resolve()
if dest.exists():raise SystemExit('目标目录必须不存在；不会覆盖已有文件')
if dest.is_relative_to(ROOT):raise SystemExit('请选择作者课程根之外的目标目录')
validate();dest.mkdir(parents=True)
for name in ['README.md','阶段报告.md','build.gradle','settings.gradle','gradle.properties','gradlew','gradlew.bat','gradle','THIRD_PARTY_NOTICES.md','LICENSE-JetBrains-template']:
    source=ROOT/name
    if source.is_dir():shutil.copytree(source,dest/name)
    else:shutil.copy2(source,dest/name)
for meta in (ROOT/'java-pilot').rglob('task-info.yaml'):
    task=meta.parent; relative=task.relative_to(ROOT); target=dest/relative;target.mkdir(parents=True)
    config=read_yaml(meta)
    # settings.gradle通过task-info.yaml发现模块；此副本不伪装成Academy课程根。
    shutil.copy2(meta,target/'task-info.yaml');shutil.copy2(task/'task.md',target/'task.md')
    for file in config['files']:
        source=(task/file['name']).read_text(encoding='utf-8')
        if 'placeholders' in file:source=student_source(source,file['placeholders'])
        out=target/file['name'];out.parent.mkdir(parents=True,exist_ok=True);out.write_text(source,encoding='utf-8')
(dest/'LEARNER-COPY.txt').write_text('普通Gradle练习副本：实现区保留TODO，题面包含公开标准答案、解析、完整调用端和全部测试。这不是Academy归档。请按Gradle工程打开；尚未完成实现时测试失败是预期行为。\n')
print(dest)
