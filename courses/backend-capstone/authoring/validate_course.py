#!/usr/bin/env python3
"""核验元数据、可见性、UTF-16学习区、标准解与同源镜像；静态成功不等于插件验收。"""
from pathlib import Path
import json,re,hashlib,yaml
root=Path(__file__).resolve().parents[1]
course=yaml.safe_load((root/'course-info.yaml').read_text());assert course['environment_settings']['jvm_language_level']=='JDK_21'
registered={x['name'] for x in course['additional_files']};assert len(registered)==len(course['additional_files'])
for name in registered:assert (root/name).is_file(),name
count=0;tasks=0
for item in json.loads((root/'authoring/manifest.json').read_text()):
 task=root/'capstone/stages'/item['module'];meta=yaml.safe_load((task/'task-info.yaml').read_text());assert meta['type']=='edu';tasks+=1
 names={f['name'] for f in meta['files']}
 for p in task.rglob('*'):
  if not p.is_file() or 'build' in p.relative_to(task).parts:continue
  if p.name not in ('task.md','task-info.yaml'):assert p.relative_to(task).as_posix() in names,p
 text=(task/'task.md').read_text()
 assert text.count('```')%2==0
 for title in ('企业','标准答案','递进提示','面试递进','核心源码','完整项目'):assert title in text or title=='企业',title
 for f in meta['files']:
  assert f.get('visible',True),f
  p=task/f['name'];assert p.is_file(),p
  if 'placeholders' in f:
   source=p.read_text();raw=source.encode('utf-16-le');last=0
   assert source in text,'完整公开答案与源码不一致：'+str(p)
   assert source==(root/'reference/src/labs/capstone'/p.name).read_text(),'参考检查点漂移：'+str(p)
   for ph in f['placeholders']:
    begin,end=ph['offset']*2,(ph['offset']+ph['length'])*2
    assert 0<=last<=begin<end<=len(raw),ph
    assert 'Exercise.unimplemented()' in ph['placeholder_text'];assert '学习区结束' not in raw[begin:end].decode('utf-16-le');last=end;count+=1
for p in root.rglob('*'):
 if not p.is_file() or any(x in p.relative_to(root).parts for x in ('build','.gradle','__pycache__')):continue
 rel=p.relative_to(root).as_posix()
 if not rel.startswith('capstone/') and rel!='course-info.yaml':assert rel in registered,'未登记资产：'+rel
raw=(root/'shared/versions.env').read_bytes();sha=hashlib.sha256(raw).hexdigest();assert (root/'shared/versions.sha256').read_text().split()[0]==sha
source=root.parents[1]/'infra/versions.env'
if source.exists():assert source.read_bytes()==raw,'生成快照已过期，请运行prepare_export.py'
keys={line.split('=',1)[0] for line in raw.decode().splitlines() if line and not line.startswith('#')};assert len(keys)==7
compose=yaml.safe_load((root/'compose.yaml').read_text());assert all('${' in s['image'] for s in compose['services'].values())
assert '0.0.0.0:' not in (root/'compose.yaml').read_text()
report={'任务数':tasks,'学习区':count,'完整标准答案同步':True,'全部测试可见':True,'镜像快照SHA256':sha,'实际Academy导入':'未由静态检查证明'}
(root/'authoring/metadata-report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
print(json.dumps(report,ensure_ascii=False))
