from pathlib import Path
import ctypes,os,re,select,signal,subprocess,sys,time
def require(ok,message):
 if not ok:raise ValueError(message)
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
