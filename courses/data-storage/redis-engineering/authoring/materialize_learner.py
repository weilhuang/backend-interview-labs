#!/usr/bin/env python3
"""生成带真实占位符的普通Gradle练习副本，不等同于Academy导出包。"""
from pathlib import Path
import argparse,shutil,yaml
ROOT=Path(__file__).resolve().parents[1]
p=argparse.ArgumentParser();p.add_argument('destination',type=Path);args=p.parse_args();dest=args.destination.resolve()
if dest.exists():raise SystemExit('目标必须不存在，不覆盖学习者文件')
dest.mkdir(parents=True)
for name in ['README.md','阶段报告.md','SOURCES.md','THIRD_PARTY_NOTICES.md','LICENSE-JetBrains-template','build.gradle','settings.gradle','gradle.properties','gradlew','gradlew.bat','gradle','support','redis']:
    source=ROOT/name
    if source.is_dir():shutil.copytree(source,dest/name,ignore=shutil.ignore_patterns('build','__pycache__'))
    else:shutil.copy2(source,dest/name)
for meta in (dest/'redis').glob('*/task-info.yaml'):
    data=yaml.safe_load(meta.read_text())
    for item in data['files']:
        path=meta.parent/item['name'];text=path.read_text()
        for place in sorted(item.get('placeholders',[]),key=lambda x:x['offset'],reverse=True):
            start=place['offset'];text=text[:start]+place['placeholder_text']+text[start+place['length']:]
        path.write_text(text)
(dest/'LEARNER-COPY.txt').write_text('这是普通Gradle练习副本；公开标准解保留在solution.md。不是已验证的Academy导出归档。独立副本使用LAB_VERSIONS指向原仓库infra/versions.env。\n')
print(dest)
