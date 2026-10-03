"""One normal profile preparation/restart, then a distinct fresh official validation."""
import hashlib
import ctypes
import json
import os
from pathlib import Path
import signal
import stat
import subprocess
import sys
import time
import zipfile
from display_diagnostic import encode, json_read, publish
from safe_io import read_regular, new_directory, directory_fd, write_new
from restart_family import Family, Cancellation, FamilyError, CODES as FAMILY_CODES, info, stable, Child
import profile_control as control
import project_trust as trust
import plugin_agreement as plugin
from ui_control import ACTIONS, EUA_SHA256, UI_BUDGET_SECONDS, validate_control, strict_json
from post_trust_diagnostic import bind_budget_owner

PROTOCOL=control.PROTOCOL
RESULT='restart-result.json'
RESULT_FIELDS={'schema','protocol','status','operation','error_code','detail_code','detail_step','cancelled','phase2_started','phase2_exit',
               'preparation_cleanup','validation_cleanup','profile_verified','restart_context_verified',
               'validation_context_verified','restart_provenance','registered_processes','course_acceptance',
               'exception_class','agreement_failure'}
OPERATIONS={'INITIALIZE','PREPARATION','AGREEMENTS','PROFILE_PREVIEW','PROFILE_CLICK','INSTALL_COMPLETION','TERMINAL_ACK','RESTART',
            'RESTART_REVIEW','PREPARATION_CLEANUP','FRESH_VALIDATION','VALIDATION_REVIEW','VALIDATION_WAIT','FINAL_CLEANUP','COMPLETED'}
ERRORS={'NONE','FAMILY_ERROR','PROFILE_ERROR','CANCELLED','TIMEOUT','BOUNDARY_ERROR','UNEXPECTED_ERROR'}


def require(ok):
    if not ok:raise ValueError('RESTART_SESSION_INVALID')


def validate_result(value):
    require(type(value) is dict and set(value)==RESULT_FIELDS)
    require(type(value['schema']) is int and value['schema']==1 and value['protocol']==PROTOCOL)
    require(value['status'] in ('FAILED','FRESH_VALIDATION_EXITED_NOT_ACCEPTANCE') and value['operation'] in OPERATIONS and value['error_code'] in ERRORS)
    from apparmor_profile import CODES as PROFILE_CODES, STEPS as PROFILE_STEPS
    require(type(value['detail_code']) is str and value['detail_code'] in FAMILY_CODES | PROFILE_CODES | {'NONE','UNKNOWN'})
    require(type(value['detail_step']) is str and value['detail_step'] in PROFILE_STEPS | {'NONE','FAMILY','UNKNOWN'})
    require(value['course_acceptance']=='NOT_RUN')
    require(type(value['exception_class']) is str and value['exception_class'] in plugin.EXCEPTION_CLASSES)
    if value['agreement_failure'] is not None:
        plugin.checkpoint_failure_document(value['agreement_failure'])
        require(value['status']=='FAILED' and value['exception_class']==value['agreement_failure']['exception_class'])
    for key in ('cancelled','phase2_started','profile_verified','restart_context_verified','validation_context_verified'):
        require(type(value[key]) is bool)
    require(value['restart_provenance'] in ('NONE','OBSERVED_RESTARTER_EXEC','CLOSED_FAMILY_ADOPTED_EXEC'))
    for key in ('preparation_cleanup','validation_cleanup'):require(value[key] is None or type(value[key]) is bool)
    require(value['phase2_exit'] is None or type(value['phase2_exit']) is int and -127<=value['phase2_exit']<=255)
    require(type(value['registered_processes']) is int and 0<=value['registered_processes']<=512)
    if value['status']=='FRESH_VALIDATION_EXITED_NOT_ACCEPTANCE':
        require(value['phase2_exit']==0 and type(value['phase2_exit']) is int and not value['cancelled']
            and value['preparation_cleanup'] is True and value['validation_cleanup'] is True
            and all(value[k] for k in ('phase2_started','profile_verified','restart_context_verified','validation_context_verified'))
            and value['restart_provenance']!='NONE'
            and value['error_code']=='NONE' and value['operation']=='COMPLETED'
            and value['exception_class']=='NONE' and value['agreement_failure'] is None)
    return value


def checked_rename(source,destination):
    """Preserve only exact current-run paths, with no links or replacement."""
    with directory_fd(source.parent) as src, directory_fd(destination.parent) as dst:
        st=os.stat(source.name,dir_fd=src,follow_symlinks=False)
        require(st.st_uid==os.getuid() and (stat.S_ISREG(st.st_mode) or stat.S_ISDIR(st.st_mode)))
        try:os.stat(destination.name,dir_fd=dst,follow_symlinks=False)
        except FileNotFoundError:pass
        else:raise ValueError('PREPARATION_DESTINATION_OCCUPIED')
        libc=ctypes.CDLL(None,use_errno=True)
        rename=getattr(libc,'renameat2',None);require(rename is not None)
        rename.argtypes=[ctypes.c_int,ctypes.c_char_p,ctypes.c_int,ctypes.c_char_p,ctypes.c_uint]
        rename.restype=ctypes.c_int
        if rename(src,os.fsencode(source.name),dst,os.fsencode(destination.name),1)!=0:
            raise OSError(ctypes.get_errno(),'PREPARATION_RENAME_FAILED')


def fresh_validation_layout(root):
    """Only config/home naturally written in P1 survive; no acceptance flags are edited."""
    run,project,archive,*_=trust.paths(root)
    saved=run/'preparation-artifacts';new_directory(saved)
    checked_rename(project,saved/'validation')
    old_profile=run/'validate-profile'
    for name in ('system','log','tmp'):
        checked_rename(old_profile/name,saved/name);new_directory(old_profile/name)
    report=run/'evidence/official-validation.json'
    if report.exists() or report.is_symlink():checked_rename(report,saved/'official-validation.json')
    gradle=run/'evidence/gradle-jvm.jsonl'
    if gradle.exists() or gradle.is_symlink():
        raw=read_regular(gradle,limit=4*1024*1024)
        rows=[json_read(line) for line in raw.splitlines()]
        for row in rows:
            require(type(row) is dict and set(row)=={'java_version','java_home','gradle_version','root'} and all(type(v) is str and len(v)<=4096 for v in row.values()))
        kept=[row for row in rows if row['root']==str(run/'student')]
        require(kept)
        checked_rename(gradle,saved/'gradle-jvm.jsonl')
        write_new(gradle,b''.join(encode(row) for row in kept))
    # Existing outer report path and exact project target remain fresh. The
    # student-import JVM receipt is intentionally retained as export evidence.
    require(not project.exists() and not report.exists())
    return {'profile_reuse':'NATURAL_CURRENT_RUN_CONFIG_HOME_ONLY','new_volatile_directories':3,
            'preparation_preserved':True,'fresh_project':True,'fresh_report':True}


def display_session(root,idea,command):
    # Called in the same process as the previous display_session: os.getppid()
    # is still the real xvfb-run wrapper. No new display parent is substituted.
    import ui_session as ui
    import apparmor_profile as profile
    result={'schema':1,'protocol':PROTOCOL,'status':'FAILED','operation':'INITIALIZE','error_code':'NONE','detail_code':'NONE','detail_step':'NONE',
            'cancelled':False,'phase2_started':False,'phase2_exit':None,'preparation_cleanup':None,
            'validation_cleanup':None,'profile_verified':False,'restart_context_verified':False,
            'validation_context_verified':False,'restart_provenance':'NONE','registered_processes':0,'course_acceptance':'NOT_RUN',
            'exception_class':'NONE','agreement_failure':None}
    agreement_progress={}
    family=None;identity=None;current=None;cancellation=Cancellation();installed=None;terminal=None
    def cancel(*_):
        cancellation.set('SIGNAL_CANCELLED')
        if not (root/'cancelled.json').exists():
            try:publish(root/'cancelled.json',encode({'schema':1,'cancelled':True}))
            except Exception:pass
        raise InterruptedError('RESTART_SESSION_CANCELLED')
    signal.signal(signal.SIGTERM,cancel);signal.signal(signal.SIGINT,cancel)
    deadline=None;ui_deadline=None
    environment=os.environ.copy();helper_env=ui.clean_env()
    helper=Path(__file__).with_name('probes')/'AgreementUi.java'
    java=str(idea/'jbr/bin/java')
    def screen(action,destination,expected=None,receipt=None,diagnostic_deadline=None,approved=None):
        family.check();identity.verify()
        args=[java,'-Xmx96m','-XX:ActiveProcessorCount=1',f'-Duser.home={environment["HOME"]}',str(helper),action,str(destination)]
        if expected is not None:args.extend([expected,str(receipt)])
        if action==trust.ACTION:args.extend([sys.executable,str(Path(__file__).with_name('project_trust.py')),str(root/'stage-4/window-identity.json'),str(root)])
        if action in plugin.ACTIONS.values():
            stage=next(k for k,v in plugin.ACTIONS.items() if v==action)
            args.extend([sys.executable,str(Path(__file__).with_name('plugin_agreement.py')),str(root/f'stage-{stage}/window-identity.json'),str(root)])
        if action in control.ACTIONS.values():
            require(action in (control.ACTIONS[7],control.ACTIONS[8],control.ACTIONS[9]) and approved is not None)
            stage=approved['stage'];require(approved['action']==action)
            args.extend([sys.executable,str(Path(__file__).with_name('profile_control.py')),str(root/f'stage-{stage}/request.json'),str(root)])
            if stage in (7,8):args.extend([str(n) for n in approved['target']['point']])
        terminal_screen=destination.parent==root/'stage-9'
        binding=control.binding_for(root,9) if terminal_screen else identity.binding
        handles=[fd for _,fd in identity.handles.values()]
        if terminal_screen:
            require(terminal is not None and family.verify_terminal_helpers(terminal))
            handles.append(family.members[terminal.key]['fd'])
        args.append(str(binding))
        family.run(args,check=True,timeout=ui.snapshot_timeout(ui_deadline,diagnostic_deadline),env=helper_env,
                   pass_fds=tuple(handles))
        family.check()
        if action not in (control.ACTIONS[8],control.ACTIONS[9]):identity.verify()
    def bind(child,epoch):
        nonlocal identity
        family.check();family.tick()
        item=family.members[child.key];require(not item['terminal'] and item['fd'] is not None)
        meta=ui.process_info(child.pid)
        require(stable({**meta,'state':'R'})==stable(item['meta']))
        if identity is not None:identity.close()
        folder=root
        if epoch:
            folder=root/f'epoch-{epoch}';new_directory(folder)
            publish(folder/'wrapper.json',read_regular(root/'wrapper.json',limit=4096))
        identity=ui.DisplayIdentity();identity.establish(folder,meta,item['fd'],ui_deadline)
    def wait_window(child):
        end=min(ui_deadline,time.monotonic()+30)
        while time.monotonic()<end:
            family.check();require(child.poll() is None);time.sleep(.1)
        family.check();require(time.monotonic()<ui_deadline and child.poll() is None)
    try:
        started=time.monotonic();deadline=min(started+2700,ui.read_outer_deadline(root))
        owner=ui.process_info(os.getpid());ui_record=ui.budget_record(owner,UI_BUDGET_SECONDS)
        ui_deadline=ui_record['monotonic_deadline']
        with zipfile.ZipFile(idea/'lib/intellij.platform.ide.impl.jar') as jar:
            item=jar.getinfo('eua.html');require(item.file_size<=512*1024 and hashlib.sha256(jar.read(item)).hexdigest()==EUA_SHA256)
        trust.context(root,command,idea)
        ui.put(root/'ui-deadline.json',ui_record)
        bind_budget_owner(root)
        family=Family(deadline,cancellation)
        result['operation']='PREPARATION'
        current=family.spawn(command,environment,role='PREPARATION_IDE');bind(current,0);wait_window(current)
        result['operation']='AGREEMENTS'
        for stage,action in ACTIONS.items():
            folder=root/f'stage-{stage}';new_directory(folder)
            screen('SNAPSHOT',folder/'before.png')
            ui.put(folder/'review-target.json',{'action':action,'fixed_target':{1:[382,612],2:[879,651],3:[663,651]}[stage],
                    'screen':[1280,900],'requirement':'审图确认目标是本次限定控件；不同画面不得批准'})
            expected={'schema':1,'run_id':os.environ['GITHUB_RUN_ID'],'run_attempt':os.environ['GITHUB_RUN_ATTEMPT'],
                      'stage':stage,'action':action,'eua_sha256':EUA_SHA256,'screenshot_sha256':hashlib.sha256(read_regular(folder/'before.png',limit=2*1024*1024)).hexdigest()}
            identity.verify();ui.put(folder/'display-identity.json',identity.metadata);ui.put(folder/'request.json',expected)
            while not (folder/'control.json').exists():
                family.check();require(time.monotonic()<ui_deadline and current.poll() is None);time.sleep(.2)
            validate_control(strict_json(read_regular(folder/'control.json',limit=4096)),expected)
            screen(action,folder/'after.png',expected['screenshot_sha256'],folder/'performed.txt')
            ui.put(folder/'receipt.json',{**expected,'after_sha256':hashlib.sha256(read_regular(folder/'after.png',limit=2*1024*1024)).hexdigest(),
                                         'status':'UI_ACTION_PERFORMED_NOT_ACCEPTANCE'})
        ui.put(root/'ui-complete.json',{'status':'NORMAL_UI_COMPLETED_NOT_COURSE_ACCEPTANCE'})
        wait_window(current)
        ui.optional_display_diagnostic(root,current,screen,identity,ui_deadline)
        trust.checkpoint(root,current,screen,identity,family,ui_deadline,command,idea,helper_env,runner=family.run)
        observer=ui.PostTrustObserver(root,identity,ui_deadline)
        while not observer.done:
            family.check();require(current.poll() is None);observer.tick(current,screen,identity);time.sleep(.2)
        for stage in (5,6):
            plugin.checkpoint(root,stage,current,screen,identity,family,ui_deadline,command,idea,helper_env,runner=family.run,progress=agreement_progress)
        result['operation']='PROFILE_PREVIEW'
        identity.verify();executable=Path(os.readlink(f'/proc/{current.pid}/exe'))
        proposal=profile.prepare(executable,idea,runner=family.run,env=environment);identity.verify()
        # This normal-UI contract supports the reviewed non-root terminal route.
        # A different provider is a visible support limit, never an alternate installer.
        require(proposal['parser']['route']=='TERMINAL_SUDO')
        publish(root/'profile-candidate.json',encode(proposal))
        family.configure_install_helpers(proposal['parser']['expected_helpers'],current)
        family.configure_restart_images(idea/'bin/restarter',executable,idea/'bin/idea')
        control.checkpoint(root,7,current,screen,identity,family,ui_deadline,helper_env)
        result['operation']='PROFILE_CLICK'
        control.checkpoint(root,8,current,screen,identity,family,ui_deadline,helper_env)
        result['operation']='INSTALL_COMPLETION'
        completion_end=min(ui_deadline,deadline,time.monotonic()+60)
        while True:
            family.check();require(time.monotonic()<completion_end and current.poll() is None)
            terminal=family.terminal_child()
            if terminal is not None and family.verify_terminal_helpers(terminal):
                try:
                    installed=profile.verify_installed(proposal,env=environment)
                except profile.ProfileError as exc:
                    # A terminal may map before its installer creates the profile.
                    # Retry only bounded read-only absence/incomplete-byte observations.
                    if exc.code not in ('FILE_UNKNOWN','INSTALLED_MISMATCH'):raise
                else:
                    require(installed.get('status')=='INSTALLED_VERIFIED' and type(installed.get('exact_name_count')) is int and installed['exact_name_count']==1)
                    break
            time.sleep(.05)
        result['profile_verified']=True;result['operation']='TERMINAL_ACK'
        control.checkpoint(root,9,current,screen,identity,family,ui_deadline,helper_env,terminal=terminal)
        # Only the acknowledged normal terminal completion permits vendor restart.
        # Discard the old GUI epoch; the fresh replacement gets a new binding.
        identity.close();identity=None
        result['operation']='RESTART'
        while True:
            family.check();require(time.monotonic()<ui_deadline)
            replacement=family.replacement()
            if replacement is not None:break
            time.sleep(.01)
        installed=profile.verify_installed(proposal,env=environment)
        require(installed.get('status')=='INSTALLED_VERIFIED' and type(installed.get('exact_name_count')) is int and installed['exact_name_count']==1)
        result['profile_verified']=True
        family.check();active_context=profile.verify_context(replacement.pid,executable);family.check()
        result['restart_context_verified']=True
        current=replacement;bind(current,1)
        publish(root/'epoch-1/apparmor-context.json',encode(control.context_document({**trust.context(root),
            'schema':1,'epoch':1,'pid':current.pid,'start_time':ui.process_info(current.pid)['start_time'],**active_context})))
        wait_window(current)
        result['operation']='RESTART_REVIEW'
        control.checkpoint(root,10,current,screen,identity,family,ui_deadline,helper_env)
        family.verify_replacement(current);result['restart_provenance']=family.restart_provenance();family.permit_normal_close(current)
        result['operation']='PREPARATION_CLEANUP'
        identity.close();identity=None
        # Vendor restart saved the original IDE configuration. This bounded
        # TERM/KILL close is not a second GUI Exit or proof of another config
        # flush; fresh P2 must prove its own behavior with that honest limitation.
        family.close_phase();result['preparation_cleanup']=True
        family.check();layout=fresh_validation_layout(root);publish(root/'phase-layout.json',encode(layout))
        family.begin_validation();family.check()
        result['operation']='FRESH_VALIDATION';result['phase2_started']=True
        current=family.spawn(command,environment,role='VALIDATION_IDE');bind(current,2);wait_window(current)
        identity.verify();installed=profile.verify_installed(proposal,env=environment)
        require(installed.get('status')=='INSTALLED_VERIFIED' and type(installed.get('exact_name_count')) is int and installed['exact_name_count']==1)
        active_context=profile.verify_context(current.pid,executable);identity.verify();result['validation_context_verified']=True
        publish(root/'epoch-2/apparmor-context.json',encode(control.context_document({**trust.context(root),
            'schema':1,'epoch':2,'pid':current.pid,'start_time':ui.process_info(current.pid)['start_time'],**active_context})))
        result['operation']='VALIDATION_REVIEW'
        control.checkpoint(root,11,current,screen,identity,family,ui_deadline,helper_env)
        result['operation']='VALIDATION_WAIT'
        while current.poll() is None:family.check();time.sleep(.1)
        result['phase2_exit']=current.returncode
        require(type(current.returncode) is int and current.returncode==0)
    except BaseException as exc:
        cancellation.set('SESSION_FAILED')
        result['exception_class']=plugin.exception_class(exc)
        if agreement_progress:
            result['agreement_failure']=plugin.checkpoint_failure(agreement_progress,exc)
        detail=getattr(exc,'code','UNKNOWN')
        result['detail_code']=detail if type(detail) is str and detail in FAMILY_CODES | profile.CODES else 'UNKNOWN'
        step=getattr(exc,'step','UNKNOWN')
        result['detail_step']='FAMILY' if isinstance(exc,FamilyError) else step if type(step) is str and step in profile.STEPS else 'UNKNOWN'
        result['error_code']=('CANCELLED' if isinstance(exc,InterruptedError) else 'TIMEOUT' if isinstance(exc,(TimeoutError,subprocess.TimeoutExpired))
                              else 'FAMILY_ERROR' if isinstance(exc,FamilyError) else 'PROFILE_ERROR' if type(exc).__name__=='ProfileError'
                              else 'BOUNDARY_ERROR' if isinstance(exc,(ValueError,OSError)) else 'UNEXPECTED_ERROR')
    finally:
        if identity is not None:identity.close()
        if family is not None:
            result['registered_processes']=len(family.members)
            try:
                family.close()
                if result['phase2_started']:result['validation_cleanup']=True
                elif result['preparation_cleanup'] is None:result['preparation_cleanup']=True
            except BaseException:
                cancellation.set('CLEANUP_FAILED')
                if result['phase2_started']:result['validation_cleanup']=False
                else:result['preparation_cleanup']=False
                result['error_code']='FAMILY_ERROR';result['detail_code']='FAMILY_CLEANUP_INCOMPLETE';result['detail_step']='FAMILY'
            result['registered_processes']=len(family.members)
        result['cancelled']=cancellation.cancelled
        if (not result['cancelled'] and result['phase2_exit']==0 and result['phase2_started']
                and result['preparation_cleanup'] is True and result['validation_cleanup'] is True):
            result['operation']='COMPLETED';result['status']='FRESH_VALIDATION_EXITED_NOT_ACCEPTANCE'
        publish(root/RESULT,encode(validate_result(result)))
    return 0 if result['status']=='FRESH_VALIDATION_EXITED_NOT_ACCEPTANCE' else 1


def collect(root):
    value=validate_result(json_read(read_regular(root/RESULT,limit=8192)))
    diagnostic=value['agreement_failure']
    if diagnostic is not None and diagnostic['context'] is not None:
        require(diagnostic['context']==trust.context(root))
    return encode(value)
