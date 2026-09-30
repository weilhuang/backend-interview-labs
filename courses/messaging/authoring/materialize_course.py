#!/usr/bin/env python3
"""生成独立课程项目目录与学习起点；它不是官方Academy导出归档。"""
from pathlib import Path
import argparse, hashlib, json, shutil
import yaml
ROOT = Path(__file__).resolve().parents[1]
p=argparse.ArgumentParser()
p.add_argument('--course', choices=['kafka','rocketmq'], required=True)
p.add_argument('--output', type=Path, required=True)
p.add_argument('--learner', action='store_true')
a=p.parse_args(); dest=a.output.resolve()
if dest.exists(): raise SystemExit('目标目录已存在，请换一个空目录，避免覆盖学习内容')
if ROOT == dest or ROOT.is_relative_to(dest): raise SystemExit('不能覆盖源课程目录')
shutil.copytree(ROOT,dest,ignore=shutil.ignore_patterns('build','.gradle','*.log','__pycache__'))
other='rocketmq' if a.course=='kafka' else 'kafka'; shutil.rmtree(dest/other)
course=yaml.safe_load((dest/'course-info.yaml').read_text())
course['content']=[a.course];course['title']='后端面试实验室：'+('Kafka消息可靠性' if a.course=='kafka' else 'RocketMQ消息与事务消息')
# 打包快照只从共享真源复制，不独立维护镜像tag。
source=ROOT.parents[1]/'infra/versions.env'; target=dest/'shared/versions.env';target.parent.mkdir();shutil.copy2(source,target)
provenance={'来源':'仓库唯一真源infra/versions.env','SHA256':hashlib.sha256(source.read_bytes()).hexdigest(),'说明':'生成快照；更换版本须在原仓库台账修改后重新生成'}
(dest/'shared/source-manifest.json').write_text(json.dumps(provenance,ensure_ascii=False,indent=2)+'\n')
course['additional_files'] += [{'name':'shared/versions.env'},{'name':'shared/source-manifest.json'}]
(dest/'course-info.yaml').write_text(yaml.safe_dump(course,allow_unicode=True,sort_keys=False))
manifest=json.loads((dest/'authoring/manifest.json').read_text())
manifest=[item for item in manifest if item['task'].startswith(a.course+'/')]
(dest/'authoring/manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n')
lessons=json.loads((dest/'authoring/lessons.json').read_text())
(dest/'authoring/lessons.json').write_text(json.dumps({k:v for k,v in lessons.items() if k.startswith(a.course+'/')},ensure_ascii=False,indent=2)+'\n')
if a.learner:
    for item in manifest:
        task=dest/item['task'];config=yaml.safe_load((task/'task-info.yaml').read_text())
        for file in config['files']:
            path=task/file['name'];raw=path.read_text().encode('utf-16-le')
            for hole in sorted(file.get('placeholders',[]),key=lambda x:x['offset'],reverse=True):
                begin=hole['offset']*2;end=begin+hole['length']*2
                raw=raw[:begin]+hole['placeholder_text'].encode('utf-16-le')+raw[end:]
            path.write_text(raw.decode('utf-16-le'))
intro='# 独立课程项目\n\n本目录只含'+course['title']+'，共享镜像快照来源与摘要见shared/source-manifest.json。它是源码项目，不是声称已通过官方Academy导出/导入的课程归档。\n\n'
readme=dest/'README.md';readme.write_text(intro+readme.read_text())
print('已生成独立项目：',dest)
