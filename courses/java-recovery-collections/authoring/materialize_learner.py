#!/usr/bin/env python3
"""Create a plain Gradle student working copy; NOT an Academy import archive."""
from pathlib import Path
import argparse, shutil
from validate_course import ROOT, read_yaml, student_source, validate
p=argparse.ArgumentParser()
p.add_argument('destination',type=Path)
a=p.parse_args(); dest=a.destination.resolve()
if dest.exists():raise SystemExit('Destination must not exist; no files are overwritten')
if dest.is_relative_to(ROOT):raise SystemExit('Choose a destination outside the author course root')
validate();dest.mkdir(parents=True)
for name in ['build.gradle','settings.gradle','gradle.properties','gradlew','gradlew.bat','gradle','THIRD_PARTY_NOTICES.md','LICENSE-JetBrains-template']:
    source=ROOT/name
    if source.is_dir():shutil.copytree(source,dest/name)
    else:shutil.copy2(source,dest/name)
for meta in (ROOT/'java-pilot').rglob('task-info.yaml'):
    task=meta.parent; relative=task.relative_to(ROOT); target=dest/relative;target.mkdir(parents=True)
    config=read_yaml(meta)
    # settings.gradle discovers task-info.yaml, but this is deliberately not an Academy course root.
    shutil.copy2(meta,target/'task-info.yaml');shutil.copy2(task/'task.md',target/'task.md')
    for file in config['files']:
        source=(task/file['name']).read_text(encoding='utf-8')
        if 'placeholders' in file:source=student_source(source,file['placeholders'])
        out=target/file['name'];out.parent.mkdir(parents=True,exist_ok=True);out.write_text(source,encoding='utf-8')
(dest/'LEARNER-COPY.txt').write_text('Plain Gradle exercise copy. No reference answers. Not an Academy archive or importable Academy course. Open as a Gradle project; test failures are expected until tasks are solved.\n')
print(dest)
