"""Two fresh normal-UI actions for the pinned base plugin only, never AI consent."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time
import urllib.request
from display_diagnostic import clean_png, digest, encode, json_read, publish
from safe_io import read_regular, validate_directory, new_directory
from ui_control import read_ui_budget, fetch_control, read_ui_deadline, NoRedirect
import project_trust as trust
import trust_window as window
import modal_window
import modal_pixels

ACTIONS={5:'CHECK_ACADEMY_PLUGIN_ONLY',6:'AGREE_ACADEMY_PLUGIN_ONLY'}
PROTOCOL='ACADEMY_PLUGIN_ONLY_THEN_SCOPED_PROFILE_TERMINAL_ACK_V2'
TERMINAL_STAGE=11
LEGAL_SHA='aca54faf26bbebc27bc32f2b9ac2f3118817f21f6a081ef07610776f9bda75b7'
PLUGIN_SHA='8358566831fe364238b584a120d7c9f8251f3cc972bce257441c52a29e6eb82b'
LEGAL_ID={'plugin_version':'1.3','privacy_version':'3.2','documents_sha256':LEGAL_SHA,
    'verification_scope':'REVIEWED_OFFICIAL_PDF_BYTES_ONLY','html_semantics':'NOT_VERIFIED',
    'pinned_ui_links_sha256':'d4f3690da95d7e618590d5b41e6bdb3c85f7a93ac70ac28920c1bbbdcdf9105a'}
FIELDS=trust.CONTEXT_FIELDS|{'schema','stage','action','protocol','terminal_stage','legal_identity','plugin_binary_sha256',
    'screenshot_sha256','display_binding_sha256','window_identity','preceding_receipt_sha256',
    'comparison_mode','window_proof_sha256','dialog_pixel_sha256'}
STATUS='UI_ACTION_PERFORMED_NOT_COURSE_ACCEPTANCE'

# Diagnostics never carry exception text, child stderr, commands, or window titles.
EXCEPTION_CLASSES={'NONE','InterruptedError','TimeoutError','TimeoutExpired','CalledProcessError',
    'ValueError','OSError','TypeError','AttributeError','KeyError','ImportError','NameError',
    'MemoryError','RecursionError','SystemExit','FamilyError','ProfileError','ModalProbeFailure','OTHER'}
EXCEPTION_CLASSES.update({'FileNotFoundError','FileExistsError','ProcessLookupError','PermissionError',
    'NotADirectoryError','IsADirectoryError','BrokenPipeError','RuntimeError','NotImplementedError',
    'AssertionError','JSONDecodeError'})
CHECKPOINT_STEPS={'START','CONTEXT','PLUGIN_BINARY','PDF_CHECK','PRECEDING_RECEIPT','CREATE_STAGE',
    'DISPLAY_BEFORE_PROBE','MODAL_PROBE_BEFORE_SNAPSHOT','SNAPSHOT','DISPLAY_AFTER_SNAPSHOT',
    'MODAL_PROBE_AFTER_SNAPSHOT','SNAPSHOT_DECODE','REQUEST_ENCODE','REQUEST_PUBLISH',
    'CONTROL_WAIT','CONTROL_VALIDATE','CONTEXT_RECHECK','PLUGIN_RECHECK','PDF_RECHECK',
    'DISPLAY_RECHECK','MODAL_PROBE_BEFORE_ACTION','APPROVED_IMAGE_RECHECK','ACTION',
    'PERFORMED_RECEIPT','AFTER_IMAGE','RECEIPT_PUBLISH'}
FAILURE_REASONS={'CANCELLED','SUBPROCESS_TIMEOUT','SUBPROCESS_EXIT','MODAL_PROBE_REJECTED',
    'BOUNDARY_REJECTED','UNCLASSIFIED_EXCEPTION'}
CHECKPOINT_FAILURE_FIELDS={'schema','status','stage','step','context','exception_class','reason',
    'probe_exit_code','modal_failure','request_state','action_invoked'}

def exception_class(exc):
    name=type(exc).__name__
    return name if name in EXCEPTION_CLASSES and name!='NONE' else 'OTHER'

class ModalProbeFailure(ValueError):
    def __init__(self,exit_code,document=None):
        self.exit_code=exit_code
        self.document=document
        super().__init__('MODAL_PROBE_REJECTED')

def checkpoint_failure_document(value):
    require(type(value) is dict and set(value)==CHECKPOINT_FAILURE_FIELDS)
    require(type(value['schema']) is int and value['schema']==1 and value['status']=='FAILED_NOT_ACCEPTANCE')
    stage_number(value['stage'])
    for key,allowed in [('step',CHECKPOINT_STEPS),('exception_class',EXCEPTION_CLASSES-{'NONE'}),('reason',FAILURE_REASONS)]:
        require(type(value[key]) is str and value[key] in allowed)
    require(value['context'] is None or type(value['context']) is dict)
    if value['context'] is not None:trust.validate_context(value['context'])
    else:require(value['step'] in ('START','CONTEXT'))
    code=value['probe_exit_code'];require(code is None or type(code) is int and -127<=code<=255 and code!=0)
    if code is not None:require(value['reason'] in ('SUBPROCESS_EXIT','MODAL_PROBE_REJECTED'))
    if value['modal_failure'] is not None:
        require(value['reason']=='MODAL_PROBE_REJECTED' and code is not None)
        modal_window.failure_document(value['modal_failure'])
    require(type(value['request_state']) is str and value['request_state'] in ('NOT_ATTEMPTED','ATTEMPTED_UNCONFIRMED','PUBLISHED'))
    if value['request_state']=='ATTEMPTED_UNCONFIRMED':require(value['step']=='REQUEST_PUBLISH')
    require(type(value['action_invoked']) is bool)
    require(not value['action_invoked'] or value['request_state']=='PUBLISHED')
    if value['action_invoked']:require(value['step'] in ('ACTION','PERFORMED_RECEIPT','AFTER_IMAGE','RECEIPT_PUBLISH'))
    require(len(encode(value))<=4096)
    return value

def checkpoint_failure(progress,exc):
    code=getattr(exc,'returncode',None) if isinstance(exc,subprocess.CalledProcessError) else None
    modal=None
    if isinstance(exc,ModalProbeFailure):code=exc.exit_code;modal=exc.document
    if type(code) is not int or not -127<=code<=255 or code==0:code=None
    reason=('CANCELLED' if isinstance(exc,InterruptedError) else
        'SUBPROCESS_TIMEOUT' if isinstance(exc,(TimeoutError,subprocess.TimeoutExpired)) else
        'MODAL_PROBE_REJECTED' if isinstance(exc,ModalProbeFailure) else
        'SUBPROCESS_EXIT' if isinstance(exc,subprocess.CalledProcessError) else
        'BOUNDARY_REJECTED' if isinstance(exc,(ValueError,OSError)) else 'UNCLASSIFIED_EXCEPTION')
    return checkpoint_failure_document({'schema':1,'status':'FAILED_NOT_ACCEPTANCE',**progress,
        'exception_class':exception_class(exc),'reason':reason,'probe_exit_code':code,'modal_failure':modal})

def require(ok):
    if not ok:raise ValueError('invalid plugin-only agreement binding')
def stage_number(stage):
    require(type(stage) is int and stage in ACTIONS);return stage

def review(stage):
    stage_number(stage)
    return {'dialog':'ACADEMY_PLUGIN_AGREEMENT','plugin_checked':stage==6,'ai_training_checked':False,
        'scope':'CURRENT100_BASE_PLUGIN_ONLY','button':'BASE_PLUGIN_CHECKBOX' if stage==5 else 'AGREE',
        'agree_enabled':stage==6,'known_terms_mismatch':False,'new_terms_observed':False,
        'legal_basis':'REVIEWED_PLUGIN_1_3_PRIVACY_3_2_PDFS',
        'complete_dialog_visible':True,'dialog_unobscured':True,'all_decision_controls_inside':True}

def pins():
    raw=read_regular(Path(__file__).with_name('academy-legal.json'),limit=16384)
    require(digest(raw)==LEGAL_SHA);return json_read(raw)['documents']

def fetch_legal(deadline):
    """Reviewed official PDFs only; no assertion about current HTML semantics."""
    end=min(deadline,time.monotonic()+15)
    opener=urllib.request.build_opener(NoRedirect())
    for item in pins():
        remaining=end-time.monotonic();require(remaining>0)
        request=urllib.request.Request(item['url'],headers={'Accept-Encoding':'identity'})
        with opener.open(request,timeout=remaining) as response:
            require(response.geturl()==item['url'] and response.status==200)
            # Exact pinned lengths bound memory. A changed/error body never becomes evidence.
            raw=response.read(item['bytes']+1)
        require(time.monotonic()<end)
        require(item['format']=='pdf' and len(raw)==item['bytes'] and digest(raw)==item['sha256'])
    return dict(LEGAL_ID)

def verify_legal(deadline,runner=None):
    # A directly spawned read-only child gives the entire two-PDF HTTP transaction a hard
    # wall-clock cap, including a server that trickles bytes before socket timeout.
    remaining=min(15,deadline-time.monotonic());require(remaining>0)
    environment={'PATH':os.defpath,'LANG':'C.UTF-8'}
    # Retain only existing normal proxy/CA routing when present; never disable TLS.
    for name in ('HTTPS_PROXY','HTTP_PROXY','ALL_PROXY','NO_PROXY','https_proxy','http_proxy','all_proxy','no_proxy','SSL_CERT_FILE','SSL_CERT_DIR'):
        if name in os.environ:environment[name]=os.environ[name]
    result=(runner or subprocess.run)([sys.executable,__file__,'legal-body-check','--deadline',str(deadline)],
        env=environment,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,
        timeout=remaining,check=True)
    require(time.monotonic()<deadline and len(result.stdout)<=512)
    value=json_read(result.stdout);require(value==LEGAL_ID);return value

def verify_plugin(root,idea):
    require(type(idea) is Path or isinstance(idea,Path))
    plugins=idea.parent/'plugins'
    jar=plugins/'JetBrainsAcademy/lib/JetBrainsAcademy-2026.9-2026.1-1070.jar'
    require(digest(read_regular(jar,limit=64*1024*1024))==PLUGIN_SHA)
    run,*_=trust.paths(root)
    props=read_regular(run/'validate-profile/idea.properties',limit=16384).decode('utf-8')
    lines=[line for line in props.splitlines() if line.startswith('idea.plugins.path=')]
    require(lines==['idea.plugins.path='+str(plugins)])
    return PLUGIN_SHA

def read_modal(folder,request):
    """Fixed no-follow sidecar; the entire graph stays out of small control records."""
    raw=read_regular(folder/'modal-proof.json',limit=modal_window.MAX_PROOF_BYTES)
    require(digest(raw)==request['window_proof_sha256'])
    proof=modal_window.validate(json_read(raw),request['action'])
    require(proof['window_identity']==request['window_identity'])
    image=read_regular(folder/'before.png',limit=2*1024*1024)
    require(digest(image)==request['screenshot_sha256'])
    require(modal_pixels.pixel_hash(image,request['window_identity'])==request['dialog_pixel_sha256'])
    return proof

FAILURE_FIELDS={'schema','action','phase','reason','dispatch_state','approved_full_sha256','approved_dialog_sha256',
    'approved_proof_sha256','current_full_sha256','current_dialog_sha256','current_proof_sha256','private_frame_status'}
def collect_failure(folder,expected):
    """Typed evidence only. A changed frame is NEVER cleared for public upload here."""
    value=json_read(read_regular(folder/'comparison-failure.json',limit=4096))
    require(type(value) is dict and set(value)==FAILURE_FIELDS and type(value['schema']) is int and value['schema']==1)
    require(value['action']==expected['action'])
    require(value['phase'] in ('INITIAL_ONE','INITIAL_TWO','FINAL_PROBE','FINAL_PIXELS','PRE_PRESS','POST_PRESS'))
    require(value['reason'] in ('MODAL_PIXELS_CHANGED','WINDOW_PROOF_UNAVAILABLE','OWNERSHIP_OR_ACTION_UNAVAILABLE','CANCELLED'))
    require(value['dispatch_state'] in ('NO_INPUT_DISPATCHED','DISPATCH_STARTED'))
    require(value['private_frame_status'] in ('RETAINED_PRIVATE_ONLY','UNAVAILABLE'))
    require(value['approved_full_sha256']==expected['screenshot_sha256'])
    for key,bound in [('approved_dialog_sha256','dialog_pixel_sha256'),('approved_proof_sha256','window_proof_sha256')]:
        require(value[key] is None or value[key]==expected[bound])
    for key in ('current_full_sha256','current_dialog_sha256','current_proof_sha256'):
        if value[key] is not None:trust.token(value[key],r'[0-9a-f]{64}')
    if value['reason']=='MODAL_PIXELS_CHANGED':
        require(value['phase'] in ('INITIAL_ONE','INITIAL_TWO','FINAL_PIXELS') and value['dispatch_state']=='NO_INPUT_DISPATCHED')
        require(value['current_full_sha256'] is not None and value['current_dialog_sha256'] is not None)
        require(value['current_dialog_sha256']!=expected['dialog_pixel_sha256'])
    require((value['phase']=='POST_PRESS')==(value['dispatch_state']=='DISPATCH_STARTED'))
    if value['private_frame_status']=='RETAINED_PRIVATE_ONLY':require(value['current_full_sha256'] is not None)
    control_raw=read_regular(folder/'control.json',limit=4096);validate_control(json_read(control_raw),expected)
    # Never open or export the private frame, even when its digest appears in the receipt.
    return {**value,'run_id':expected['run_id'],'run_attempt':expected['run_attempt'],'stage':expected['stage'],
        'request_sha256':digest(read_regular(folder/'request.json',limit=4096)),'control_sha256':digest(control_raw),
        'tested_sha':expected['tested_sha'],'source_tree':expected['source_tree'],'archive_sha256':expected['archive_sha256'],
        'failure_image_public':'NOT_CLEARED','status':'DIAGNOSTIC_NOT_ACCEPTANCE'}

def request_document(value):
    require(type(value) is dict and set(value)==FIELDS)
    trust.validate_context({k:value[k] for k in trust.CONTEXT_FIELDS})
    stage=stage_number(value['stage'])
    require(type(value['schema']) is int and value['schema']==1 and value['action']==ACTIONS[stage])
    require(value['protocol']==PROTOCOL and type(value['terminal_stage']) is int and value['terminal_stage']==TERMINAL_STAGE)
    require(type(value['legal_identity']) is dict and value['legal_identity']==LEGAL_ID)
    require(value['plugin_binary_sha256']==PLUGIN_SHA)
    for key in ('screenshot_sha256','display_binding_sha256','preceding_receipt_sha256','window_proof_sha256','dialog_pixel_sha256'):trust.token(value[key],r'[0-9a-f]{64}')
    require(value['comparison_mode']==modal_pixels.MODE)
    window.validate(value['window_identity'],ACTIONS[stage]);modal_pixels.rectangle(value['window_identity']);return value

def validate_control(value,expected):
    request_document(expected)
    require(type(value) is dict and set(value)==FIELDS|{'visual_review'})
    visual=value['visual_review'];required=review(expected['stage'])
    require(type(visual) is dict and set(visual)==set(required) and visual==required)
    for name in ('plugin_checked','ai_training_checked','agree_enabled','known_terms_mismatch','new_terms_observed','complete_dialog_visible','dialog_unobscured','all_decision_controls_inside'):require(type(visual[name]) is bool)
    request_document({k:value[k] for k in FIELDS})
    require({k:value[k] for k in FIELDS}==expected);return value

def receipt_document(value,expected):
    require(type(value) is dict and set(value)==FIELDS|{'visual_review','after_sha256','status','legal_rechecked'})
    validate_control({k:value[k] for k in FIELDS|{'visual_review'}},expected)
    require(value['status']==STATUS and value['legal_rechecked'] is True)
    trust.token(value['after_sha256'],r'[0-9a-f]{64}');return value

def preceding(root,stage,expected_context):
    previous=stage_number(stage)-1
    raw=read_regular(root/f'stage-{previous}/receipt.json',limit=4096);value=json_read(raw)
    request=trust.read_json(root/f'stage-{previous}/request.json',4096)
    require(type(request) is dict and type(request.get('stage')) is int and request['stage']==previous)
    if previous==4:
        trust.request_document(request)
        require(type(value) is dict and set(value)==trust.REQUEST_FIELDS|{'visual_review','after_sha256','status'})
        trust.validate_control({k:value[k] for k in trust.REQUEST_FIELDS|{'visual_review'}},request)
        require(value['status']==STATUS);trust.token(value['after_sha256'],r'[0-9a-f]{64}')
    else:
        receipt_document(value,request);read_modal(root/f'stage-{previous}',request)
    require({k:request[k] for k in trust.CONTEXT_FIELDS}==expected_context)
    require(digest(read_regular(root/f'stage-{previous}/after.png',limit=2*1024*1024))==value['after_sha256'])
    require(digest(read_regular(root/'display-binding.properties',limit=4096))==request['display_binding_sha256'])
    return digest(raw)

def window_probe(pid,action,environment,runner=None):
    require(action in ACTIONS.values())
    result=(runner or subprocess.run)([sys.executable,__file__,'observe-window','--pid',str(pid),'--stage',str(next(k for k,v in ACTIONS.items() if v==action))],
        env=environment,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,timeout=2,check=False)
    require(type(result.returncode) is int and -127<=result.returncode<=255)
    if result.returncode:
        document=None
        try:
            require(type(result.stdout) is bytes and len(result.stdout)<=2048)
            document=modal_window.failure_document(json_read(result.stdout))
        except (ValueError,TypeError,KeyError):pass
        raise ModalProbeFailure(result.returncode,document)
    require(len(result.stdout)<=modal_window.MAX_PROOF_BYTES);return modal_window.validate(json_read(result.stdout),action)

def checkpoint(root,stage,proc,screen,identity,owned,deadline,command,idea,environment,runner=None,progress=None):
    progress={} if progress is None else progress
    progress.clear();progress.update(stage=stage,step='START',context=None,request_state='NOT_ATTEMPTED',action_invoked=False)
    stage_number(stage);require(time.monotonic()<deadline and proc.poll() is None)
    progress['step']='CONTEXT';expected_context=trust.context(root,command,idea);progress['context']=expected_context
    progress['step']='PLUGIN_BINARY';plugin=verify_plugin(root,idea)
    progress['step']='PDF_CHECK';legal=verify_legal(deadline,**({'runner':runner} if runner else {}))
    progress['step']='PRECEDING_RECEIPT'
    prior=preceding(root,stage,expected_context)
    progress['step']='CREATE_STAGE'
    folder=root/f'stage-{stage}';new_directory(folder)
    action=ACTIONS[stage];progress['step']='DISPLAY_BEFORE_PROBE';identity.verify()
    progress['step']='MODAL_PROBE_BEFORE_SNAPSHOT';win=window_probe(identity.metadata['ide']['pid'],action,environment,**({'runner':runner} if runner else {}))
    progress['step']='SNAPSHOT';screen('SNAPSHOT',folder/'before.png')
    progress['step']='DISPLAY_AFTER_SNAPSHOT';identity.verify()
    progress['step']='MODAL_PROBE_AFTER_SNAPSHOT'
    require(window_probe(identity.metadata['ide']['pid'],action,environment,**({'runner':runner} if runner else {}))==win)
    progress['step']='SNAPSHOT_DECODE'
    raw=read_regular(folder/'before.png',limit=2*1024*1024);clean_png(raw)
    proof=win;win=proof['window_identity'];proof_raw=encode(proof)
    progress['step']='REQUEST_ENCODE'
    expected=request_document({**expected_context,'schema':1,'stage':stage,'action':action,'protocol':PROTOCOL,'terminal_stage':TERMINAL_STAGE,
        'legal_identity':legal,'plugin_binary_sha256':plugin,'preceding_receipt_sha256':prior,
        'screenshot_sha256':digest(raw),'display_binding_sha256':digest(read_regular(identity.binding,limit=4096)),'window_identity':win,
        'comparison_mode':modal_pixels.MODE,'window_proof_sha256':digest(proof_raw),'dialog_pixel_sha256':modal_pixels.pixel_hash(raw,win)})
    require(len(encode({**expected,'visual_review':review(stage),'after_sha256':'f'*64,'status':STATUS,'legal_rechecked':True}))<=4096)
    progress['step']='REQUEST_PUBLISH'
    publish(folder/'modal-proof.json',proof_raw);publish(folder/'window-identity.json',encode(win))
    progress['request_state']='ATTEMPTED_UNCONFIRMED';publish(folder/'request.json',encode(expected))
    progress['request_state']='PUBLISHED';progress['step']='CONTROL_WAIT'
    while not (folder/'control.json').exists():
        require(proc.poll() is None)
        if time.monotonic()>=deadline:raise TimeoutError('900秒UI总预算耗尽')
        owned.scan();time.sleep(.2)
    progress['step']='CONTROL_VALIDATE';approved=validate_control(trust.read_json(folder/'control.json',4096),expected)
    require(time.monotonic()<deadline and proc.poll() is None)
    progress['step']='CONTEXT_RECHECK'
    require(trust.context(root,command,idea)==expected_context and preceding(root,stage,expected_context)==prior)
    progress['step']='PLUGIN_RECHECK';verify_plugin(root,idea)
    progress['step']='PDF_RECHECK';require(verify_legal(deadline,**({'runner':runner} if runner else {}))==legal)
    progress['step']='DISPLAY_RECHECK'
    require(digest(read_regular(identity.binding,limit=4096))==expected['display_binding_sha256'])
    identity.verify();progress['step']='MODAL_PROBE_BEFORE_ACTION'
    require(window_probe(identity.metadata['ide']['pid'],action,environment,**({'runner':runner} if runner else {}))==proof)
    progress['step']='APPROVED_IMAGE_RECHECK'
    read_modal(folder,expected)
    require(time.monotonic()<deadline and proc.poll() is None)
    progress['step']='ACTION';progress['action_invoked']=True
    screen(action,folder/'after.png',expected['screenshot_sha256'],folder/'performed.txt')
    progress['step']='PERFORMED_RECEIPT'
    require(read_regular(folder/'performed.txt',limit=64)==(action+'\n').encode())
    progress['step']='AFTER_IMAGE';after=read_regular(folder/'after.png',limit=2*1024*1024);clean_png(after)
    progress['step']='RECEIPT_PUBLISH'
    publish(folder/'receipt.json',encode(receipt_document({**approved,'after_sha256':digest(after),'status':STATUS,'legal_rechecked':True},expected)))
    progress.clear()

def receive(root,stage):
    stage_number(stage);expected=request_document(trust.read_json(root/f'stage-{stage}/request.json',4096))
    require(expected['stage']==stage and trust.context(root)=={k:expected[k] for k in trust.CONTEXT_FIELDS});read_modal(root/f'stage-{stage}',expected)
    require(preceding(root,stage,{k:expected[k] for k in trust.CONTEXT_FIELDS})==expected['preceding_receipt_sha256'])
    budget,deadline=read_ui_budget(root);output=root/f'stage-{stage}/control.json'
    require(not output.exists() and not output.is_symlink())
    while time.monotonic()<deadline:
        value=fetch_control(os.environ['GITHUB_REPOSITORY'],expected['run_id'],expected['run_attempt'],stage,os.environ['GH_TOKEN'],min(5,deadline-time.monotonic()))
        if value is not None:
            validate_control(value,expected);read_modal(root/f'stage-{stage}',expected);read_ui_deadline(root,expected=budget);require(time.monotonic()<deadline);publish(output,encode(value));return
        time.sleep(min(2,max(0,deadline-time.monotonic())))
    raise TimeoutError('UI总预算耗尽；未写插件协议动作记录')

def collect(root,stage,run_id,attempt):
    stage_number(stage);folder=root/f'stage-{stage}'
    expected=request_document(trust.read_json(folder/'request.json',4096))
    require(expected['stage']==stage and expected['run_id']==run_id and expected['run_attempt']==attempt)
    require(root.name=='academy-ui-'+run_id+'-'+attempt)
    require(preceding(root,stage,{k:expected[k] for k in trust.CONTEXT_FIELDS})==expected['preceding_receipt_sha256'])
    proof=read_modal(folder,expected)
    raw=read_regular(folder/'before.png',limit=2*1024*1024);require(digest(raw)==expected['screenshot_sha256']);clean=clean_png(raw)
    prefix=f'plugin-stage-{stage}'
    mapping={'schema':1,'before_raw_sha256':digest(raw),'before_uploaded_sha256':digest(clean),'after_raw_sha256':None,'after_uploaded_sha256':None}
    files={prefix+'-request.json':encode(expected),prefix+'-before.png':clean,prefix+'-images.json':encode(mapping),prefix+'-modal-proof.json':encode(proof)}
    try:files[prefix+'-comparison-failure.json']=encode(collect_failure(folder,expected))
    except FileNotFoundError:pass
    except (ValueError,OSError):
        files[prefix+'-comparison-failure.json']=encode({'schema':1,'status':'INVALID_OPTIONAL_DIAGNOSTIC','stage':stage,'failure_image_public':'NOT_CLEARED'})
    try:receipt=receipt_document(trust.read_json(folder/'receipt.json',4096),expected)
    except FileNotFoundError:return files
    after=read_regular(folder/'after.png',limit=2*1024*1024);require(digest(after)==receipt['after_sha256']);clean_after=clean_png(after)
    mapping.update(after_raw_sha256=digest(after),after_uploaded_sha256=digest(clean_after))
    files.update({prefix+'-receipt.json':encode(receipt),prefix+'-after.png':clean_after,prefix+'-images.json':encode(mapping)})
    return files

def stage_artifact(root,stage,phase,run_id,attempt):
    stage_number(stage);require(phase in ('review','receipt'));validate_directory(root)
    require(root.name=='academy-ui-'+trust.token(run_id,r'[1-9][0-9]{0,19}')+'-'+trust.token(attempt,r'[1-9][0-9]{0,19}'))
    out=root/f'plugin-{stage}-{phase}-artifact';new_directory(out)
    receipt=root/f'stage-{stage}/receipt.json'
    if phase=='review':require(not receipt.exists())
    else:require(receipt.is_file())
    files=collect(root,stage,run_id,attempt)
    if phase=='review':files[f'plugin-stage-{stage}-review-target.json']=encode({'protocol':PROTOCOL,'terminal_stage':TERMINAL_STAGE,'action':ACTIONS[stage],
        'fixed_target':list(window.target(ACTIONS[stage])),'screen':[1280,900],'required_visual_review':review(stage),'legal_identity':LEGAL_ID})
    for name,raw in files.items():publish(out/name,raw)

def verify_window(root,expected_path):
    stage=next((s for s in ACTIONS if expected_path==root/f'stage-{s}/window-identity.json'),None);stage_number(stage)
    request=request_document(trust.read_json(root/f'stage-{stage}/request.json',4096));require(request['stage']==stage)
    validate_control(trust.read_json(root/f'stage-{stage}/control.json',4096),request)
    require(trust.context(root)=={k:request[k] for k in trust.CONTEXT_FIELDS})
    require(preceding(root,stage,{k:request[k] for k in trust.CONTEXT_FIELDS})==request['preceding_receipt_sha256'])
    expected=window.validate(trust.read_json(expected_path,2048),ACTIONS[stage]);require(expected==request['window_identity'])
    require(digest(read_regular(root/'display-binding.properties',limit=4096))==request['display_binding_sha256'])
    budget,deadline=read_ui_budget(root);require(time.monotonic()<deadline)
    proof=read_modal(root/f'stage-{stage}',request)
    require(modal_window.observe(expected['pid'],ACTIONS[stage])==proof);read_ui_deadline(root,expected=budget);require(time.monotonic()<deadline)
    return 'MODAL1 '+' '.join(str(v) for v in modal_pixels.rectangle(expected))+' '+request['dialog_pixel_sha256']+' '+request['screenshot_sha256']+' '+request['window_proof_sha256']

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('mode',choices=['receive','observe-window','verify-window','stage-artifact','complete','legal-body-check'])
    p.add_argument('--deadline',type=float);p.add_argument('--root',type=Path);p.add_argument('--pid',type=int);p.add_argument('--expected',type=Path)
    p.add_argument('--stage',type=int,choices=[5,6]);p.add_argument('--phase',choices=['review','receipt']);p.add_argument('--run-id');p.add_argument('--run-attempt')
    a=p.parse_args()
    if a.mode=='legal-body-check':print(json.dumps(fetch_legal(a.deadline),separators=(',',':')))
    elif a.mode=='receive':receive(a.root,a.stage)
    elif a.mode=='stage-artifact':stage_artifact(a.root,a.stage,a.phase,a.run_id,a.run_attempt)
    elif a.mode=='observe-window':
        try:print(json.dumps(modal_window.observe(a.pid,ACTIONS[stage_number(a.stage)]),separators=(',',':')))
        except InterruptedError:raise
        except Exception as exc:
            print(json.dumps(modal_window.failure_from_exception(exc),separators=(',',':')))
            raise SystemExit(2) from None
    elif a.mode=='verify-window':print(verify_window(a.root,a.expected))
    else:
        stage_number(a.stage);deadline=read_ui_deadline(a.root)
        while not (a.root/f'stage-{a.stage}/receipt.json').exists():
            if time.monotonic()>=deadline or (a.root/'result.json').exists():raise RuntimeError('插件正常UI动作未完成')
            time.sleep(.2)
        receipt_document(trust.read_json(a.root/f'stage-{a.stage}/receipt.json',4096),request_document(trust.read_json(a.root/f'stage-{a.stage}/request.json',4096)))
