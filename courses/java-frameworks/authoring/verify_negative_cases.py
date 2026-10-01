#!/usr/bin/env python3
"""用同一公开测试检验学生空实现与错误变体，编译失败不能冒充测试拒绝。"""
from pathlib import Path
import argparse,json,subprocess,os,re,yaml,hashlib
from validate_course import ROOT,student,validate,replace_fragment
p=argparse.ArgumentParser();p.add_argument('--console',type=Path,required=True);p.add_argument('--jdk',type=Path,required=True);a=p.parse_args()
assert hashlib.sha256(a.console.read_bytes()).hexdigest()=='329bd10288875a74d04c9ca6b7c9889c265ddf87b21a9ea42a7f7392f391472a', 'JUnit控制台版本或校验和不匹配'
validate();manifest=json.loads((ROOT/'authoring/manifest.json').read_text());output=ROOT/'build/negative-verification';output.mkdir(parents=True,exist_ok=True)
records=[]
for item in manifest:
 task=ROOT/item['path'];cp=(task/'build/verification-classpath.txt').read_text();config=yaml.safe_load((task/'task-info.yaml').read_text())
 sources={f['name']:(task/f['name']).read_text() for f in config['files'] if f['name'].startswith('src/') and f['name'].endswith('.java')}
 stub=dict(sources)
 for f in config['files']:
  if f.get('placeholders'):stub[f['name']]=student(sources[f['name']],f['placeholders'])
 cases=[('学生起点',stub)]
 for i,(old,new) in enumerate(item['mutations']):
  changed=dict(sources);changed['src/labs/frameworks/Lab.java']=replace_fragment(changed['src/labs/frameworks/Lab.java'],old,new);cases.append((f'错误变体{i+1}',changed))
 for label,files in cases:
  work=output/item['name']/label;classes=work/'classes';classes.mkdir(parents=True,exist_ok=True);paths=[]
  for rel,text in files.items():
   dest=work/rel;dest.parent.mkdir(parents=True,exist_ok=True);dest.write_text(text);paths.append(str(dest))
  compiled=subprocess.run([str(a.jdk/'bin/javac'),'--release','21','-parameters','-encoding','UTF-8','-cp',cp,'-d',str(classes)]+paths,capture_output=True,text=True,timeout=60)
  (work/'compile.log').write_text(compiled.stdout+compiled.stderr)
  if compiled.returncode:raise RuntimeError(f'{item["name"]}/{label}编译失败，不能算已被正确性测试拒绝：{work}')
  ran=subprocess.run([str(a.jdk/'bin/java'),'-Dserver.address=127.0.0.1','-jar',str(a.console.resolve()),'execute','--class-path',str(classes)+os.pathsep+cp,'--select-class','labs.frameworks.LabTest','--exclude-tag','docker','--disable-banner','--disable-ansi-colors','--details','summary'],capture_output=True,text=True,timeout=90)
  log=ran.stdout+ran.stderr;(work/'junit.log').write_text(log)
  match=re.search(r'\[\s*(\d+) tests failed\s*\]',log)
  if ran.returncode!=1 or not match or int(match.group(1))<1:raise RuntimeError(f'{item["name"]}/{label}未被正常断言拒绝或引擎错误：{work}')
  record={'task':item['name'],'case':label,'compiled':True,'failed_tests':int(match.group(1)),'status':'rejected'};records.append(record);print(record,flush=True)
report={'status':'passed','jdk':str(a.jdk),'compiler':'--release 21 -parameters','cases':records,'note':'只验证本课程公开测试的已知负例，不能证明不存在其他缺陷'}
(ROOT/'authoring/negative-report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n');print('所有已声明负例均被拒绝',len(records),flush=True)
