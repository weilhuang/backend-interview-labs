"""Fresh normal-GUI profile controls; no installer, privilege command, or policy write."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time
from display_diagnostic import clean_png, digest, encode, json_read, publish
from safe_io import read_regular, new_directory
from ui_control import read_ui_budget, read_ui_deadline, fetch_control
import project_trust as trust
import plugin_agreement as plugin
import profile_window as window

ACTIONS={7:'ENABLE_BROWSER_OPTIONS',8:'INSTALL_SCOPED_APPARMOR_PROFILE',
         9:'ACK_VENDOR_INSTALL_COMPLETION',10:'REVIEW_RESTARTED_IDE',11:'REVIEW_FRESH_VALIDATION_IDE'}
PROTOCOL='SCOPED_PROFILE_TERMINAL_ACK_AND_FRESH_VALIDATION_V2'
FIELDS=trust.CONTEXT_FIELDS|{'schema','stage','action','protocol','terminal_stage','epoch',
    'screenshot_sha256','display_binding_sha256','windows','preceding_receipt_sha256',
    'candidate_sha256','profile_evidence_sha256','active_context_sha256','terminal_identity','installed_profile_sha256'}


def require(ok):
    if not ok:raise ValueError('PROFILE_CONTROL_INVALID')


def stage_number(stage):
    require(type(stage) is int and stage in ACTIONS);return stage


def review(stage):
    stage_number(stage)
    if stage==7:return {'dialog':'EMBEDDED_BROWSER_SUSPENDED','button':'ENABLE_BROWSER','disable_sandbox':False,'authentication_dialog':False}
    if stage==8:return {'dialog':'ENABLE_EMBEDDED_BROWSER','button':'INSTALL_PROFILE','scope':'CURRENT_OFFICIAL_EXECUTABLE_ONLY',
                        'disable_sandbox':False,'authentication_dialog':False}
    if stage==9:return {'dialog':'VENDOR_INSTALL_COMPLETION','prompt':'PRESS_ENTER_TO_CLOSE',
                        'installation_completed':True,'authentication_dialog':False,'password_prompt':False,
                        'unexpected_prompt':False,'key':'ENTER_ONLY'}
    return {'dialog':'RESTARTED_CURRENT100_IDE' if stage==10 else 'FRESH_CURRENT100_VALIDATION',
            'browser_suspended':False,'unexpected_prompt':False,'new_ai_consent_requested':False,'authentication_dialog':False}


def cancelled(root):
    if (root/'cancelled.json').exists():raise InterruptedError('PROFILE_CONTROL_CANCELLED')


def candidate(root):
    raw=read_regular(root/'profile-candidate.json',limit=256*1024)
    value=json_read(raw)
    import apparmor_profile
    public=apparmor_profile.public_evidence(value)
    return value,digest(raw),public,digest(encode(public))


def request_document(value):
    require(type(value) is dict and set(value)==FIELDS)
    trust.validate_context({k:value[k] for k in trust.CONTEXT_FIELDS})
    stage=stage_number(value['stage']);require(type(value['schema']) is int and value['schema']==1)
    require(value['action']==ACTIONS[stage] and value['protocol']==PROTOCOL and type(value['terminal_stage']) is int and value['terminal_stage']==11)
    require(type(value['epoch']) is int and value['epoch']==({7:0,8:0,9:0,10:1,11:2}[stage]))
    for key in ('screenshot_sha256','display_binding_sha256','preceding_receipt_sha256','candidate_sha256','profile_evidence_sha256'):
        trust.token(value[key],r'[0-9a-f]{64}')
    window.inventory(value['windows'])
    if stage==9:
        terminal_document(value['terminal_identity'])
        require(len({row['pid'] for row in value['windows']})<=2)
        require(len([row for row in value['windows'] if row['pid']==value['terminal_identity']['pid']])==1)
        trust.token(value['installed_profile_sha256'],r'[0-9a-f]{64}')
    else:
        require(len({row['pid'] for row in value['windows']})==1)
        require(value['terminal_identity'] is None and value['installed_profile_sha256'] is None)
    if stage in (7,8,9):require(value['active_context_sha256'] is None)
    else:trust.token(value['active_context_sha256'],r'[0-9a-f]{64}')
    return value


def terminal_document(value):
    require(type(value) is dict and set(value)=={'pid','ppid','pgrp','session','uid','start_time','executable_sha256'})
    for key in ('pid','ppid','pgrp','session'):
        require(type(value[key]) is int and 0<value[key]<2**31)
    require(type(value['uid']) is int and 0<=value['uid']<2**32)
    trust.token(value['start_time'],r'[0-9]{1,20}');trust.token(value['executable_sha256'],r'[0-9a-f]{64}')
    return value


def installed_bytes(proposed):
    import apparmor_profile
    result=apparmor_profile.verify_installed(proposed,env=dict(os.environ))
    require(result.get('status')=='INSTALLED_VERIFIED' and type(result.get('exact_name_count')) is int and result['exact_name_count']==1)
    # public_evidence is the fixed scalar allowlist; never copy unknown helper fields.
    return encode({**apparmor_profile.public_evidence(proposed),'status':'INSTALLED_VERIFIED','exact_name_count':1})


def terminal_current(proposed,expected):
    from restart_family import info
    terminal=terminal_document(expected);pid=terminal['pid']
    current=info(pid)
    require(current['state'] not in ('Z','X') and current['uid']==os.getuid())
    require({k:current[k] for k in terminal if k!='executable_sha256'}=={k:v for k,v in terminal.items() if k!='executable_sha256'})
    helper=proposed['parser']['expected_helpers']['TERMINAL']
    require(os.readlink(f'/proc/{pid}/exe')==helper['path'])
    st=Path(helper['path']).lstat()
    require([st.st_dev,st.st_ino,st.st_uid,st.st_mode,st.st_size,st.st_mtime_ns,st.st_ctime_ns]==helper['identity'])
    require(helper['sha256']==terminal['executable_sha256'])
    return current


def context_document(value):
    require(type(value) is dict and set(value)==trust.CONTEXT_FIELDS|{'schema','epoch','pid','start_time','status','interface','mode','profile_name_sha256','context_sha256'})
    trust.validate_context({k:value[k] for k in trust.CONTEXT_FIELDS})
    require(type(value['schema']) is int and value['schema']==1 and type(value['epoch']) is int and value['epoch'] in (1,2))
    require(type(value['pid']) is int and 0<value['pid']<2**31)
    trust.token(value['start_time'],r'[0-9]{1,20}')
    require(value['status']=='CONTEXT_VERIFIED' and value['interface'] in ('APPARMOR_CURRENT','LSM_CURRENT') and value['mode']=='unconfined')
    for key in ('profile_name_sha256','context_sha256'):trust.token(value[key],r'[0-9a-f]{64}')
    return value


def context_bytes(root,stage,request=None):
    if stage in (7,8,9):return None
    raw=read_regular(root/f'epoch-{stage-9}/apparmor-context.json',limit=4096)
    value=context_document(json_read(raw))
    require(value['epoch']==stage-9 and {k:value[k] for k in trust.CONTEXT_FIELDS}==trust.context(root))
    _,_,public,_=candidate(root);require(value['profile_name_sha256']==public['profile_name_sha256'])
    if request is not None:
        require(digest(raw)==request['active_context_sha256'] and value['pid']==request['windows'][0]['pid'])
    return raw


def validate_control(value,expected):
    request_document(expected)
    extra={'visual_review','target'} if expected['stage'] in (7,8) else {'visual_review'}
    require(type(value) is dict and set(value)==FIELDS|extra)
    require({k:value[k] for k in FIELDS}==expected)
    required=review(expected['stage']);actual=value['visual_review']
    require(type(actual) is dict and set(actual)==set(required) and actual==required)
    for key,entry in required.items():
        if type(entry) is bool:require(type(actual[key]) is bool)
    if 'target' in extra:
        target=value['target'];require(type(target) is dict and set(target)=={'window_id','point'})
        require(type(target['window_id']) is int)
        matches=[row for row in expected['windows'] if row['window_id']==target['window_id']]
        require(len(matches)==1);window.point(target['point'],matches[0])
    return value


def receipt_document(value,expected):
    extra={'visual_review','target'} if expected['stage'] in (7,8) else {'visual_review'}
    require(type(value) is dict and set(value)==FIELDS|extra|{'status','after_sha256'})
    validate_control({k:value[k] for k in FIELDS|extra},expected)
    if expected['stage'] in (8,9):
        require(value['status']==('INSTALL_CLICK_DISPATCHED_OUTCOME_UNVERIFIED' if expected['stage']==8 else 'TERMINAL_ENTER_DISPATCHED_RESTART_UNVERIFIED') and value['after_sha256'] is None)
    elif expected['stage']==7:
        require(value['status']=='NORMAL_UI_ACTION_NOT_ACCEPTANCE');trust.token(value['after_sha256'],r'[0-9a-f]{64}')
    else:
        require(value['status']=='VISUAL_OBSERVATION_NOT_ACCEPTANCE' and value['after_sha256'] is None)
    return value


def preceding(root,stage):
    previous=stage_number(stage)-1
    raw=read_regular(root/f'stage-{previous}/receipt.json',limit=4096)
    expected=json_read(read_regular(root/f'stage-{previous}/request.json',limit=4096))
    if previous==6:
        plugin.receipt_document(json_read(raw),expected);plugin.read_modal(root/'stage-6',expected)
    else:receipt_document(json_read(raw),expected)
    require({k:expected[k] for k in trust.CONTEXT_FIELDS}==trust.context(root))
    return digest(raw)


def observe(root,pid,runner,environment,terminal=None):
    cancelled(root)
    command=[sys.executable,__file__,'observe','--pid',str(pid)]
    if terminal is not None:command.extend(['--terminal-pid',str(terminal)])
    result=runner(command,env=environment,
                  stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,timeout=2,check=True)
    require(len(result.stdout)<=3072)
    return window.inventory(json_read(result.stdout),pid if terminal is None else None)


def binding_for(root,stage):
    if stage==9:return root/'stage-9/display-binding.properties'
    return root/'display-binding.properties' if stage in (7,8) else root/f'epoch-{stage-9}'/'display-binding.properties'


def checkpoint(root,stage,proc,screen,identity,family,deadline,environment,terminal=None):
    stage_number(stage);cancelled(root);family.check()
    require(time.monotonic()<deadline and proc.poll() is None)
    proposed,proposal_sha,public,public_sha=candidate(root)
    previous=preceding(root,stage)
    folder=root/f'stage-{stage}';new_directory(folder)
    terminal_meta=None;installed=None
    if stage==9:
        require(terminal is not None and family.verify_terminal_helpers(terminal))
        meta=family.members[terminal.key]['meta'];handle=family.members[terminal.key]['fd']
        terminal_meta=terminal_document({**{k:meta[k] for k in ('pid','ppid','pgrp','session','uid','start_time')},
            'executable_sha256':proposed['parser']['expected_helpers']['TERMINAL']['sha256']})
        terminal_current(proposed,terminal_meta);installed=installed_bytes(proposed)
        publish(folder/'installed-profile.json',installed)
        base=read_regular(identity.binding,limit=4096)
        require(b'terminal.' not in base)
        extra={**{k:meta[k] for k in ('pid','ppid','pgrp','session','uid','start_time')},'fd':handle}
        publish(binding_for(root,stage),base+b''.join(f'terminal.{k}={v}\n'.encode() for k,v in sorted(extra.items())))
    else:require(terminal is None)
    terminal_pid=terminal.pid if terminal is not None else None
    identity.verify();windows=observe(root,proc.pid,family.run,environment,terminal_pid)
    screen('SNAPSHOT',folder/'before.png')
    identity.verify();require(observe(root,proc.pid,family.run,environment,terminal_pid)==windows)
    image=read_regular(folder/'before.png',limit=2*1024*1024);clean_png(image)
    expected=request_document({**trust.context(root),'schema':1,'stage':stage,'action':ACTIONS[stage],
        'protocol':PROTOCOL,'terminal_stage':11,'epoch':{7:0,8:0,9:0,10:1,11:2}[stage],
        'screenshot_sha256':digest(image),'display_binding_sha256':digest(read_regular(binding_for(root,stage),limit=4096)),
        'windows':windows,'preceding_receipt_sha256':previous,'candidate_sha256':proposal_sha,'profile_evidence_sha256':public_sha,
        'active_context_sha256':digest(context_bytes(root,stage)) if stage in (10,11) else None,
        'terminal_identity':terminal_meta,'installed_profile_sha256':digest(installed) if installed else None})
    publish(folder/'request.json',encode(expected))
    while not (folder/'control.json').exists():
        cancelled(root);family.check();require(time.monotonic()<deadline and proc.poll() is None)
        family.tick();time.sleep(.2)
    approved=validate_control(json_read(read_regular(folder/'control.json',limit=4096)),expected)
    cancelled(root);family.check();require(time.monotonic()<deadline and proc.poll() is None)
    require(preceding(root,stage)==previous and candidate(root)[1]==proposal_sha)
    require(trust.context(root)=={k:expected[k] for k in trust.CONTEXT_FIELDS})
    identity.verify()
    if stage in (7,8,9):
        require(observe(root,proc.pid,family.run,environment,terminal_pid)==windows)
        if stage==8:
            import apparmor_profile
            require(deadline-time.monotonic()>=120)
            apparmor_profile.recheck_before(proposed,Path(os.readlink(f'/proc/{proc.pid}/exe')),
                runner=family.run,env=environment,receipt_path=folder/'provider-observation.json')
            family.arm_restart(proc,digest(encode(approved)))
        if stage==9:
            require(family.verify_terminal_helpers(terminal));terminal_current(proposed,terminal_meta)
            require(digest(installed_bytes(proposed))==expected['installed_profile_sha256'])
        screen(ACTIONS[stage],folder/'after.png',expected['screenshot_sha256'],folder/'performed.txt',approved=approved)
        require(read_regular(folder/'performed.txt',limit=64)==(ACTIONS[stage]+'\n').encode())
        family.check();cancelled(root)
        if stage==8:family.clicked(digest(encode(approved)));after=None;status='INSTALL_CLICK_DISPATCHED_OUTCOME_UNVERIFIED'
        elif stage==9:
            install=json_read(read_regular(root/'stage-8/control.json',limit=4096))
            family.terminal_acknowledged(digest(encode(install)))
            after=None;status='TERMINAL_ENTER_DISPATCHED_RESTART_UNVERIFIED'
        else:
            after=digest(read_regular(folder/'after.png',limit=2*1024*1024));status='NORMAL_UI_ACTION_NOT_ACCEPTANCE'
    else:
        # Read-only approval attests this captured image. No input event or old
        # image is used to drive a moving validation screen.
        after=None;status='VISUAL_OBSERVATION_NOT_ACCEPTANCE'
    publish(folder/'receipt.json',encode(receipt_document({**approved,'status':status,'after_sha256':after},expected)))


def verify_window(root,expected_path):
    stage=next((s for s in (7,8,9) if expected_path==root/f'stage-{s}/request.json'),None);stage_number(stage)
    cancelled(root)
    expected=request_document(json_read(read_regular(expected_path,limit=4096)))
    approved=validate_control(json_read(read_regular(root/f'stage-{stage}/control.json',limit=4096)),expected)
    require(time.monotonic()<read_ui_deadline(root))
    require(trust.context(root)=={k:expected[k] for k in trust.CONTEXT_FIELDS})
    proposed,sha,_,summary_sha=candidate(root)
    require(sha==expected['candidate_sha256'] and summary_sha==expected['profile_evidence_sha256'])
    require(digest(read_regular(binding_for(root,stage),limit=4096))==expected['display_binding_sha256'])
    require(preceding(root,stage)==expected['preceding_receipt_sha256'])
    binding=read_regular(root/'display-binding.properties',limit=4096).decode('ascii')
    pids=[line[8:] for line in binding.splitlines() if line.startswith('ide.pid=')]
    require(len(pids)==1 and pids[0].isdigit());pid=int(pids[0])
    terminal_pid=expected['terminal_identity']['pid'] if stage==9 else None
    if stage==9:
        terminal_current(proposed,expected['terminal_identity'])
        require(digest(installed_bytes(proposed))==expected['installed_profile_sha256'])
    require(window.observe(pid,terminal_pid)==expected['windows'])
    if stage==8:
        import apparmor_profile
        apparmor_profile.recheck_snapshot(proposed,Path(os.readlink(f'/proc/{pid}/exe')),
            env=dict(os.environ),receipt_path=root/f'stage-{stage}/provider-observation.json')
    cancelled(root);require(time.monotonic()<read_ui_deadline(root))


def receive(root,stage):
    stage_number(stage);cancelled(root)
    expected=request_document(json_read(read_regular(root/f'stage-{stage}/request.json',limit=4096)))
    require(expected['stage']==stage and trust.context(root)=={k:expected[k] for k in trust.CONTEXT_FIELDS})
    require(preceding(root,stage)==expected['preceding_receipt_sha256'])
    output=root/f'stage-{stage}/control.json';require(not output.exists() and not output.is_symlink())
    budget,deadline=read_ui_budget(root)
    while time.monotonic()<deadline:
        cancelled(root)
        value=fetch_control(os.environ['GITHUB_REPOSITORY'],expected['run_id'],expected['run_attempt'],stage,os.environ['GH_TOKEN'],min(5,deadline-time.monotonic()))
        if value is not None:
            validate_control(value,expected);cancelled(root);read_ui_deadline(root,expected=budget);require(time.monotonic()<deadline)
            publish(output,encode(value));return
        time.sleep(min(2,max(0,deadline-time.monotonic())))
    raise TimeoutError('PROFILE_CONTROL_DEADLINE')


def collect(root,stage,run_id,attempt):
    stage_number(stage);folder=root/f'stage-{stage}'
    request=request_document(json_read(read_regular(folder/'request.json',limit=4096)))
    require(request['stage']==stage and request['run_id']==run_id and request['run_attempt']==attempt)
    require(root.name=='academy-ui-'+run_id+'-'+attempt)
    require(preceding(root,stage)==request['preceding_receipt_sha256'])
    _,sha,public,summary_sha=candidate(root)
    require(sha==request['candidate_sha256'] and summary_sha==request['profile_evidence_sha256'])
    raw=read_regular(folder/'before.png',limit=2*1024*1024);require(digest(raw)==request['screenshot_sha256']);clean=clean_png(raw)
    prefix=f'profile-stage-{stage}'
    mapping={'schema':1,'before_raw_sha256':digest(raw),'before_uploaded_sha256':digest(clean),'after_raw_sha256':None,'after_uploaded_sha256':None}
    files={prefix+'-request.json':encode(request),prefix+'-before.png':clean,prefix+'-profile-summary.json':encode(public)}
    if stage==9:
        raw=read_regular(folder/'installed-profile.json',limit=4096)
        expected_installed={**public,'status':'INSTALLED_VERIFIED','exact_name_count':1}
        parsed=json_read(raw)
        require(type(parsed) is dict and parsed==expected_installed and all(type(parsed[k]) is type(v) for k,v in expected_installed.items())
                and digest(raw)==request['installed_profile_sha256'])
        files[prefix+'-installed-profile.json']=encode(expected_installed)
    if stage in (10,11):files[prefix+'-apparmor-context.json']=context_bytes(root,stage,request)
    try:receipt=receipt_document(json_read(read_regular(folder/'receipt.json',limit=4096)),request)
    except FileNotFoundError:receipt=None
    if receipt is not None:
        files[prefix+'-receipt.json']=encode(receipt)
        if stage==7:
            after=read_regular(folder/'after.png',limit=2*1024*1024);require(digest(after)==receipt['after_sha256'])
            clean_after=clean_png(after);files[prefix+'-after.png']=clean_after
            mapping.update(after_raw_sha256=digest(after),after_uploaded_sha256=digest(clean_after))
    files[prefix+'-images.json']=encode(mapping)
    return files


def stage_artifact(root,stage,phase,run_id,attempt):
    require(phase in ('review','receipt'));stage_number(stage)
    out=root/f'profile-{stage}-{phase}-artifact';new_directory(out)
    receipt=root/f'stage-{stage}/receipt.json'
    require((phase=='review' and not receipt.exists()) or (phase=='receipt' and receipt.is_file()))
    files=collect(root,stage,run_id,attempt)
    if phase=='review':files[f'profile-stage-{stage}-review-target.json']=encode({'protocol':PROTOCOL,'terminal_stage':11,'action':ACTIONS[stage],
        'screen':[1280,900],'required_visual_review':review(stage),'coordinate_rule':'Stages 7/8 approve one point in the named button; stage 9 sends only Enter to the already focused verified completion terminal with no target; later observations contain no input.'})
    for name,raw in files.items():publish(out/name,raw)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('mode',choices=['observe','verify-window','receive','complete','stage-artifact'])
    p.add_argument('--root',type=Path);p.add_argument('--pid',type=int);p.add_argument('--terminal-pid',type=int);p.add_argument('--stage',type=int,choices=list(ACTIONS))
    p.add_argument('--expected',type=Path);p.add_argument('--phase',choices=['review','receipt']);p.add_argument('--run-id');p.add_argument('--run-attempt');a=p.parse_args()
    if a.mode=='observe':print(json.dumps(window.observe(a.pid,a.terminal_pid),separators=(',',':')))
    elif a.mode=='verify-window':verify_window(a.root,a.expected)
    elif a.mode=='receive':receive(a.root,a.stage)
    elif a.mode=='stage-artifact':stage_artifact(a.root,a.stage,a.phase,a.run_id,a.run_attempt)
    else:
        deadline=read_ui_deadline(a.root)
        while not (a.root/f'stage-{a.stage}/receipt.json').exists():
            cancelled(a.root);require(time.monotonic()<deadline and not (a.root/'result.json').exists());time.sleep(.2)
        receipt_document(json_read(read_regular(a.root/f'stage-{a.stage}/receipt.json',limit=4096)),
                         request_document(json_read(read_regular(a.root/f'stage-{a.stage}/request.json',limit=4096))))
