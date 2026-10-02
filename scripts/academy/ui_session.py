#!/usr/bin/env python3
"""同一 runner 的有限 UI 检查点；独立图像，不导出 profile 或秘密。"""
from __future__ import annotations
import argparse, hashlib, json, os, select, signal, stat, subprocess, sys, time, zipfile, re, shutil
from pathlib import Path
from safe_io import replace_regular
from go_environment import validated_go_environment
from display_diagnostic import capture as capture_display_diagnostic
from project_trust import checkpoint as trust_checkpoint, context as trust_context, ACTION as TRUST_ACTION
from ui_control import ACTIONS, EUA_SHA256, FIELDS, UI_BUDGET_SECONDS, strict_json, validate_control, atomic_json, checked_budget, read_ui_deadline


def put(path, value):
    atomic_json(path,value)

def exception_diagnostic(exc, operation):
    """Typed facts only: exception text can contain commands, paths or secrets."""
    name=type(exc).__name__
    if not re.fullmatch(r'[A-Za-z][A-Za-z0-9_]{0,63}',name):name='UnknownException'
    result={'operation':operation,'exception_type':name}
    if isinstance(exc,OSError) and type(exc.errno) is int:result['errno']=exc.errno
    codes={'OWNERSHIP_UNVERIFIED':'OWNERSHIP_UNVERIFIED',
           '进程元数据过大':'PROCESS_METADATA_LIMIT',
           '进程登记预算耗尽':'REGISTRATION_DEADLINE',
           '子进程登记预算耗尽':'REGISTRATION_DEADLINE',
           '自有子链枚举预算耗尽':'CHILD_ENUMERATION_BUDGET',
           '自有子链元数据过大':'CHILD_METADATA_LIMIT',
           '自有子链数量上限':'CHILD_COUNT_LIMIT',
           '已登记进程上限':'REGISTERED_COUNT_LIMIT',
           '已登记进程未全部退出':'REGISTERED_CLEANUP_INCOMPLETE',
           '当前运行取消':'CANCELLED',
           '原官方执行60分钟总预算耗尽':'OUTER_DEADLINE',
           '监督预算未初始化':'INITIALIZATION_DEADLINE'}
    result['code']=codes.get(exc.args[0] if exc.args and isinstance(exc.args[0],str) else '', 'UNCLASSIFIED_EXCEPTION')
    return result


def process_info(pid):
    base=Path(f'/proc/{pid}')
    data=(base/'stat').read_text()
    if len(data)>16384:raise ValueError('进程元数据过大')
    values=data.rsplit(')',1)[1].split()
    return {'pid':pid,'ppid':int(values[1]),'pgrp':int(values[2]),'session':int(values[3]),
            'start_time':values[19],'uid':base.stat().st_uid}


def start_time(pid):return process_info(pid)['start_time']


def live(fd):return not select.select([fd],[],[],0)[0]


def matching(meta,fd):
    try:return live(fd) and process_info(meta['pid'])==meta
    except (FileNotFoundError,ProcessLookupError):return False


def direct_candidates(parent,deadline):
    # 只读取已核验父进程的task/children；不读取全系统进程表。
    tasks=Path(f"/proc/{parent['pid']}/task")
    result=set();count=0
    for task in tasks.iterdir():
        count+=1
        if count>1024 or time.monotonic()>=deadline:raise RuntimeError('自有子链枚举预算耗尽')
        try:
            value=(task/'children').read_text()
            if len(value)>65536:raise RuntimeError('自有子链元数据过大')
            result.update(int(word) for word in value.split())
        except (FileNotFoundError,ProcessLookupError):continue
        if len(result)>512:raise RuntimeError('自有子链数量上限')
    return result


class Owned:
    """仅证明已登记集合；未登记/脱离子链的进程交fresh runner销毁。"""
    def __init__(self,deadline):
        # 构造不访问进程/文件；调用方须在Popen后立即进入try/finally。
        self.deadline=deadline;self.members={};self.root_registered=False
    def register_root(self,proc):
        # 这是本调用刚Popen且尚未poll/wait的直接孩子；未reap前其PID不能复用。
        fd=os.pidfd_open(proc.pid)
        try:
            before=process_info(proc.pid)
            if not live(fd) or before['ppid']!=os.getpid() or before['uid']!=os.getuid():
                raise RuntimeError('OWNERSHIP_UNVERIFIED')
            if process_info(proc.pid)!=before:raise RuntimeError('OWNERSHIP_UNVERIFIED')
            self.members[proc.pid]=(before,fd);self.root_registered=True
            return before
        except BaseException:
            os.close(fd);raise
    def scan(self):
        # 用当前父链发现候选，再用候选完整身份和父pidfd复核；陈旧children数字不授予归属。
        queue=list(self.members.values());seen=set()
        while queue:
            if time.monotonic()>=self.deadline:raise TimeoutError('进程登记预算耗尽')
            parent,parent_fd=queue.pop(0)
            if parent['pid'] in seen:continue
            seen.add(parent['pid'])
            if not matching(parent,parent_fd):continue
            try:candidates=direct_candidates(parent,self.deadline)
            except (FileNotFoundError,ProcessLookupError):continue
            for pid in candidates:
                if time.monotonic()>=self.deadline:raise TimeoutError('子进程登记预算耗尽')
                if len(self.members)>=512:raise RuntimeError('已登记进程上限')
                if pid in self.members:
                    meta,fd=self.members[pid]
                    if matching(meta,fd):queue.append((meta,fd))
                    continue
                fd=None
                try:
                    before=process_info(pid)
                    if before['ppid']!=parent['pid'] or before['uid']!=parent['uid']:continue
                    if int(before['start_time'])<int(parent['start_time']):continue
                    if before['session'] not in (parent['session'],pid):continue
                    if before['pgrp'] not in (parent['pgrp'],pid):continue
                    fd=os.pidfd_open(pid)
                    if not live(fd) or process_info(pid)!=before or not matching(parent,parent_fd):continue
                    self.members[pid]=(before,fd);queue.append((before,fd));fd=None
                except (FileNotFoundError,ProcessLookupError):continue
                finally:
                    if fd is not None:os.close(fd)
    def stop(self):
        # 不在清理阶段补收养；只signal已经可靠登记的pidfd。
        for sig,seconds in ((signal.SIGTERM,3),(signal.SIGKILL,2)):
            for _,fd in self.members.values():
                if live(fd):
                    try:signal.pidfd_send_signal(fd,sig)
                    except ProcessLookupError:pass
            end=time.monotonic()+seconds
            while time.monotonic()<end and any(live(fd) for _,fd in self.members.values()):time.sleep(.05)
        complete=all(not live(fd) for _,fd in self.members.values())
        for _,fd in self.members.values():os.close(fd)
        self.members.clear()
        if not self.root_registered:raise RuntimeError('OWNERSHIP_UNVERIFIED')
        if not complete:raise RuntimeError('已登记进程未全部退出')


def clean_env():
    names={'PATH','HOME','USER','LOGNAME','LANG','LC_ALL','LC_CTYPE','LANGUAGE','TZ','TERM',
           'TMPDIR','JAVA_HOME','CI','GITHUB_ACTIONS','GITHUB_WORKSPACE','DISPLAY','XAUTHORITY',
           'GITHUB_REPOSITORY','GITHUB_SHA','GITHUB_RUN_ID','GITHUB_RUN_ATTEMPT','RUNNER_TEMP','RUNNER_TRACKING_ID'}
    result={k:v for k,v in os.environ.items() if k in names}
    result.update(validated_go_environment())
    return result


def identity_alive(info):
    try:return start_time(info['pid'])==info['start_time']
    except (FileNotFoundError,ProcessLookupError):return False


def budget_record(owner,seconds):
    return {'monotonic_deadline':int(owner['start_time'])/os.sysconf('SC_CLK_TCK')+seconds,
            'budget_seconds':seconds,'owner':owner}


def read_outer_deadline(root):
    value=strict_json((root/'state.json').read_bytes())
    try:observed=process_info(value['owner']['pid'])
    except (FileNotFoundError,ProcessLookupError):
        if not (root/'result.json').exists():raise RuntimeError('预算拥有者消失且无终态')
        observed=value['owner']  # 已终态只读取结果，不再授予进程或动作运行时间。
    return checked_budget(value,3600,observed)


def worker(root,command):
    result={'schema_version':1,'status':'FAILED','exit_code':None,'cleanup_verified':None,
            'termination':'UNKNOWN','operation':'INITIALIZE'}
    owned=None;proc=None
    def stop_signal(*_):raise InterruptedError('当前运行取消')
    signal.signal(signal.SIGTERM,stop_signal);signal.signal(signal.SIGINT,stop_signal)
    try:
        initialization_deadline=time.monotonic()+2
        while not (root/'state.json').exists():
            if time.monotonic()>=initialization_deadline:raise RuntimeError('监督预算未初始化')
            time.sleep(.01)
        deadline=read_outer_deadline(root);owned=Owned(deadline)
        result['operation']='OPEN_WORKER_STREAMS'
        with (root/'worker.stdout.log').open('xb') as out,(root/'worker.stderr.log').open('xb') as err:
            result['operation']='SPAWN_CHILD'
            proc=subprocess.Popen(command,stdout=out,stderr=err,env=clean_env(),start_new_session=True)
            result['operation']='REGISTER_ROOT'
            owned.register_root(proc)
            while True:
                result['operation']='POLL_CHILD'
                if proc.poll() is not None:break
                result['operation']='SCAN_OWNED'
                owned.scan()
                result['operation']='CHECK_DEADLINE'
                if time.monotonic()>=deadline:raise TimeoutError('原官方执行60分钟总预算耗尽')
                time.sleep(.25)
            result['exit_code']=proc.returncode if type(proc.returncode) is int else None
            result['termination']='CHILD_EXIT';result['operation']='CHILD_EXIT_OBSERVED'
            if proc.returncode==0:result['status']='PASS'
    except BaseException as exc:
        result['termination']='SUPERVISOR_EXCEPTION';result['error']=type(exc).__name__
        result['error_details']=exception_diagnostic(exc,result['operation'])
    finally:
        result['registered_process_count']=len(owned.members) if owned is not None and isinstance(owned.members,dict) else None
        if proc is not None:
            try:owned.stop();result['cleanup_verified']=True;result['cleanup_scope']='REGISTERED_SET_ONLY'
            except Exception as exc:
                result['status']='FAILED';result['cleanup_verified']=False;result['cleanup_error']=type(exc).__name__
                result['cleanup_error_details']=exception_diagnostic(exc,'STOP_REGISTERED_SET')
        if proc:
            try:
                code=proc.wait(timeout=1);result['exit_code']=code if type(code) is int else None
            except subprocess.TimeoutExpired as exc:
                result['status']='FAILED';result['cleanup_verified']=False;result['cleanup_error']='OWNERSHIP_UNVERIFIED'
                result['cleanup_error_details']=exception_diagnostic(exc,'REAP_CHILD')
        put(root/'result.json',result)
    return 0 if result['status']=='PASS' else 1


def launch(root,command):
    root.mkdir();deadline=time.monotonic()+3600
    owned=Owned(deadline);proc=None;handed_off=False
    result={'schema_version':1,'status':'FAILED','operation':'SPAWN_SUPERVISOR','exit_code':None,'cleanup_verified':None}
    try:
        with (root/'supervisor.log').open('xb') as output:
            proc=subprocess.Popen([sys.executable,__file__,'worker','--root',str(root),'--',*command],
                                  stdout=output,stderr=subprocess.STDOUT,env=clean_env(),start_new_session=True)
            result['operation']='REGISTER_SUPERVISOR';meta=owned.register_root(proc)
            owner={key:meta[key] for key in ('pid','start_time','uid','session','pgrp')}
            result['operation']='WRITE_BUDGET';put(root/'supervisor.json',owner)
            put(root/'state.json',budget_record(owner,3600))
        result['operation']='AWAIT_STAGE_1';await_stage(root,1);handed_off=True
        result['status']='CHECKPOINT_REACHED_NOT_ACCEPTANCE'
    except BaseException as exc:
        result['error_details']=exception_diagnostic(exc,result['operation']);raise
    finally:
        if handed_off:
            for _,fd in owned.members.values():os.close(fd)
            owned.members.clear()
        elif proc is not None:
            try:owned.stop();result['cleanup_verified']=True;result['cleanup_scope']='REGISTERED_SET_ONLY'
            except BaseException as exc:
                result['cleanup_verified']=False;result['cleanup_error_details']=exception_diagnostic(exc,'STOP_REGISTERED_SET');raise
            finally:
                try:
                    code=proc.wait(timeout=1);result['exit_code']=code if type(code) is int else None
                except subprocess.TimeoutExpired:result['exit_code']=None
                put(root/'launch-result.json',result)
        if proc is None or handed_off:put(root/'launch-result.json',result)


def await_stage(root,stage):
    deadline=read_ui_deadline(root) if stage==4 else read_outer_deadline(root)
    # 首次还包含官方export，仍受其原600秒与原60分钟总界限，不延长。
    while time.monotonic()<deadline:
        if (root/f'stage-{stage}'/'request.json').is_file():return
        if (root/'result.json').exists():raise RuntimeError('官方进程在UI阶段前终止')
        if not identity_alive(json.loads((root/'supervisor.json').read_bytes())):raise RuntimeError('监督进程已经退出')
        time.sleep(.5)
    raise TimeoutError('原执行总预算耗尽')


def finish(root):
    deadline=read_outer_deadline(root)
    while time.monotonic()<deadline:
        path=root/'result.json'
        if path.is_file():
            result=json.loads(path.read_bytes())
            if result['status']!='PASS' or not result['cleanup_verified']:raise RuntimeError('官方命令或清理失败')
            return
        time.sleep(.5)
    raise TimeoutError('原执行总预算耗尽')


def _cleanup(root):
    path=root/'supervisor.json'
    if not path.exists():return 'NO_SUPERVISOR_IDENTITY'
    info=json.loads(path.read_bytes())
    def same():
        try:
            current=process_info(info['pid'])
            return all(current[key]==value for key,value in info.items())
        except (FileNotFoundError,ProcessLookupError):return False
    if not same():return 'SUPERVISOR_IDENTITY_NOT_LIVE'
    try:fd=os.pidfd_open(info['pid'])
    except ProcessLookupError:return 'SUPERVISOR_IDENTITY_NOT_LIVE'
    try:
        if not live(fd):return 'SUPERVISOR_EXIT_OBSERVED'
        if not same():raise RuntimeError('监督进程身份变化')
        signal.pidfd_send_signal(fd,signal.SIGTERM)
        if not select.select([fd],[],[],8)[0]:raise RuntimeError('监督进程未正常清理退出')
        return 'SUPERVISOR_EXIT_OBSERVED'
    finally:os.close(fd)

def cleanup(root):
    # The cleanup command can observe the supervisor only. Its child-set
    # cleanup verdict comes exclusively from worker result.json, never inferred.
    result={'schema_version':1,'status':'UNKNOWN','cleanup_verified':None,
            'cleanup_scope':'SUPERVISOR_ONLY','observation':'UNKNOWN'}
    try:
        result['observation']=_cleanup(root);result['status']='COMMAND_COMPLETED_NOT_CHILD_CLEANUP_PROOF'
    except BaseException as exc:
        result['status']='FAILED';result['error_details']=exception_diagnostic(exc,'CLEANUP_SUPERVISOR');raise
    finally:
        replace_regular(root/'cleanup-result.json',(json.dumps(result,ensure_ascii=False,indent=2)+'\n').encode())


def server_session(root,command):
    """监督正常xvfb-run，记录直接孩子身份；不替代或放宽X权限。"""
    deadline=read_outer_deadline(root)
    owned=Owned(deadline);proc=None
    def cancel(*_):raise InterruptedError('本次显示器监督取消')
    signal.signal(signal.SIGTERM,cancel);signal.signal(signal.SIGINT,cancel)
    try:
        proc=subprocess.Popen(command,env=os.environ.copy(),start_new_session=True)
        meta=owned.register_root(proc)
        put(root/'wrapper.json',meta)
        while proc.poll() is None:
            owned.scan()
            if time.monotonic()>=deadline:raise TimeoutError('原执行总预算耗尽')
            time.sleep(.25)
        return proc.returncode
    finally:
        if proc is not None:
            try:owned.stop()
            finally:
                try:proc.wait(timeout=1)
                except subprocess.TimeoutExpired:pass  # 不用数字PID兜底；异常仍由owned.stop抛出


def file_identity(path,kind):
    info=path.lstat()
    if info.st_uid!=os.getuid() or not kind(info.st_mode):raise RuntimeError('显示器文件归属不符')
    return {'dev':info.st_dev,'ino':info.st_ino,'uid':info.st_uid}


class DisplayIdentity:
    def __init__(self):self.handles={};self.metadata=None
    def establish(self,root,ide_meta,ide_fd,deadline):
        while not (root/'wrapper.json').exists():
            if time.monotonic()>=deadline:raise TimeoutError('显示器身份等待超时')
            time.sleep(.05)
        wrapper=json.loads((root/'wrapper.json').read_bytes())
        if wrapper['pid']!=os.getppid():raise RuntimeError('不是本次xvfb-run父进程')
        fd=os.pidfd_open(wrapper['pid']);self.handles['wrapper']=(wrapper,fd)
        if not matching(wrapper,fd):raise RuntimeError('显示器父进程身份变化')
        display=os.environ.get('DISPLAY','')
        if not re.fullmatch(r':[0-9]{1,4}',display):raise RuntimeError('显示器编号不符')
        authority=Path(os.environ['XAUTHORITY'])
        socket=Path('/tmp/.X11-unix')/('X'+display[1:])
        self.authority=authority;self.socket=socket
        auth_identity=file_identity(authority,stat.S_ISREG)
        socket_identity=file_identity(socket,stat.S_ISSOCK)
        server=None
        for pid in direct_candidates(wrapper,deadline):
            handle=None
            try:
                before=process_info(pid)
                if before['ppid']!=wrapper['pid'] or before['uid']!=wrapper['uid']:continue
                if before['session']!=wrapper['session'] or before['pgrp']!=wrapper['pgrp']:continue
                handle=os.pidfd_open(pid)
                if not matching(before,handle) or not matching(wrapper,fd):continue
                executable=Path(f'/proc/{pid}/exe').resolve()
                args=Path(f'/proc/{pid}/cmdline').read_bytes().split(b'\0')
                if executable!=Path(shutil.which('Xvfb')).resolve() or display.encode() not in args:continue
                index=args.index(b'-auth') if b'-auth' in args else -1
                if index<0 or args[index+1]!=os.fsencode(authority):continue
                if not matching(before,handle) or not matching(wrapper,fd):continue
                if server is not None:raise RuntimeError('显示器server不是唯一')
                server=(before,handle);self.handles['server']=server;handle=None
            except (FileNotFoundError,ProcessLookupError):continue
            finally:
                if handle is not None:os.close(handle)
        if server is None:raise RuntimeError('本次owned Xvfb身份不可证明')
        self.handles['ide']=(ide_meta,os.dup(ide_fd))
        self.metadata={'display':display,'wrapper':wrapper,'server':server[0],'ide':ide_meta,
                       'authority':auth_identity,'socket':socket_identity}
        self.verify()
        # 内部只含本次owned进程/文件元数据，供Java在同一截图/点击调用内核对继承的pidfd。
        props={'display':display,'socket.path':str(socket),'authority.path':str(authority)}
        for kind,(meta,handle) in self.handles.items():
            props.update({kind+'.'+key:str(value) for key,value in meta.items()});props[kind+'.fd']=str(handle)
        for kind,identity in [('socket',socket_identity),('authority',auth_identity)]:
            props.update({kind+'.'+key:str(value) for key,value in identity.items()})
        self.binding=root/'display-binding.properties'
        with self.binding.open('x') as stream:stream.write(''.join(key+'='+value+'\n' for key,value in sorted(props.items())))
    def verify(self):
        if self.metadata is None:raise RuntimeError('显示器身份未建立')
        if os.environ.get('DISPLAY')!=self.metadata['display']:raise RuntimeError('显示器编号变化')
        for meta,fd in self.handles.values():
            if not matching(meta,fd):raise RuntimeError('显示器或IDE身份变化')
        if file_identity(self.authority,stat.S_ISREG)!=self.metadata['authority']:raise RuntimeError('Xauthority文件身份变化')
        if file_identity(self.socket,stat.S_ISSOCK)!=self.metadata['socket']:raise RuntimeError('显示器socket身份变化')
    def close(self):
        for _,fd in self.handles.values():os.close(fd)
        self.handles.clear()


def optional_display_diagnostic(root,proc,screen,identity,ui_deadline):
    try:return capture_display_diagnostic(root,proc,screen,identity,ui_deadline)
    except InterruptedError:raise  # Preserve the existing cancellation handler/cleanup path.
    except Exception:return None  # Optional I/O cannot grant acceptance or extend execution.


def display_session(root,idea,command):
    """由原 capture 在自有 xvfb-run 内调用；原2700秒包含全部UI等待。"""
    # 固定官方配置元数据只核实际内置协议，不更改vendor jar。
    with zipfile.ZipFile(idea/'lib/intellij.platform.ide.impl.jar') as jar:
        info=jar.getinfo('eua.html')
        if info.file_size>512*1024:raise ValueError('内置协议尺寸不符')
        if hashlib.sha256(jar.read(info)).hexdigest()!=EUA_SHA256:raise ValueError('内置协议不符')
    helper=Path(__file__).with_name('probes')/'AgreementUi.java'
    java=str(idea/'jbr/bin/java')
    def screen(action,destination,expected=None,receipt=None):
        identity.verify()
        args=[java,'-Xmx96m','-XX:ActiveProcessorCount=1',f'-Duser.home={os.environ["HOME"]}',str(helper),action,str(destination)]
        if expected is not None:args.extend([expected,str(receipt)])
        if action==TRUST_ACTION:
            args.extend([sys.executable,str(Path(__file__).with_name('project_trust.py')),
                         str(root/'stage-4/window-identity.json'),str(root)])
        args.append(str(identity.binding))
        subprocess.run(args,check=True,timeout=min(15,max(.1,ui_deadline-time.monotonic())),env=clean_env(),
                       pass_fds=tuple(fd for _,fd in identity.handles.values()))
        identity.verify()
    started=time.monotonic();ui_deadline=started+UI_BUDGET_SECONDS
    owned=Owned(started+2700);identity=DisplayIdentity();proc=None
    def terminate(*_):raise InterruptedError('本次UI会话取消')
    signal.signal(signal.SIGTERM,terminate);signal.signal(signal.SIGINT,terminate)
    try:
        trust_context(root,command,idea)  # Exact current100 source/archive/CLI target; never a generic trust grant.
        proc=subprocess.Popen(command,env=os.environ.copy(),start_new_session=True)
        ide_meta=owned.register_root(proc)
        record=budget_record(ide_meta,UI_BUDGET_SECONDS);ui_deadline=record['monotonic_deadline']
        put(root/'ui-deadline.json',record)
        identity.establish(root,ide_meta,owned.members[proc.pid][1],ui_deadline)
        # 仅给正常窗口初始化留时间；这不是正确状态判定，真正动作必须经本次画面人工核对。
        while time.monotonic()<started+30:
            if proc.poll() is not None:raise RuntimeError('IDE在首张图前退出')
            owned.scan();time.sleep(.25)
        for stage,action in ACTIONS.items():
            stage_dir=root/f'stage-{stage}';stage_dir.mkdir()
            before=stage_dir/'before.png';screen('SNAPSHOT',before)
            put(stage_dir/'review-target.json',{'action':action,'fixed_target':{1:[382,612],2:[879,651],3:[663,651]}[stage],
                'screen':[1280,900],'requirement':'审图时确认固定目标位于对应控件内；不同布局不得批准'})
            expected={'schema':1,'run_id':os.environ['GITHUB_RUN_ID'],'run_attempt':os.environ['GITHUB_RUN_ATTEMPT'],
                      'stage':stage,'action':action,'eua_sha256':EUA_SHA256,
                      'screenshot_sha256':hashlib.sha256(before.read_bytes()).hexdigest()}
            identity.verify();put(stage_dir/'display-identity.json',identity.metadata)
            put(stage_dir/'request.json',expected)
            while not (stage_dir/'control.json').exists():
                if proc.poll() is not None:raise RuntimeError('IDE已退出')
                if time.monotonic()>=ui_deadline:raise TimeoutError('900秒UI总预算耗尽')
                owned.scan();time.sleep(.2)
            validate_control(strict_json((stage_dir/'control.json').read_bytes()),expected)
            if time.monotonic()>=ui_deadline or proc.poll() is not None:raise RuntimeError('动作已过期')
            screen(action,stage_dir/'after.png',expected['screenshot_sha256'],stage_dir/'performed.txt')
            put(stage_dir/'receipt.json',{**expected,'after_sha256':hashlib.sha256((stage_dir/'after.png').read_bytes()).hexdigest(),
                                         'status':'UI_ACTION_PERFORMED_NOT_ACCEPTANCE'})
        put(root/'ui-complete.json',{'status':'NORMAL_UI_COMPLETED_NOT_COURSE_ACCEPTANCE'})
        diagnostic_due=time.monotonic()+30;diagnostic_done=False
        while proc.poll() is None:
            owned.scan()
            if not diagnostic_done and time.monotonic()>=diagnostic_due:
                diagnostic_done=True
                optional_display_diagnostic(root,proc,screen,identity,ui_deadline)
                trust_checkpoint(root,proc,screen,identity,owned,ui_deadline,command,idea,clean_env())
            time.sleep(.25)
        if not diagnostic_done:
            optional_display_diagnostic(root,proc,screen,identity,ui_deadline)
        return proc.returncode
    finally:
        identity.close()
        if proc is not None:
            try:owned.stop()
            finally:
                try:proc.wait(timeout=1)
                except subprocess.TimeoutExpired:pass


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('mode',choices=['launch','worker','await','complete','trust-complete','finish','cleanup','display','server'])
    p.add_argument('--root',type=Path,required=True);p.add_argument('--stage',type=int,choices=[1,2,3,4])
    p.add_argument('--idea',type=Path)
    argv=sys.argv[1:];index=argv.index('--') if '--' in argv else len(argv)
    a=p.parse_args(argv[:index]);command=argv[index+1:]
    if a.mode=='launch':launch(a.root,command)
    elif a.mode=='worker':sys.exit(worker(a.root,command))
    elif a.mode=='await':await_stage(a.root,a.stage)
    elif a.mode=='complete':
        deadline=read_ui_deadline(a.root)
        while not (a.root/'ui-complete.json').exists():
            if time.monotonic()>=deadline or (a.root/'result.json').exists():raise RuntimeError('UI未完成')
            time.sleep(.2)
    elif a.mode=='trust-complete':
        deadline=read_ui_deadline(a.root)
        while not (a.root/'stage-4/receipt.json').exists():
            if time.monotonic()>=deadline or (a.root/'result.json').exists():raise RuntimeError('本次项目UI信任未完成')
            time.sleep(.2)
    elif a.mode=='finish':finish(a.root)
    elif a.mode=='cleanup':cleanup(a.root)
    elif a.mode=='server':sys.exit(server_session(a.root,command))
    else:sys.exit(display_session(a.root,a.idea,command))
