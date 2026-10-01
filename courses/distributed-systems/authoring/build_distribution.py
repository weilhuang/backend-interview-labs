#!/usr/bin/env python3
"""制作可审查源码分发包和共享台账快照，不冒充Academy GUI导出。"""
from pathlib import Path
import shutil,yaml,json,hashlib,zipfile
R=Path(__file__).resolve().parents[1];out=R/'build/standalone-course'
if out.exists():shutil.rmtree(out)
out.mkdir(parents=True)
metadata=yaml.safe_load((R/'course-info.yaml').read_text())
for item in metadata['additional_files']:
 source=R/item['name'];target=out/item['name'];target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(source,target)
shutil.copytree(R/'distributed-course',out/'distributed-course',ignore=shutil.ignore_patterns('build'))
versions=R/'../../infra/versions.env'
if not versions.exists():versions=R/'shared/versions.env'
if not versions.is_file():raise SystemExit('找不到共享台账，拒绝制作缺少服务版本的包')
(out/'shared').mkdir(exist_ok=True);shutil.copy2(versions,out/'shared/versions.env')
metadata['additional_files'].append({'name':'shared/versions.env'})
(out/'course-info.yaml').write_text(yaml.safe_dump(metadata,allow_unicode=True,sort_keys=False))
manifest={'version':'0.2.0','kind':'公开源码分发，非Academy GUI导出','shared_versions_sha256':hashlib.sha256(versions.read_bytes()).hexdigest(),'files':{}}
for p in sorted(out.rglob('*')):
 if p.is_file():manifest['files'][str(p.relative_to(out))]=hashlib.sha256(p.read_bytes()).hexdigest()
(R/'authoring/distribution-report.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n')
archive=R/'build/distributed-systems-source-0.2.0.zip'
with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED) as z:
 for p in sorted(out.rglob('*')):
  if p.is_file():z.write(p,p.relative_to(out))
print('源码分发包已生成：',archive,'文件数：',len(manifest['files']))
