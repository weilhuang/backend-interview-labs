#!/usr/bin/env python3
"""Run the unchanged strict Java gate for current main plus all frozen variants."""
from pathlib import Path
import ctypes,errno,hashlib,json,os,re,select,signal,socket,subprocess,sys,tempfile,time
import verify_java_variants as strict
R=Path(__file__).resolve().parents[1]
WORKFLOW='.github/workflows/observability-java.yml'
NAMES=('reference-map','reference-typed','starter','wrong-header-leak','wrong-json-concatenation','wrong-high-cardinality','wrong-millisecond-unit','wrong-double-count','wrong-new-trace-every-hop','wrong-baggage-leak','wrong-retry-all-failures','native-starter-safe-events','native-starter-metrics','native-starter-trace-context')
def require(ok,message):
 if not ok:raise ValueError(message)
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def save(path,value):path.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n')
def source_snapshot():
 repo=R.parents[1]
 result=subprocess.run(['git','-C',str(repo),'ls-files','-z','--','courses/observability-labs',WORKFLOW],capture_output=True,check=True,timeout=10)
 names=[n for n in result.stdout.decode().split('\0') if n]
 require(bool(names),'no tracked course sources')
 require('courses/observability-labs/validation/gradle.lockfile' in names,'new dependency lock is not tracked')
 return {name:sha(repo/name) for name in sorted(names)}
def validate_report(report,manifest):
 require(report.get('status')=='PASS','strict gate did not pass')
 require(report.get('selected')==list(manifest),'scenario selection changed or incomplete')
 rows=report.get('results',[])
 require([r.get('variant') for r in rows]==list(manifest),'missing, duplicate, or reordered scenario result')
 require(len(rows)==15,'must run current main and all 14 variants')
 require(len({r.get('run_directory') for r in rows})==15,'each scenario needs its own fresh build directory')
 for row in rows:
  contract=manifest[row['variant']]
  require(row.get('status')=='PASS' and row.get('compilation_ok') is True and row.get('compile_exit')==0,'compilation or strict evidence failure')
  require(row.get('tests')==len(contract['expected_test_cases']) and row.get('skipped')==0,'test scope or skip count changed')
  observed={f['case'] for f in row.get('failed_business_cases',[])}
  expected=set(contract['expected_failure_cases'])
  require(observed==expected and row.get('failures')==len(expected),'business failure set changed')
  require(row.get('test_exit')==0 if not expected else row.get('test_exit') not in (None,0),'test exit does not match scenario contract')
 return rows
def process_identity(pid):
 """Read only a known PID. start_ticks and pidfd bind signals to its birth."""
 try:fields=Path('/proc/'+str(pid)+'/stat').read_text().rsplit(') ',1)[1].split()
 except FileNotFoundError:return None
 return {'pid':pid,'ppid':int(fields[1]),'pgid':int(fields[2]),'sid':int(fields[3]),'start_ticks':int(fields[19]),'state':fields[0]}
def child_pids(pid,deadline=None):
 # /proc/<pid>/task/<pid>/children may be absent or omit children born in other
 # threads. ps --ppid queries only this known parent's children across threads.
 if process_identity(pid) is None:return []
 remaining=1 if deadline is None else min(1,deadline-time.monotonic())
 require(remaining>0,'owned child discovery deadline expired')
 query=subprocess.Popen(['ps','--ppid',str(pid),'-o','pid='],stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
 try:stdout,stderr=query.communicate(timeout=remaining)
 except BaseException:
  query.kill();query.wait(timeout=.2);raise
 require(stderr=='','scoped child query reported diagnostics: '+stderr)
 if query.returncode==1:
  require(stdout=='','ambiguous no-match child query output')
  return []
 require(query.returncode==0,'scoped child query failed with exit '+str(query.returncode))
 lines=stdout.splitlines()
 require(bool(lines),'successful child query returned no PID rows')
 require(all(re.fullmatch(r'[ \t]*[1-9][0-9]*[ \t]*',line) for line in lines),'malformed child PID output')
 pids=[int(line.strip()) for line in lines]
 require(len(pids)==len(set(pids)) and all(n<=2147483647 for n in pids),'duplicate or invalid child PID output')
 return [pid for pid in pids if pid!=query.pid]
def same_birth(a,b):return a is not None and b is not None and (a['pid'],a['start_ticks'])==(b['pid'],b['start_ticks'])
class OwnedProcess:
 """A serial Linux child scope: no global process scan and no numeric killpg.

 A launch handshake binds the root before it can fork. A process-local subreaper
 keeps orphaned descendants in this scope, including children that call setsid.
 Discovery uses only ps --ppid <owned-pid> across parent threads; every signal
 uses a registered pidfd after a start-time check. Reused numeric IDs are refused.
 """
 def __init__(self,command,log):
  require(sys.platform=='linux' and hasattr(os,'pidfd_open') and hasattr(signal,'pidfd_send_signal'),'Linux pidfd support is required for certain cleanup')
  self.owner=os.getpid();self.entries={};self.process=None;self.finished=False;self.root=None
  require(not child_pids(self.owner),'owned scope requires no pre-existing direct children')
  self.libc=ctypes.CDLL(None,use_errno=True);old=ctypes.c_int()
  require(self.libc.prctl(37,ctypes.byref(old),0,0,0)==0,'cannot read process-local subreaper state')
  self.old_subreaper=old.value
  require(self.libc.prctl(36,1,0,0,0)==0,'cannot enable process-local child reaping')
  self.command=command
  launcher="import os,sys; token=sys.stdin.readline(); sys.exit(97) if token!='START\\n' else None; os.execvpe(sys.argv[1],sys.argv[1:],os.environ)"
  try:
   self.process=subprocess.Popen([sys.executable,'-c',launcher,*command],stdin=subprocess.PIPE,stdout=log,stderr=subprocess.STDOUT,start_new_session=True,env={**os.environ,'PYTHONDONTWRITEBYTECODE':'1'})
   self.root=process_identity(self.process.pid)
   require(self.root is not None and self.root['sid']==self.root['pid'] and self.root['pgid']==self.root['pid'],'root session identity was not established')
   self.register(self.process.pid,self.owner)
   self.process.stdin.write(b'START\n');self.process.stdin.flush();self.process.stdin.close()
  except BaseException:
   # Before the handshake completes, the launcher cannot create descendants.
   if self.process is not None:
    if self.process.stdin and not self.process.stdin.closed:self.process.stdin.close()
    entry=self.entries.get(self.process.pid)
    if entry is not None:
     try:signal.pidfd_send_signal(entry['fd'],signal.SIGKILL)
     except ProcessLookupError:pass
    self.process.wait(timeout=5)
   self.close_handles();raise
 def register(self,pid,parent):
  identity=process_identity(pid)
  if identity is None:return
  if pid in self.entries:
   require(same_birth(identity,self.entries[pid]['identity']),'owned PID birth changed; refusing identity reuse')
   return
  require(identity['ppid'] in (parent,self.owner),'descendant ancestry changed before registration')
  require(identity['start_ticks']>=self.root['start_ticks'],'descendant predates owned root')
  require(len(self.entries)<256,'owned descendant limit exceeded; cleanup cannot be certified')
  try:fd=os.pidfd_open(pid)
  except ProcessLookupError:return
  fresh=process_identity(pid)
  if fresh is None:os.close(fd);return
  if not same_birth(identity,fresh):os.close(fd);raise ValueError('PID birth changed while opening pidfd')
  self.entries[pid]={'identity':fresh,'fd':fd}
 def is_live(self,entry):
  if select.select([entry['fd']],[],[],0)[0]:return False
  fresh=process_identity(entry['identity']['pid'])
  if fresh is None and select.select([entry['fd']],[],[],0)[0]:return False
  require(same_birth(fresh,entry['identity']),'owned PID birth changed; signal refused')
  return True
 def capture(self,deadline=None):
  deadline=min(deadline if deadline is not None else float('inf'),time.monotonic()+1)
  queue=[self.owner];seen=set()
  while queue:
   require(time.monotonic()<deadline,'owned discovery deadline expired')
   parent=queue.pop()
   if parent in seen:continue
   seen.add(parent)
   if parent!=self.owner and not self.is_live(self.entries[parent]):continue
   children=child_pids(parent,deadline)
   if parent!=self.owner and not self.is_live(self.entries[parent]):continue
   for pid in children:
    self.register(pid,parent)
    if pid in self.entries:queue.append(pid)
 def wait(self,timeout):
  deadline=time.monotonic()+timeout
  while True:
   self.capture();code=self.process.poll()
   if code is not None:self.capture();return code
   if time.monotonic()>=deadline:raise subprocess.TimeoutExpired(self.command,timeout)
   time.sleep(.05)
 def close_handles(self):
  for entry in self.entries.values():os.close(entry['fd'])
  require(self.libc.prctl(36,self.old_subreaper,0,0,0)==0,'cannot restore process-local subreaper state')
 def stop(self,term_seconds=2,kill_seconds=2):
  require(not self.finished,'owned cleanup was already finalized')
  cleanup_deadline=time.monotonic()+6
  report={'status':'RUNNING','root_identity':self.root,'signals':[],'errors':[],'remaining':[]}
  def error(e):
   text=type(e).__name__+': '+str(e)
   if text not in report['errors']:report['errors'].append(text)
  def live():
   try:self.capture(cleanup_deadline)
   except Exception as e:error(e)
   active=[]
   for pid,entry in list(self.entries.items()):
    try:
     if self.is_live(entry):active.append((pid,entry))
    except Exception as e:error(e)
   return active
  try:
   for sig,seconds in [(signal.SIGTERM,term_seconds),(signal.SIGKILL,kill_seconds)]:
    until=min(cleanup_deadline,time.monotonic()+seconds);sent=set()
    while True:
     active=live()
     for pid,entry in active:
      if pid in sent:continue
      try:
       # Revalidate immediately before signalling; the pidfd also prevents PID reuse races.
       if self.is_live(entry):signal.pidfd_send_signal(entry['fd'],sig);report['signals'].append({'pid':pid,'start_ticks':entry['identity']['start_ticks'],'signal':sig.name})
       sent.add(pid)
      except ProcessLookupError:pass
      except Exception as e:error(e)
     if not active or time.monotonic()>=until:break
     time.sleep(.05)
   report['remaining']=[entry['identity'] for _,entry in live()]
   self.process.poll()
   for pid,entry in list(self.entries.items()):
    if pid==self.process.pid:continue
    try:
     if not self.is_live(entry):os.waitpid(pid,os.WNOHANG)
    except ChildProcessError:pass
    except Exception as e:error(e)
   # Reaping must leave no child outside the registered live set in this serial scope.
   residual=child_pids(self.owner,cleanup_deadline)
   if residual:report['errors'].append('owned child scope is not empty after cleanup: '+str(residual))
  except BaseException as e:error(e)
  finally:
   try:self.close_handles()
   except Exception as e:error(e)
   self.finished=True
  report['registered']=[entry['identity'] for entry in self.entries.values()]
  report['status']='PASS' if not report['errors'] and not report['remaining'] else 'FAIL'
  return report
def closed_ports(rows):
 ports=[]
 for row in rows:
  for xml in (R/row['run_directory']/'build/test-results/test').glob('TEST-*.xml'):
   ports.extend(int(p) for p in re.findall(r'C12_PORT_CLEANUP port=(\d+) CLOSED',xml.read_text()))
 require(len(ports)==8,'expected four real two-context HTTP suites and eight cleanup markers')
 results=[]
 for port in ports:
  with socket.socket() as sock:
   sock.settimeout(1);code=sock.connect_ex(('127.0.0.1',port))
  results.append({'port':port,'connect_ex':code,'connection_refused':code==errno.ECONNREFUSED})
 require(all(p['connection_refused'] for p in results),'a test HTTP port is still reachable or closure is inconclusive')
 return results
def interrupted(signum,frame):raise InterruptedError('CI process was interrupted')
def main():
 signal.signal(signal.SIGTERM,interrupted)
 deadline=time.monotonic()+480
 out=R/'evidence/ci';out.mkdir(parents=True,exist_ok=True)
 receipt={'status':'RUNNING','workflow_execution':'CURRENT_RUN_ONLY','backend_status':'NOT_RUN','started_unix':time.time(),'github_sha':os.environ.get('GITHUB_SHA'),'pr_head_sha':os.environ.get('C12_PR_HEAD_SHA'),'scenarios':[]}
 target=out/'receipt.json';save(target,receipt)
 before=None;process=None;failure=None;gradle=None;rows=[]
 try:
  require(__debug__,'Python -O/PYTHONOPTIMIZE is not supported')
  before=source_snapshot();save(out/'source-before.json',before)
  lock=R/'validation/gradle.lockfile';receipt['lock_sha256_before']=sha(lock)
  java_home=Path(os.environ['JAVA_HOME']);gradle=Path(os.environ['GRADLE_HOME'])/'bin/gradle'
  release=(java_home/'release').read_text()
  require('JAVA_VERSION="21.0.12.1"' in release and 'IMPLEMENTOR="Eclipse Adoptium"' in release,'requires the pinned full Temurin JDK')
  require((java_home/'bin/javac').is_file() and (java_home/'lib/ct.sym').is_file(),'full JDK compiler and ct.sym required')
  for name,cmd,expected in [('java',[str(java_home/'bin/java'),'-version'],'21.0.12.1'),('javac',[str(java_home/'bin/javac'),'-version'],'javac 21.0.12.1'),('gradle',[str(gradle),'--version'],'Gradle 8.10.2')]:
   version=subprocess.run(cmd,capture_output=True,text=True,timeout=30);text=version.stdout+version.stderr;(out/(name+'-version.log')).write_text(text)
   require(version.returncode==0 and expected in text,'unexpected '+name+' version')
  manifest=json.loads((R/'manifest/variants-extended.json').read_text())
  require(tuple(manifest)==NAMES,'frozen 14-variant contract changed')
  public=sorted(strict.inventory(R/'observability-lab/src/test/java'));require(len(public)==28,'public suite must contain all 28 methods')
  manifest={'current-main':{'path':'observability-lab/src/main/java','tests':['labs.observability.*'],'expected':'PASS','expected_test_cases':public,'expected_failure_cases':[]},**manifest}
  run=Path(tempfile.mkdtemp(prefix='run-',dir=out));save(run/'selected-manifest.json',manifest)
  report_path=run/'strict-results.json';receipt['run_id']=run.name;save(target,receipt)
  command=[sys.executable,str(R/'scripts/verify_java_variants.py'),'--manifest',str(run/'selected-manifest.json'),'--output',str(report_path)]
  save(run/'command.json',command)
  with (run/'console.log').open('w') as log:
   process=OwnedProcess(command,log)
   code=process.wait(timeout=max(1,deadline-time.monotonic()))
  receipt['strict_gate_exit']=code
  require(code==0,'strict gate returned failure; inspect per-scenario compile/test logs')
  rows=validate_report(json.loads(report_path.read_text()),manifest)
  # Re-read this run's XML with the same unchanged gate; never infer success from exit alone.
  for row in rows:
   contract=manifest[row['variant']]
   strict.read_results(R/row['run_directory']/'build',set(contract['expected_test_cases']),set(contract['expected_failure_cases']),row['variant']=='starter' or row['variant'].startswith('native-starter-'))
  receipt['scenarios']=rows;receipt['port_checks']=closed_ports(rows)
  receipt['test_executions']=sum(row['tests'] for row in rows)
  receipt['expected_business_failures']=sum(row['failures'] for row in rows)
  require(receipt['test_executions']==167 and receipt['expected_business_failures']==52,'aggregate contract changed')
 except BaseException as e:
  failure=type(e).__name__+': '+str(e)
 finally:
  if process is not None:
   try:
    receipt['process_cleanup']=process.stop()
    require(receipt['process_cleanup']['status']=='PASS','owned descendant cleanup was not confirmed')
   except BaseException as e:failure=(failure or '')+'; process cleanup: '+str(e)
  if gradle is not None and gradle.is_file():
   try:
    stopped=subprocess.run([str(gradle),'--stop'],capture_output=True,text=True,timeout=25);(out/'gradle-stop.log').write_text(stopped.stdout+stopped.stderr)
    require(stopped.returncode==0,'Gradle cleanup failed')
   except Exception as e:failure=(failure or '')+'; Gradle cleanup: '+str(e)
  if before is not None:
   try:
    after=source_snapshot();save(out/'source-after.json',after);receipt['source_unchanged']=after==before
    receipt['lock_sha256_after']=sha(R/'validation/gradle.lockfile')
    require(after==before and receipt['lock_sha256_after']==receipt['lock_sha256_before'],'tracked sources or dependency lock changed during execution')
   except Exception as e:failure=(failure or '')+'; integrity: '+str(e)
  receipt['status']='FAIL' if failure else 'PASS';receipt['reason']=failure;receipt['finished_unix']=time.time();save(target,receipt)
 print(json.dumps({'status':receipt['status'],'receipt':'evidence/ci/receipt.json','reason':failure},ensure_ascii=False),flush=True)
 return 1 if failure else 0
if __name__=='__main__':raise SystemExit(main())
