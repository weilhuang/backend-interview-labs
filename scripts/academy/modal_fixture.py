"""One private existing Xvfb, synthetic X11 windows, no IDE or consent action."""
from pathlib import Path
import ctypes as C,os,json,subprocess,time,tempfile,struct,sys,signal
R=Path(__file__).resolve().parent
import modal_window
from display_diagnostic import encode,publish
BINARY=Path('/usr/bin/Xvfb')
NAME='modal-window-fixture.json'
def require(ok):
    if not ok:raise ValueError('synthetic modal fixture boundary')
CASE_NAMES=('complete_dialog_signed_focus_proxy_shape_input','higher_root_overlay','input_only_interception','foreign_focus','descendant_restack_changes_proof','nondefault_shape_input')
def report_document(value):
    import re
    fields={'schema','status','kind','cases','cleanup','error','run_id','run_attempt','tested_sha','elapsed_milliseconds'}
    def require(ok):
        if not ok:raise ValueError('invalid synthetic modal fixture evidence')
    require(type(value) is dict and set(value)==fields and type(value['schema']) is int and value['schema']==1)
    require(value['status'] in ('PASS','FAIL') and value['kind']=='PRIVATE_SYNTHETIC_X11_NOT_IDE_OR_ACCEPTANCE')
    require(value['cleanup'] in ('NOT_STARTED','REAPED','UNVERIFIED'))
    require(value['error'] is None or value['error'] in ('PRECHECK_UNAVAILABLE','XVFB_START_UNAVAILABLE','PROOF_OR_FIXTURE_FAILED','CANCELLED','CLEANUP_UNVERIFIED'))
    for key,pattern in [('run_id',r'[1-9][0-9]{0,19}'),('run_attempt',r'[1-9][0-9]{0,19}'),('tested_sha',r'[0-9a-f]{40}')]:require(type(value[key]) is str and re.fullmatch(pattern,value[key]) is not None)
    require(type(value['elapsed_milliseconds']) is int and 0<=value['elapsed_milliseconds']<=90000)
    require(type(value['cases']) is list and len(value['cases'])<=len(CASE_NAMES))
    for index,item in enumerate(value['cases']):
        require(type(item) is dict and set(item)=={'case','status'} and item['case']==CASE_NAMES[index])
        require(item['status']==('PASS' if index in (0,4) else 'REJECTED'))
    if value['status']=='PASS':require(len(value['cases'])==len(CASE_NAMES) and value['cleanup']=='REAPED' and value['error'] is None)
    else:require(value['error'] is not None)
    return value

def main(output):
    # Existing workflow owns a one-minute step; local signal adds a50-second bound.
    def stop(*_):raise InterruptedError('CANCELLED')
    signal.signal(signal.SIGTERM,stop);signal.signal(signal.SIGINT,stop);signal.signal(signal.SIGALRM,stop);signal.alarm(50)
    start=time.monotonic();report={'schema':1,'status':'FAIL','kind':'PRIVATE_SYNTHETIC_X11_NOT_IDE_OR_ACCEPTANCE','cases':[],'cleanup':'NOT_STARTED','error':'PRECHECK_UNAVAILABLE','run_id':os.environ['GITHUB_RUN_ID'],'run_attempt':os.environ['GITHUB_RUN_ATTEMPT'],'tested_sha':os.environ['GITHUB_SHA']}
    temp=tempfile.TemporaryDirectory(prefix='academy-modal-x11-');folder=Path(temp.name);os.chmod(folder,0o700)
    server=None;fd=None;connection=None
    try:
     display=':7999';require(not Path('/tmp/.X11-unix/X7999').exists() and not Path('/tmp/.X7999-lock').exists())
     cookie=os.urandom(16)
     def field(raw):return struct.pack('>H',len(raw))+raw
     authority=folder/'authority';authority.write_bytes(struct.pack('>H',65535)+field(b'')+field(b'7999')+field(b'MIT-MAGIC-COOKIE-1')+field(cookie));authority.chmod(0o600)
     env={'PATH':os.defpath,'LANG':'C.UTF-8','DISPLAY':display,'XAUTHORITY':str(authority)}
     require(BINARY.is_file() and not BINARY.is_symlink())
     report['error']='XVFB_START_UNAVAILABLE'
     server=subprocess.Popen([str(BINARY),display,'-screen','0','1280x900x24','-nolisten','tcp','-auth',str(authority),'-noreset'],env=env,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,start_new_session=True)
     fd=os.pidfd_open(server.pid);os.environ['DISPLAY']=display;os.environ['XAUTHORITY']=str(authority)
     x=C.CDLL('libX11.so.6');u=C.c_ulong;i=C.c_int;ptr=C.c_void_p
     specs={'XOpenDisplay':([C.c_char_p],ptr),'XDefaultRootWindow':([ptr],u),'XCreateSimpleWindow':([ptr,u,i,i,C.c_uint,C.c_uint,C.c_uint,u,u],u),'XMapWindow':([ptr,u],i),'XDestroyWindow':([ptr,u],i),'XRaiseWindow':([ptr,u],i),'XLowerWindow':([ptr,u],i),'XStoreName':([ptr,u,C.c_char_p],i),'XInternAtom':([ptr,C.c_char_p,i],u),'XChangeProperty':([ptr,u,u,u,i,i,C.c_void_p,i],i),'XSetInputFocus':([ptr,u,i,u],i),'XSync':([ptr,i],i),'XCloseDisplay':([ptr],i),'XMoveWindow':([ptr,u,i,i],i),'XCreateWindow':([ptr,u,i,i,C.c_uint,C.c_uint,C.c_uint,i,C.c_uint,ptr,u,ptr],u)}
     for name,(args,result) in specs.items():fn=getattr(x,name);fn.argtypes=args;fn.restype=result
     until=time.monotonic()+5
     while time.monotonic()<until:
      if server.poll() is not None:raise RuntimeError('XVFB_START_EXIT')
      connection=x.XOpenDisplay(display.encode())
      if connection:break
      time.sleep(.05)
     require(bool(connection))
     report['error']='PROOF_OR_FIXTURE_FAILED'
     root=x.XDefaultRootWindow(connection)
     def pid_prop(win):
      value=u(os.getpid());x.XChangeProperty(connection,win,x.XInternAtom(connection,b'_NET_WM_PID',False),x.XInternAtom(connection,b'CARDINAL',False),32,0,C.byref(value),1)
     def create(parent,xx,yy,w,h,name):
      win=x.XCreateSimpleWindow(connection,parent,xx,yy,w,h,0,0,0x444444);pid_prop(win);x.XStoreName(connection,win,name.encode());x.XMapWindow(connection,win);return win
     background=create(root,0,0,1280,900,'synthetic owned background');dialog=create(root,380,335,520,235,'synthetic Academy agreement')
     proxy=create(dialog,-1,-1,1,1,'synthetic focus proxy');child=create(dialog,0,0,520,235,'synthetic content')
     x.XSetInputFocus(connection,proxy,1,0);x.XSync(connection,False)
     action='CHECK_ACADEMY_PLUGIN_ONLY'
     def observe():
      require(time.monotonic()-start<45)
      code="import sys,json;sys.path.insert(0,sys.argv[1]);import modal_window;print(json.dumps(modal_window.observe(int(sys.argv[2]),sys.argv[3])))"
      result=subprocess.run([sys.executable,'-B','-c',code,str(R),str(os.getpid()),action],env=env,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=2)
      if result.returncode:raise ValueError('STRICT_PROBE_REJECTED')
      require(len(result.stdout)<=32768)
      return json.loads(result.stdout)
     def reject(name,change,restore):
      change();x.XSync(connection,False)
      try:observe();raise AssertionError('UNSAFE_ACCEPTED_'+name)
      except ValueError:report['cases'].append({'case':name,'status':'REJECTED'})
      finally:restore();x.XSync(connection,False)
     proof=observe();report['cases'].append({'case':'complete_dialog_signed_focus_proxy_shape_input','status':'PASS'})
     # An unchanged metadata observation must reproduce the same structural proof.
     x.XStoreName(connection,background,b'synthetic owned background');x.XSync(connection,False);require(observe()==proof)
     overlay=create(root,400,400,30,30,'synthetic overlay');x.XSync(connection,False)
     try:observe();raise AssertionError('OVERLAY_ACCEPTED')
     except ValueError:report['cases'].append({'case':'higher_root_overlay','status':'REJECTED'})
     x.XDestroyWindow(connection,overlay);x.XSync(connection,False)
     intercept=x.XCreateWindow(connection,dialog,60,60,60,60,0,0,2,None,0,None);x.XMapWindow(connection,intercept);x.XSync(connection,False)
     try:observe();raise AssertionError('INPUT_ONLY_ACCEPTED')
     except ValueError:report['cases'].append({'case':'input_only_interception','status':'REJECTED'})
     x.XDestroyWindow(connection,intercept);x.XSync(connection,False)
     reject('foreign_focus',lambda:x.XSetInputFocus(connection,background,1,0),lambda:x.XSetInputFocus(connection,proxy,1,0))
     # Restacking descendants changes bound ordered proof even if fields stay identical.
     lower=create(dialog,10,10,10,10,'synthetic nested one');upper=create(dialog,30,10,10,10,'synthetic nested two');x.XSync(connection,False)
     first=observe();x.XLowerWindow(connection,upper);x.XSync(connection,False);require(observe()!=first);report['cases'].append({'case':'descendant_restack_changes_proof','status':'PASS'})
     x.XDestroyWindow(connection,lower);x.XDestroyWindow(connection,upper);x.XSync(connection,False)
     # Actual ShapeInput coverage, not only QueryExtents.
     ext=C.CDLL('libXext.so.6')
     class Rectangle(C.Structure):_fields_=[('x',C.c_short),('y',C.c_short),('width',C.c_ushort),('height',C.c_ushort)]
     ext.XShapeCombineRectangles.argtypes=[ptr,u,i,i,i,C.POINTER(Rectangle),i,i,i];ext.XShapeCombineRectangles.restype=None
     rect=Rectangle(0,0,260,235);ext.XShapeCombineRectangles(connection,dialog,2,0,0,C.byref(rect),1,0,0);x.XSync(connection,False)
     try:observe();raise AssertionError('PARTIAL_SHAPE_ACCEPTED')
     except ValueError:report['cases'].append({'case':'nondefault_shape_input','status':'REJECTED'})
     report['status']='PASS';report['error']=None
    except BaseException as error:
     report['status']='FAIL'
     if isinstance(error,InterruptedError):report['error']='CANCELLED'
    finally:
     signal.alarm(0)
     # No potentially blocking Xlib roundtrip in cleanup. Process exit closes our client FD.
     if server is not None:
      try:
       if server.poll() is None:
        if fd is not None:signal.pidfd_send_signal(fd,signal.SIGTERM)
        else:server.terminate()  # Only this unreaped directly spawned child.
       try:server.wait(timeout=3)
       except subprocess.TimeoutExpired:
        if fd is not None:signal.pidfd_send_signal(fd,signal.SIGKILL)
        else:server.kill()
        server.wait(timeout=2)
       report['cleanup']='REAPED'
      except BaseException:report.update(status='FAIL',error='CLEANUP_UNVERIFIED',cleanup='UNVERIFIED')
     if fd is not None:os.close(fd)
     report['elapsed_milliseconds']=max(0,int((time.monotonic()-start)*1000));temp.cleanup()
     if report['cleanup']!='REAPED' and report['status']=='PASS':report.update(status='FAIL',error='CLEANUP_UNVERIFIED')
     publish(output,encode(report_document(report)))
    if report['status']!='PASS':raise SystemExit(1)

if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser();parser.add_argument('--report',type=Path,required=True);args=parser.parse_args();main(args.report)
