#!/usr/bin/env python3
"""Fresh, scoped compilation and business-test evidence; never infer compilation from old XML."""
from pathlib import Path
import argparse,fnmatch,hashlib,json,os,re,shutil,subprocess,tempfile,time,xml.etree.ElementTree as ET
R=Path(__file__).resolve().parents[1]
ASSERTION_TYPES={'org.opentest4j.AssertionFailedError','org.opentest4j.MultipleFailuresError','java.lang.AssertionError'}
def require(ok,message):
 if not ok:raise ValueError(message)
def inventory(path):
 cases=set()
 for p in path.rglob('*.java'):
  s=p.read_text();package=re.search(r'package\s+([\w.]+)\s*;',s)
  if not package:continue
  for method in re.findall(r'@Test\s+void\s+(\w+)\s*\(',s):cases.add(package.group(1)+'.'+p.stem+'#'+method)
 return cases
def source_hash(path):
 h=hashlib.sha256()
 for p in sorted(path.rglob('*.java')):h.update(str(p.relative_to(path)).encode()+b'\0'+p.read_bytes()+b'\0')
 return h.hexdigest()
def read_results(build,expected,allowed_failures,is_starter):
 xmls=list((build/'test-results/test').glob('TEST-*.xml'))
 require(bool(xmls),'本次独立build目录没有JUnit XML')
 seen=set();failures=[];skipped=0
 for p in xmls:
  suite=ET.parse(p).getroot();cases=suite.findall('testcase')
  require(int(suite.attrib['tests'])==len(cases),'XML tests计数与实际testcase不一致')
  for c in cases:
   name=c.attrib.get('name','').removesuffix('()');key=c.attrib.get('classname','')+'#'+name
   require(key in expected,'未知/框架初始化失败testcase: '+key)
   require(key not in seen,'重复testcase: '+key);seen.add(key)
   skipped+=c.find('skipped') is not None
   fail=c.find('failure');error=c.find('error')
   require(error is None,'测试框架或执行error，不归因为业务断言')
   if fail is not None:
    kind=fail.attrib.get('type','');require(key in allowed_failures,'失败方法不在本变体预期业务失败清单: '+key)
    require(kind in ASSERTION_TYPES or (is_starter and kind=='java.lang.UnsupportedOperationException'),'失败类型不是业务断言/声明的未完成starter: '+kind)
    failures.append({'case':key,'type':kind,'message':fail.attrib.get('message','')})
  require(int(suite.attrib.get('failures',0))==sum(c.find('failure') is not None for c in cases),'XML failure计数不一致')
  require(int(suite.attrib.get('errors',0))==0,'XML errors非零')
  require(int(suite.attrib.get('skipped',0))==sum(c.find('skipped') is not None for c in cases),'XML skipped计数不一致')
 require(seen==expected,'本次测试集合不完整: '+str(sorted(expected-seen)))
 require(skipped==0,'不允许跳过测试')
 require({f['case'] for f in failures}==allowed_failures,'本次失败集合必须与声明的业务失败集合完全相同，缺失/额外失败均拒绝')
 return len(seen),failures
def main(argv=None):
 p=argparse.ArgumentParser();p.add_argument('--manifest',default='manifest/variants.json');p.add_argument('--only',action='append');p.add_argument('--output',default='evidence/java-variants.json');a=p.parse_args(argv)
 output=R/a.output;output.parent.mkdir(parents=True,exist_ok=True)
 report={'status':'BLOCKED','evidence_type':'FRESH_COMPILE_AND_JUNIT','selected':[],'results':[],'reason':'validation has not started'}
 def save():output.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
 save() # Replace stale success report before input validation or a subprocess.
 try:
  require(__debug__,'拒绝Python优化模式；请勿使用-O/PYTHONOPTIMIZE')
  variants=json.loads((R/a.manifest).read_text());require(isinstance(variants,dict) and bool(variants),'manifest不能为空')
  if a.only:
   unknown=set(a.only)-set(variants);require(not unknown,'未知--only: '+','.join(sorted(unknown)))
   require(len(a.only)==len(set(a.only)),'重复--only选择')
   variants={k:variants[k] for k in a.only}
  require(bool(variants),'执行集合不能为空')
  java_home=os.environ.get('JAVA_HOME');gradle_home=os.environ.get('GRADLE_HOME')
  require(bool(java_home and gradle_home),'请设置已有JDK21的JAVA_HOME及Gradle8.10.2的GRADLE_HOME')
  report['selected']=list(variants);report['reason']=None;save()
  all_cases=inventory(R/'observability-lab/src/test/java');require(bool(all_cases),'没有已声明的公开@Test方法')
  runs=R/'validation-runs';runs.mkdir(exist_ok=True)
  for name,v in variants.items():
   require(re.fullmatch(r'[a-z0-9-]+',name) is not None,'非法变体名')
   row={'variant':name,'status':'BLOCKED','compilation_ok':False,'tests':0,'failures':0,'skipped':0}
   report['results'].append(row);save()
   try:
    expected={c for c in all_cases if any(fnmatch.fnmatchcase(c.split('#')[0],pattern) for pattern in v['tests'])}
    require(bool(expected),'测试选择为空')
    declared=set(v.get('expected_test_cases',[]));require(declared==expected,'manifest测试清单与公开测试/选择器不一致')
    allowed=set(v.get('expected_failure_cases',[]));require(allowed<=expected,'失败清单越出所选测试')
    require(v['expected'] in ('PASS','EXPECTED_TEST_FAILURE'),'未知expected类型')
    if v['expected']=='EXPECTED_TEST_FAILURE':require(bool(allowed),'负例必须声明业务失败方法')
    run_dir=Path(tempfile.mkdtemp(prefix=name+'-',dir=runs));build=run_dir/'build'
    src=(R/v['path']).resolve();require(src.is_relative_to(R.resolve()) and src.is_dir(),'源码必须在本草稿范围内')
    shutil.copytree(src,run_dir/'source');shutil.copytree(R/'observability-lab/src/test/java',run_dir/'tests')
    digest=source_hash(run_dir/'source');test_digest=source_hash(run_dir/'tests')
    row.update({'run_directory':str(run_dir.relative_to(R)),'source_sha256':digest,'test_source_sha256':test_digest})
    base=[str(Path(gradle_home)/'bin/gradle'),'--no-daemon','--no-build-cache','--max-workers=1','-Dorg.gradle.jvmargs=-Xmx384m -XX:ActiveProcessorCount=2','-p',str(R/'validation'),f'-PsourceRoot={run_dir/"source"}',f'-PtestSourceRoot={run_dir/"tests"}',f'-PvariantBuild={build}','--console=plain']
    env={**os.environ,'JAVA_HOME':java_home}
    compiled=subprocess.run(base+['clean','testClasses','--rerun-tasks'],env=env,capture_output=True,text=True,timeout=180)
    (run_dir/'compile.log').write_text(compiled.stdout+compiled.stderr)
    row['compile_exit']=compiled.returncode
    require(compiled.returncode==0,'本次testClasses编译失败或工具未启动，不能读取旧测试结果')
    # The unique directory did not exist before this invocation; all reports must come from step 2.
    require(not list(build.rglob('TEST-*.xml')),'编译阶段出现JUnit结果，拒绝污染证据')
    class_count=0
    for origin,kind in [(run_dir/'source','main'),(run_dir/'tests','test')]:
     for java in origin.rglob('*.java'):
      text=java.read_text();package=re.search(r'package\s+([\w.]+)\s*;',text)
      if not package:continue
      klass=build/'classes/java'/kind/Path(package.group(1).replace('.','/'))/(java.stem+'.class')
      require(klass.is_file() and klass.read_bytes().startswith(bytes.fromhex('cafebabe')),'本次编译未产出预期class: '+java.name)
      class_count+=1
    require(class_count>0,'没有本次编译产物')
    row['compile_artifact_count']=class_count
    row['compilation_ok']=True
    test_command=base+['test','--rerun-tasks']
    for selector in v['tests']:test_command+=['--tests',selector]
    tested=subprocess.run(test_command,env=env,capture_output=True,text=True,timeout=180)
    (run_dir/'test.log').write_text(tested.stdout+tested.stderr);row['test_exit']=tested.returncode
    require(source_hash(run_dir/'source')==digest and source_hash(run_dir/'tests')==test_digest,'运行中源码发生变化')
    count,failures=read_results(build,expected,allowed,name=='starter' or name.startswith('native-starter-'))
    row.update({'tests':count,'failures':len(failures),'failed_business_cases':failures})
    if v['expected']=='PASS':require(tested.returncode==0 and not failures,'正确解未全部通过')
    else:require(tested.returncode!=0 and bool(failures),'负例没有预期业务断言失败')
    row['status']='PASS'
   except (OSError,subprocess.TimeoutExpired) as e:row.update({'status':'BLOCKED','reason':type(e).__name__+': '+str(e)})
   except Exception as e:row.update({'status':'FAIL','reason':type(e).__name__+': '+str(e)})
   save();print(name,row['status'],row['tests'],row['failures'],flush=True)
  require(len(report['results'])==len(report['selected'])>0,'结果集合不完整')
  report['status']='PASS' if all(x['status']=='PASS' for x in report['results']) else 'FAIL'
 except Exception as e:report.update({'status':'BLOCKED','reason':type(e).__name__+': '+str(e)})
 save();return 0 if report['status']=='PASS' else 1
if __name__=='__main__':raise SystemExit(main())
