#!/usr/bin/env python3
"""C15 serial Java acceptance; only evidence from this invocation is accepted."""
from pathlib import Path
import argparse,errno,hashlib,json,os,re,shutil,signal,socket,subprocess,sys,tempfile,time,uuid,types
import verify_finalizedby_gate as strict
try:
 from owned_process import OwnedProcess
except ImportError:
 OwnedProcess=None
ROOT=Path(__file__).resolve().parents[1]
WORKFLOW='.github/workflows/identity-java.yml'
PREFIX='courses/identity-labs/'
NAMES=('table','explicit','starter','token-means-admin','missing-tenant-check','admin-any-action','wrong-reasons','empty-identifiers','wrong-precedence')
LOCKS={
 'identity/01-policy/lab/gradle.lockfile':'1f91c1662aa8ffa6bf5423cb507ab520647793944e1eb886033c63b8ceae85b1',
 'materials/identity/identity-lab/gradle.lockfile':'e9ba38009bbf248b5e5c697d572ab96c1c05b7fa9e5c95ab806a14d581013ff2'}
FLAGS=['--no-daemon','--no-build-cache','--no-configuration-cache','--rerun-tasks','--console=plain','--max-workers=1']
GROUP_PATHS={'unit':strict.TASK/'build/test-results/test','http':strict.SERVICE/'build/test-results/httpAcceptance','service':strict.SERVICE/'build/test-results/test'}
SERVICE_TASK=':identity-resource-server:test'
def require(ok,message):
 if not ok:raise ValueError(message)
def save(path,data):
 path.parent.mkdir(parents=True,exist_ok=True);path.write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n')
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
class Budget:
 def __init__(self,seconds=480):self.deadline=time.monotonic()+seconds
 def remaining(self):
  left=self.deadline-time.monotonic();require(left>0,'CI hard deadline expired');return left
 def check(self):self.remaining()
def source_snapshot(root=ROOT):
 repo=root.parents[1]
 p=subprocess.run(['git','-C',str(repo),'ls-files','-z','--',PREFIX,WORKFLOW],capture_output=True,check=True,timeout=10)
 names=[n for n in p.stdout.decode().split('\0') if n]
 require(WORKFLOW in names and all(PREFIX+n in names for n in LOCKS),'workflow or fixed locks are not tracked')
 result={}
 for name in sorted(names):
  path=repo/name
  require((name.startswith(PREFIX) or name==WORKFLOW) and path.is_file() and not path.is_symlink() and path.resolve().is_relative_to(repo.resolve()),'unsafe tracked source path')
  result[name]=sha(path)
 require(strict.source_map(root)=={k[len(PREFIX):]:v for k,v in result.items() if k.startswith(PREFIX)},'untracked/missing course source affects execution')
 return result

def run_owned(command,folder,budget,phase_seconds=480):
 folder.mkdir(parents=True,exist_ok=False);save(folder/'command.json',command)
 start=time.time_ns();process=None;error=None;code=None;cleanup=None
 try:
  require(OwnedProcess is not None,'reviewed owned-process cleanup module is missing')
  timeout=min(phase_seconds,budget.remaining())
  with (folder/'console.log').open('wb') as log:
   process=OwnedProcess(command,log);code=process.wait(timeout=timeout)
  budget.check()
 except BaseException as exc:error=type(exc).__name__+': '+str(exc)
 finally:
  if process is not None:
   try:
    cleanup=process.stop();require(cleanup.get('status')=='PASS','owned descendants did not converge');budget.check()
   except BaseException as exc:error=(error or '')+'; cleanup: '+str(exc)
  result={'command':command,'exit':code,'start_ns':start,'end_ns':time.time_ns(),'status':'FAIL' if error else 'FINISHED','reason':error,'cleanup':cleanup}
  save(folder/'result.json',result)
 require(error is None,'execution/cleanup failed: '+str(error))
 return result

def validate_case_groups(source,contract,result):
 require(result['status']=='FINISHED' and result['exit']==contract['expected_exit'],'wrong Gradle exit or infrastructure failure')
 actual={};groups={}
 for group,folder in GROUP_PATHS.items():
  expected=contract['groups'].get(group)
  if expected is None:
   require(not list((source/folder).glob('TEST-*.xml')),'unexpected service suite after learner failure');continue
  cases=strict.parse_xml(source/folder,expected,result['start_ns'],result['end_ns']);groups[group]=cases
  actual.update({group+'|'+suite+'|'+method:c for (suite,method),c in cases.items()})
 require(len(actual)==contract['method_calls'],'wrong exact executed method count')
 require(not any(c['state'] in ('error','skipped') for c in actual.values()),'error/skip is never a business negative')
 failures={key:c for key,c in actual.items() if c['state']=='failure'}
 require(set(failures)==set(contract['expected_failures']),'wrong exact business failure set')
 for key,expected in contract['expected_failures'].items():
  case=failures[key];_,suite,method=key.split('|')
  require(case['failure_type']==expected['type'] and case['failure_message']==expected['message'],'wrong exception type/message for '+key)
  require(suite+'.'+method in (case['failure_text'] or ''),'wrong failure origin')
 return groups

def task_row_ok(row,failed=False):
 return row.get('executed') is True and row.get('skipped') is False and row.get('up_to_date') is False and row.get('no_source') is False and row.get('skip_message') is None and row.get('failed') is failed
def validate_receipts(source,data,contract,result,groups):
 require(strict.source_map(source)==data['sources'],'source/config/lock changed during variant')
 events=strict.read_jsonl(Path(data['receipt']),result['start_ns'],result['end_ns'])
 for event in events:
  require(event.get('kind') in {'start','case','finish','task'},'unknown receipt event')
  for key in ('run_id','binding_sha256','source_sha256','config_sha256','locks_sha256'):
   require(event.get(key)==data[key],'receipt binding mismatch')
 failed_tasks=[]
 for group,task in [('unit',strict.UNIT_TASK),('http',strict.HTTP_TASK)]:
  cases=groups[group];rows=[e for e in events if e.get('task')==task]
  start=[e for e in rows if e['kind']=='start'];finish=[e for e in rows if e['kind']=='finish'];tasks=[e for e in rows if e['kind']=='task'];tests=[e for e in rows if e['kind']=='case']
  require(len(start)==len(finish)==len(tasks)==1,'missing/duplicate target task receipt')
  require(start[0].get('gradle_version')=='8.10.2' and start[0].get('java_major')=='21','wrong actual toolchain')
  count=sum(c['state']=='failure' for c in cases.values());has_failure=count>0
  if has_failure:failed_tasks.append(task)
  require(task_row_ok(tasks[0],has_failure),'cached/skipped/failed task state mismatch')
  require(len(tests)==len(cases),'wrong receipt case count');seen=set()
  for event in tests:
   key=(event.get('class'),strict.method_name(event.get('method')))
   require(key in cases and key not in seen,'wrong/duplicate receipt case');seen.add(key)
   require(event.get('result')==('FAILURE' if cases[key]['state']=='failure' else 'SUCCESS'),'XML/receipt case result mismatch')
  require(seen==set(cases),'missing receipt case')
  require(finish[0].get('tests')==len(cases) and finish[0].get('failed')==count and finish[0].get('skipped')==0 and finish[0].get('successful')==len(cases)-count,'wrong receipt totals')
  require(start[0]['time_ms']<=finish[0]['time_ms']<=tasks[0]['time_ms'],'wrong receipt chronology')
 required=[*strict.BUILD_TASKS]+([SERVICE_TASK] if 'service' in groups else [])
 for task in required:
  rows=[e for e in events if e['kind']=='task' and e.get('task')==task]
  require(len(rows)==1 and task_row_ok(rows[0]),'compile/jar/provenance/service task not freshly successful: '+task)
 if 'service' not in groups:require(not [e for e in events if e.get('task')==SERVICE_TASK],'unexpected service task after learner failure')
 require([e.get('task') for e in events if e['kind']=='task' and e.get('failed') is True]==failed_tasks,'unexpected failing task/compile/infrastructure')
 require(all(e['kind']=='task' or e.get('task') in (strict.UNIT_TASK,strict.HTTP_TASK) for e in events),'unexpected test receipt task')
 trace=strict.read_jsonl(Path(data['http_trace']),result['start_ns'],result['end_ns']);require(len(trace)==1,'wrong HTTP trace count');row=trace[0]
 require(row.get('run_id')==data['run_id'] and row.get('binding_sha256')==data['binding_sha256'],'HTTP trace binding mismatch')
 require(row.get('suite')=='labs.identity.IdentityNetworkTest' and row.get('method')==strict.METHOD and row.get('marker')==strict.MARKER,'wrong HTTP trace identity')
 require(type(row.get('expected')) is int and row['expected']==200 and type(row.get('observed')) is int and row['observed']==contract['http_observed'],'wrong actual HTTP trace value')
 text=Path(result['log']).read_text()
 for task in [strict.UNIT_TASK,strict.HTTP_TASK,*required]:
  require('> Task '+task+(' FAILED' if task in failed_tasks else '')+'\n' in text,'missing executed task output')
  for line in text.splitlines():
   if task in line:require(not any(token in line for token in ('FROM-CACHE','UP-TO-DATE','NO-SOURCE','SKIPPED')),'cached/unexecuted target log')
 require(('BUILD FAILED' if failed_tasks else 'BUILD SUCCESSFUL') in text,'missing Gradle final result')

def prepare_variant(root,work,name,contract,gradle,java):
 folder=work/'variants'/name;source=folder/'source';folder.mkdir(parents=True,exist_ok=False)
 shutil.copytree(root,source,ignore=shutil.ignore_patterns(*strict.EXCLUDED))
 policy=source/contract['policy_path'];require(sha(policy)==contract['policy_sha256'],'frozen variant source changed')
 if policy!=source/strict.TASK/'src/labs/identity/Policy.java':shutil.copyfile(policy,source/strict.TASK/'src/labs/identity/Policy.java')
 sources=strict.source_map(source);run_id=str(uuid.uuid4());config={'variant':name,'flags':FLAGS,'task':'identityCheck','gradle_sha256':sha(gradle),'java_sha256':sha(java),'contract_sha256':strict.digest(contract)}
 data={'schema':2,'run_id':run_id,'scenario':name,'sources':sources,'source_sha256':strict.digest(sources),'config':config,'config_sha256':strict.digest(config),'locks':LOCKS,'locks_sha256':strict.digest(LOCKS),'receipt':str(folder/'execution.jsonl'),'http_trace':str(folder/'http.jsonl')}
 data['binding_sha256']=strict.digest({k:data[k] for k in ('run_id','scenario','source_sha256','config_sha256','locks_sha256')});save(folder/'input.json',data)
 return folder,source,data
def run_variant(root,work,name,contract,gradle,java,budget):
 folder,source,data=prepare_variant(root,work,name,contract,gradle,java);input_hash=sha(folder/'input.json')
 result=run_owned([str(gradle),*FLAGS,'-p',str(source),'clean','identityCheck','-PidentityGateInput='+str(folder/'input.json')],folder/'execution',budget)
 result['log']=str(folder/'execution/console.log')
 require(sha(folder/'input.json')==input_hash,'input changed during variant')
 require(sha(gradle)==data['config']['gradle_sha256'] and sha(java)==data['config']['java_sha256'],'tool entry changed during variant')
 groups=validate_case_groups(source,contract,result);validate_receipts(source,data,contract,result,groups)
 summary={'variant':name,'status':'PASS','run_id':data['run_id'],'gradle_exit':result['exit'],'method_calls':contract['method_calls'],'unique_methods':len({case for cases in groups.values() for case in cases}),'expected_business_failures':len(contract['expected_failures']),'errors':0,'skips':0,'binding_sha256':data['binding_sha256']};save(folder/'summary.json',summary);return summary

def run_strict_gate(root,work,gradle,java_home,budget):
 # Reuse the unchanged strict algorithm with an actual streaming subprocess
 # adapter. Each Gradle process is owned and logs survive timeout/interruption.
 output=work/'strict-gate';started=time.time_ns();launched=[]
 original_subprocess=strict.subprocess;original_argv=sys.argv
 def actual_run(command,**options):
  require(command[0]==str(gradle) and options.get('capture_output') is True and options.get('text') is True,'unexpected strict process request')
  require(options.get('env')==dict(os.environ,JAVA_HOME=str(java_home),TZ='UTC') and os.environ.get('JAVA_HOME')==str(java_home) and os.environ.get('TZ')=='UTC','strict process environment differs')
  folder=work/'strict-executions'/str(len(launched)+1);launched.append(folder)
  result=run_owned(command,folder,budget,min(600,options['timeout']))
  return subprocess.CompletedProcess(command,result['exit'],stdout=(folder/'console.log').read_text(),stderr='')
 try:
  strict.subprocess=types.SimpleNamespace(run=actual_run,TimeoutExpired=subprocess.TimeoutExpired)
  sys.argv=[str(root/'scripts/verify_finalizedby_gate.py'),'--gradle',str(gradle),'--java-home',str(java_home),'--output',str(output)]
  code=strict.main()
 finally:
  strict.subprocess=original_subprocess;sys.argv=original_argv
 ended=time.time_ns();require(code==0,'strict real HTTP gate failed')
 rows=json.loads((output/'gate-results.json').read_text());require([r.get('scenario') for r in rows]==['table-positive','explicit-positive','real-http-negative'],'strict gate scenario set changed')
 require(len(launched)==3 and len({r.get('detail',{}).get('run_id') for r in rows})==3,'missing invocation or duplicate strict run ID')
 for row in rows:
  require(row.get('status')=='PASS' and row.get('gradle_exit')==(1 if row['scenario']=='real-http-negative' else 0),'strict gate result not successful')
  require(row.get('detail',{}).get('unit_cases')==11 and row.get('detail',{}).get('http_cases')==4,'strict gate scope changed')
  folder=output/row['scenario'];data=json.loads((folder/'input.json').read_text())
  require(sha(folder/'input.json')==row['input_sha256'],'strict input hash changed')
  completed=subprocess.CompletedProcess([],row['gradle_exit'],stdout=(folder/'gradle.log').read_text(),stderr='')
  strict.validate(folder/'source',data,completed,started,ended,json.loads((root/'gate-contract.json').read_text()))
 return rows

def run_duplicate(root,work,gradle,budget):
 folder=work/'duplicate-source';source=folder/'source';folder.mkdir(parents=True)
 shutil.copytree(root,source,ignore=shutil.ignore_patterns(*strict.EXCLUDED));table=source/strict.TASK/'reference/table/Policy.java'
 shutil.copyfile(table,source/strict.TASK/'src/labs/identity/Policy.java');shutil.copyfile(table,source/strict.SERVICE/'src/main/java/labs/identity/Policy.java')
 before=strict.source_map(source);save(folder/'source-before.json',before)
 result=run_owned([str(gradle),*FLAGS,'-p',str(source),'clean',':identity-resource-server:verifyProductionPolicyJar'],folder/'execution',budget)
 text=(folder/'execution/console.log').read_text()
 require(result['exit']==1 and '> Task :identity-resource-server:compileJava\n' in text and '> Task :identity-01-policy-lab:compileJava\n' in text,'duplicate-source did not compile first')
 require('> Task :identity-resource-server:verifyProductionPolicyJar FAILED\n' in text and '服务不准有本地Policy源副本' in text,'duplicate-source gate did not reject the intended defect')
 require(re.findall(r'^> Task (\S+) FAILED$',text,re.M)==[':identity-resource-server:verifyProductionPolicyJar'],'unexpected duplicate-source failure task')
 require(strict.source_map(source)==before,'duplicate-source inputs changed')
 return {'status':'PASS','kind':'structural rejection, not a business negative','gradle_exit':1}
def closed_ports(work):
 roots=[work/'strict-gate'/name/'source' for name in ('table-positive','explicit-positive','real-http-negative')]+[work/'variants'/name/'source' for name in NAMES]
 rows=[]
 for source in roots:
  ports=[]
  for p in (source/GROUP_PATHS['http']).glob('TEST-*.xml'):
   ports.extend(map(int,re.findall(r'Tomcat started on port (\d+)',p.read_text())))
  require(len(ports)==1 and 0<ports[0]<65536,'each HTTP scenario requires exactly one actual Tomcat port')
  port=ports[0]
  with socket.socket() as sock:sock.settimeout(.5);code=sock.connect_ex(('127.0.0.1',port))
  rows.append({'scenario':str(source.parent.relative_to(work)),'port':port,'connect_ex':code});require(code==errno.ECONNREFUSED,'HTTP port still open or cleanup inconclusive')
 return rows

def validate_summary(gate,variants):
 require([x.get('variant') for x in variants]==list(NAMES),'missing/duplicate/reordered matrix summary')
 require(all(x.get('status')=='PASS' and x.get('errors')==0 and x.get('skips')==0 for x in variants),'matrix summary is not entirely accepted')
 expected_failures=[0,0,12,12,4,2,11,2,2]
 for i,row in enumerate(variants):
  positive=row['variant'] in ('table','explicit')
  require(row.get('method_calls')==(35 if positive else 15) and row.get('unique_methods')==(33 if positive else 15),'matrix summary method scope mismatch')
  require(row.get('gradle_exit')==(0 if positive else 1) and row.get('expected_business_failures')==expected_failures[i],'matrix summary failure contract mismatch')
 ids=[x.get('run_id') for x in variants]+[x.get('detail',{}).get('run_id') for x in gate]
 require(len(ids)==12 and len(set(ids))==12 and all(isinstance(x,str) and x for x in ids),'all twelve Java scenarios require different run IDs')

def public_evidence(work,out):
 records=[];known={'input.json','execution.jsonl','http.jsonl','gate-results.json','command.json','result.json','summary.json','source-before.json','console.log','gradle.log'}
 for p in sorted(work.rglob('*')):
  if not p.is_file() or 'source' in p.relative_to(work).parts and not (p.name.startswith('TEST-') and p.suffix=='.xml'):continue
  if p.name not in known and not (p.name.startswith('TEST-') and p.suffix=='.xml'):continue
  target=out/'runs'/p.relative_to(work);target.parent.mkdir(parents=True,exist_ok=True);raw=p.read_text()
  clean=re.sub(r'eyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}','[REDACTED_JWT]',raw)
  clean=re.sub(r'-----BEGIN (?:RSA |EC |)PRIVATE KEY-----.*?-----END (?:RSA |EC |)PRIVATE KEY-----','[REDACTED_PRIVATE_KEY]',clean,flags=re.S)
  target.write_text(clean);records.append({'path':str(target.relative_to(out)),'sha256':sha(target),'original_sha256':sha(p),'redacted':clean!=raw})
 save(out/'artifact-files.json',records);return len(records)
def interrupted(signum,frame):raise InterruptedError('CI invocation interrupted')
def main():
 parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',type=Path,default=Path(os.environ.get('C15_EVIDENCE_DIRECTORY',str(ROOT.parent/'identity-ci-evidence'))));args=parser.parse_args()
 out=args.output.resolve();require(not out.is_relative_to(ROOT),'evidence must be outside course sources');out.mkdir(parents=True,exist_ok=True)
 stale_output=(out/'runs').exists() or (out/'source-before.json').exists()
 receipt={'status':'RUNNING','scope':'CURRENT_CI_INVOCATION','started_unix':time.time(),'github_sha':os.environ.get('GITHUB_SHA'),'pr_head_sha':os.environ.get('C15_PR_HEAD_SHA'),'java_matrix':'NOT_RUN','scenarios':[]};save(out/'receipt.json',receipt)
 budget=Budget();before=None;work=None;failure=None;previous=signal.signal(signal.SIGTERM,interrupted);os.environ['TZ']='UTC'
 try:
  require(__debug__,'Python optimized mode is forbidden');require(not stale_output,'refuse stale evidence output directory')
  require(OwnedProcess is not None,'reviewed owned-process implementation missing')
  before=source_snapshot(ROOT);save(out/'source-before.json',before)
  require(all(sha(ROOT/p)==expected for p,expected in LOCKS.items()),'fixed dependency lock changed')
  home=Path(os.environ['JAVA_HOME']);gradle=Path(os.environ['GRADLE_HOME'])/'bin/gradle';java=home/'bin/java'
  release=(home/'release').read_text();require('JAVA_VERSION="21.0.12.1"' in release and 'JAVA_RUNTIME_VERSION="21.0.12.1+1-LTS"' in release and 'IMPLEMENTOR="Eclipse Adoptium"' in release,'requires full pinned Temurin 21.0.12.1+1')
  require((home/'bin/javac').is_file() and (home/'lib/ct.sym').is_file() and (home/'jmods/java.base.jmod').is_file(),'full JDK compiler/modules required')
  work=Path(tempfile.mkdtemp(prefix='c15-work-',dir=os.environ.get('RUNNER_TEMP')));receipt['run_id']=work.name
  receipt['tool_sha256']={'java':sha(java),'javac':sha(home/'bin/javac'),'gradle':sha(gradle)};receipt['locks']=LOCKS
  for name,command,expected in [('java',[str(java),'-version'],'21.0.12.1'),('javac',[str(home/'bin/javac'),'-version'],'javac 21.0.12.1'),('gradle',[str(gradle),'--version'],'Gradle 8.10.2')]:
   result=run_owned(command,work/('version-'+name),budget,30);require(result['exit']==0 and expected in (work/('version-'+name)/'console.log').read_text(),'wrong '+name+' version')
  receipt['strict_gate']=run_strict_gate(ROOT,work,gradle,home,budget);save(out/'receipt.json',receipt)
  manifest=json.loads((ROOT/'manifest/ci-variants.json').read_text());require(manifest.get('schema')==1 and tuple(manifest['variants'])==NAMES,'frozen variant matrix changed')
  for name in NAMES:
   receipt['scenarios'].append(run_variant(ROOT,work,name,manifest['variants'][name],gradle,java,budget));save(out/'receipt.json',receipt)
  validate_summary(receipt['strict_gate'],receipt['scenarios'])
  receipt['duplicate_source']=run_duplicate(ROOT,work,gradle,budget);receipt['ports']=closed_ports(work)
  budget.check();receipt['java_matrix']='PASS'
 except BaseException as exc:failure=type(exc).__name__+': '+str(exc)
 finally:
  if before is not None:
   try:
    after=source_snapshot(ROOT);save(out/'source-after.json',after);require(before==after,'tracked source/lock/workflow changed');receipt['source_unchanged']=True
   except BaseException as exc:failure=(failure or '')+'; integrity: '+str(exc)
  if work is not None:
   try:receipt['artifact_files']=public_evidence(work,out)
   except BaseException as exc:failure=(failure or '')+'; artifact collection: '+str(exc)
  try:budget.check()
  except BaseException as exc:failure=(failure or '')+'; deadline: '+str(exc)
  receipt['status']='FAIL' if failure else 'PASS';receipt['reason']=failure;receipt['finished_unix']=time.time();save(out/'receipt.json',receipt);signal.signal(signal.SIGTERM,previous)
 print(json.dumps({'status':receipt['status'],'receipt':str(out/'receipt.json'),'reason':failure},ensure_ascii=False))
 return 1 if failure else 0
if __name__=='__main__':raise SystemExit(main())

