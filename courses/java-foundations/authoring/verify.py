#!/usr/bin/env python3
"""离线作者验证：完整JDK默认；显式受限模式不宣称release兼容或IDE通过。"""
from pathlib import Path
import argparse,json,re,subprocess,shutil,hashlib,os,sys
import yaml
R=Path(__file__).resolve().parents[1]
M=json.loads((R/'authoring/manifest.json').read_text())
def student(source,ph):
 raw=source.encode('utf-16-le')
 for p in sorted(ph,key=lambda x:x['offset'],reverse=True):raw=raw[:p['offset']*2]+p['placeholder_text'].encode('utf-16-le')+raw[(p['offset']+p['length'])*2:]
 return raw.decode('utf-16-le')
def validate():
 tasks=[]
 c=yaml.safe_load((R/'course-info.yaml').read_text());assert c['environment_settings']['jvm_language_level']=='JDK_21'
 for item in M:
  d=R/item['task'];config=yaml.safe_load((d/'task-info.yaml').read_text());tasks.append(item['task'])
  paths=[f['name'] for f in config['files']];assert len(paths)==len(set(paths))
  for f in config['files']:
   p=(d/f['name']).resolve();assert p.is_relative_to(d.resolve()) and p.is_file() and f['visible']
   if 'placeholders' in f:
    s=p.read_text();assert len(f['placeholders'])==item['placeholders']
    assert 'TODO' in student(s,f['placeholders'])
    assert s.strip() in (d/'task.md').read_text(), '正文标准解与源码不一致'
  assert (d/f'solutions/{item["class"]}.java.txt').read_text()==(d/item['source']).read_text()
  doc=(d/'task.md').read_text();assert all(h in doc for h in ['## 完整调用示例','## 标准解与逐步解释','## 面试问答与迁移','## 源码与证据','```text'])
  for src in d.rglob('*.java'):
   if 'build' not in src.relative_to(d).parts:assert str(src.relative_to(d)) in paths
 assert len(tasks)==16
 assert hashlib.sha256((R/'gradle/wrapper/gradle-wrapper.jar').read_bytes()).hexdigest()=='a8451eeda314d0568b5340498b36edf147a8f0d692c5ff58082d477abe9146e4'
 for f in c['additional_files']:assert (R/f['name']).is_file()
 return {'tasks':len(tasks),'placeholders':sum(x['placeholders'] for x in M),'status':'PASS'}
def main():
 p=argparse.ArgumentParser();p.add_argument('--junit-console',type=Path,required=True);p.add_argument('--limited-compiler-module',action='store_true');args=p.parse_args()
 jar=args.junit_console.resolve();assert hashlib.sha256(jar.read_bytes()).hexdigest()=='b016ef6b1c3454d6d7c2c88ce081dabf289699686af6622d6e4e2e1b54b4a2fc'
 home=os.getenv('JAVA_HOME');java=str(Path(home)/'bin/java') if home else 'java';javac=str(Path(home)/'bin/javac') if home else 'javac'
 compiler=[java,'com.sun.tools.javac.Main'] if args.limited_compiler_module else [javac]
 flags=['-source','21','-target','21'] if args.limited_compiler_module else ['--release','21']
 report={'static':validate(),'environment':subprocess.run([java,'-version'],text=True,capture_output=True).stderr,'compiler':compiler+flags,'release_api_verified':not args.limited_compiler_module,'gradle':'NOT_RUN','IDEA_Academy':'NOT_RUN','JMH':'NOT_RUN','cases':[]}
 work=R/'build/verification';work.mkdir(parents=True,exist_ok=True)
 def run_case(item,label,source,pass_expected):
  d=R/item['task'];out=work/(item['class']+'-'+label)
  if out.exists():shutil.rmtree(out)
  classes=out/'classes';classes.mkdir(parents=True);src=out/'src';src.mkdir()
  files=[]
  for f in list((d/'src').rglob('*.java'))+list((d/'test').rglob('*.java'))+list((R/'common/src').rglob('*.java')):
   target=src/f.name;target.write_text(source if f==d/item['source'] else f.read_text());files.append(str(target))
  command=compiler+flags+['-encoding','UTF-8','-cp',str(jar),'-d',str(classes)]+files
  c=subprocess.run(command,text=True,capture_output=True,timeout=45);(out/'compile.log').write_text(c.stdout+c.stderr)
  assert c.returncode==0,f'{item["class"]} {label} 编译失败 {out}'
  t=subprocess.run([java,'-Xmx192m','-XX:ActiveProcessorCount=2','-jar',str(jar),'execute','--class-path',str(classes),'--scan-class-path','--disable-banner','--disable-ansi-colors','--details','summary'],text=True,capture_output=True,timeout=30)
  output=t.stdout+t.stderr;(out/'junit.log').write_text(output)
  counts={k:int(re.search(r'\[\s*(\d+) tests '+k+r'\s*\]',output).group(1)) for k in ['found','successful','failed']}
  assert counts['found']>0
  assert (t.returncode==0 and counts['failed']==0) if pass_expected else (t.returncode==1 and counts['failed']>0),f'{item["class"]} {label} 结果不符合预期：{out}'
  record={'task':item['id'],'case':label,**counts,'status':'PASS' if pass_expected else 'EXPECTED_FAIL'}
  if label=='reference':
   u=subprocess.run([java,'-Xmx96m','-cp',str(classes),'labs.foundation.'+item['class']+'Usage'],text=True,capture_output=True,timeout=15);(out/'usage.log').write_text(u.stdout+u.stderr);assert u.returncode==0;record['caller_stdout']=u.stdout
  report['cases'].append(record);print(item['id'],label,counts,flush=True)
 for item in M:
  d=R/item['task'];source=(d/item['source']).read_text();config=yaml.safe_load((d/'task-info.yaml').read_text());ph=next(f['placeholders'] for f in config['files'] if f['name']==item['source'])
  run_case(item,'reference',source,True);run_case(item,'student',student(source,ph),False)
  run_case(item,'alternative',(R/item['alternative']).read_text(),True)
  for i,(old,new) in enumerate(item['mutations']):
   assert source.count(old)==1,(item['id'],old,source.count(old));run_case(item,f'mutant-{i}',source.replace(old,new),False)
 report['status']='PASS_LIMITED_COMPILER' if args.limited_compiler_module else 'PASS'
 (work/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
 print('报告：',work/'report.json')
if __name__=='__main__':main()
