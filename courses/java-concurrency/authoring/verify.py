#!/usr/bin/env python3
"""真实JDK21/JUnit5作者门禁；静态YAML验证不冒充IDE导入。"""
from pathlib import Path
import argparse,hashlib,json,os,re,shutil,subprocess,sys
import yaml
ROOT=Path(__file__).resolve().parents[1]

def load(path):return yaml.safe_load(path.read_text(encoding='utf-8'))
def student(source,placeholders):
 data=source.encode('utf-16-le')
 for item in sorted(placeholders,key=lambda x:x['offset'],reverse=True):
  a,b=item['offset']*2,(item['offset']+item['length'])*2
  data=data[:a]+item['placeholder_text'].encode('utf-16-le')+data[b:]
 return data.decode('utf-16-le')
def validate():
 course=load(ROOT/'course-info.yaml');assert course['environment_settings']['jvm_language_level']=='JDK_21';assert course['language']=='Chinese'
 found=[]
 for section in course['content']:
  for lesson in load(ROOT/section/'section-info.yaml')['content']:
   for task in load(ROOT/section/lesson/'lesson-info.yaml')['content']:
    folder=ROOT/section/lesson/task;found.append(str(folder.relative_to(ROOT)))
    meta=load(folder/'task-info.yaml');assert meta['type']=='edu';count=0
    for file in meta['files']:
     path=folder/file['name'];assert path.is_file() and path.resolve().is_relative_to(folder.resolve());assert file['visible'] is True
     source=path.read_text();end=0
     for p in file.get('placeholders',[]):
      assert p['offset']>=end and p['length']>0;end=p['offset']+p['length'];assert end<=len(source.encode('utf-16-le'))//2;count+=1
     if file.get('placeholders'):assert 'TODO' in student(source,file['placeholders'])
    assert count>0
    doc=(folder/'task.md').read_text();assert '## 标准答案与逐步解析' in doc and '## 完整调用示例' in doc and '## 面试题递进与参考表达' in doc
 assert len(found)==8 and len(set(found))==8
 for file in course['additional_files']:assert (ROOT/file['name']).is_file(),file
 assert hashlib.sha256((ROOT/'gradle/wrapper/gradle-wrapper.jar').read_bytes()).hexdigest()=='a8451eeda314d0568b5340498b36edf147a8f0d692c5ff58082d477abe9146e4'
 return found

def main():
 parser=argparse.ArgumentParser();parser.add_argument('--junit-console',type=Path,required=True);parser.add_argument('--java-home',type=Path,default=Path(os.environ['JAVA_HOME']) if os.environ.get('JAVA_HOME') else None);parser.add_argument('--metadata-only',action='store_true');args=parser.parse_args()
 validate()
 if args.metadata_only:print('静态元数据通过；未运行IDE');return
 if args.java_home is None:parser.error('请用 --java-home 或 JAVA_HOME 指定完整 JDK21')
 jar=args.junit_console.resolve();assert hashlib.sha256(jar.read_bytes()).hexdigest()=='b016ef6b1c3454d6d7c2c88ce081dabf289699686af6622d6e4e2e1b54b4a2fc'
 javac=args.java_home/'bin/javac';java=args.java_home/'bin/java'
 version=subprocess.check_output([str(java),'-version'],stderr=subprocess.STDOUT,text=True);assert 'version "21' in version
 work=ROOT/'build/verification';shutil.rmtree(work,ignore_errors=True);work.mkdir(parents=True)
 report={'jdk':version.strip(),'release':21,'metadata':'PASS','gradle':'由独立命令另验','idea_academy':'NOT_RUN','tasks':[]}
 manifest=json.loads((ROOT/'authoring/manifest.json').read_text())
 def check(name,folder,source,expected):
  case=work/name;case.mkdir();classes=case/'classes';classes.mkdir();files=[]
  for p in list((folder/'src').rglob('*.java'))+list((folder/'test').rglob('*.java')):
   dest=case/p.relative_to(folder);dest.parent.mkdir(parents=True,exist_ok=True);dest.write_text(source if p==folder/item['source'] else p.read_text());files.append(str(dest))
  result=subprocess.run([str(javac),'--release','21','-encoding','UTF-8','-cp',str(jar),'-d',str(classes)]+files,text=True,capture_output=True,timeout=35)
  (case/'compile.log').write_text(result.stdout+result.stderr);assert result.returncode==0,f'{name}编译失败，见{case}/compile.log'
  result=subprocess.run([str(java),'-Xmx128m','-jar',str(jar),'execute','--class-path',str(classes),'--scan-class-path','--disable-banner','--disable-ansi-colors','--details','summary'],text=True,capture_output=True,timeout=35)
  output=result.stdout+result.stderr;(case/'junit.log').write_text(output)
  counts={key:int(re.search(r'\[\s*(\d+) tests '+key+r'\s*\]',output).group(1)) for key in ['found','successful','failed']}
  assert counts['found']>0
  assert (result.returncode==0 and counts['failed']==0) if expected else (result.returncode==1 and counts['failed']>0),f'{name}结果不符合预期，见{case}/junit.log'
  print(name,counts,flush=True);return counts,classes
 for item in manifest:
  folder=ROOT/item['task'];source=(folder/item['source']).read_text();record={'task':item['task']}
  record['reference'],classes=check(item['cls']+'-reference',folder,source,True)
  usage=subprocess.run([str(java),'-Xmx128m','-cp',str(classes),'labs.'+item['cls']+'Usage'],text=True,capture_output=True,timeout=12)
  assert usage.returncode==0,(item['cls'],usage.stderr);record['caller']={'status':'PASS','stdout':usage.stdout};(classes.parent/'usage.log').write_text(usage.stdout+usage.stderr)
  placeholders=next(file['placeholders'] for file in load(folder/'task-info.yaml')['files'] if file['name']==item['source'])
  record['learner_expected_fail'],_=check(item['cls']+'-learner',folder,student(source,placeholders),False)
  record['alternative'],_=check(item['cls']+'-alternative',folder,(folder/item['alternative']).read_text(),True)
  record['mutants']=[]
  for index,mutant_path in enumerate(item['mutation_files']):
   result,_=check(item['cls']+f'-mutant-{index}',folder,(ROOT/mutant_path).read_text(),False);record['mutants'].append(result)
  report['tasks'].append(record)
  (work/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
 report['status']='PASS';report['reference_tests']=sum(t['reference']['found'] for t in report['tasks']);report['mutants_killed']=sum(len(t['mutants']) for t in report['tasks']);report['learner_tasks_rejected']=len(manifest)
 (work/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n');print('验证完成',work/'report.json')
if __name__=='__main__':main()
