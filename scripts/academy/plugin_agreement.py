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
from ui_control import fetch_control, read_ui_deadline, NoRedirect
import project_trust as trust
import trust_window as window

ACTIONS={5:'CHECK_ACADEMY_PLUGIN_ONLY',6:'AGREE_ACADEMY_PLUGIN_ONLY'}
PROTOCOL='ACADEMY_PLUGIN_ONLY_STAGES_5_6_SHORT_DIAGNOSTIC_V1'
LEGAL_SHA='aca54faf26bbebc27bc32f2b9ac2f3118817f21f6a081ef07610776f9bda75b7'
PLUGIN_SHA='8358566831fe364238b584a120d7c9f8251f3cc972bce257441c52a29e6eb82b'
LEGAL_ID={'plugin_version':'1.3','privacy_version':'3.2','documents_sha256':LEGAL_SHA,
    'verification_scope':'REVIEWED_OFFICIAL_PDF_BYTES_ONLY','html_semantics':'NOT_VERIFIED',
    'pinned_ui_links_sha256':'d4f3690da95d7e618590d5b41e6bdb3c85f7a93ac70ac28920c1bbbdcdf9105a'}
FIELDS=trust.CONTEXT_FIELDS|{'schema','stage','action','protocol','terminal_stage','legal_identity','plugin_binary_sha256',
    'screenshot_sha256','display_binding_sha256','window_identity','preceding_receipt_sha256'}
STATUS='UI_ACTION_PERFORMED_NOT_COURSE_ACCEPTANCE'

def require(ok):
    if not ok:raise ValueError('invalid plugin-only agreement binding')
def stage_number(stage):
    require(type(stage) is int and stage in ACTIONS);return stage

def review(stage):
    stage_number(stage)
    return {'dialog':'ACADEMY_PLUGIN_AGREEMENT','plugin_checked':stage==6,'ai_training_checked':False,
        'scope':'CURRENT100_BASE_PLUGIN_ONLY','button':'BASE_PLUGIN_CHECKBOX' if stage==5 else 'AGREE',
        'agree_enabled':stage==6,'known_terms_mismatch':False,'new_terms_observed':False,
        'legal_basis':'REVIEWED_PLUGIN_1_3_PRIVACY_3_2_PDFS'}

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

def verify_legal(deadline):
    # A directly spawned read-only child gives the entire two-PDF HTTP transaction a hard
    # wall-clock cap, including a server that trickles bytes before socket timeout.
    remaining=min(15,deadline-time.monotonic());require(remaining>0)
    environment={'PATH':os.defpath,'LANG':'C.UTF-8'}
    # Retain only existing normal proxy/CA routing when present; never disable TLS.
    for name in ('HTTPS_PROXY','HTTP_PROXY','ALL_PROXY','NO_PROXY','https_proxy','http_proxy','all_proxy','no_proxy','SSL_CERT_FILE','SSL_CERT_DIR'):
        if name in os.environ:environment[name]=os.environ[name]
    result=subprocess.run([sys.executable,__file__,'legal-body-check','--deadline',str(deadline)],
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

def request_document(value):
    require(type(value) is dict and set(value)==FIELDS)
    trust.validate_context({k:value[k] for k in trust.CONTEXT_FIELDS})
    stage=stage_number(value['stage'])
    require(type(value['schema']) is int and value['schema']==1 and value['action']==ACTIONS[stage])
    require(value['protocol']==PROTOCOL and type(value['terminal_stage']) is int and value['terminal_stage']==6)
    require(type(value['legal_identity']) is dict and value['legal_identity']==LEGAL_ID)
    require(value['plugin_binary_sha256']==PLUGIN_SHA)
    for key in ('screenshot_sha256','display_binding_sha256','preceding_receipt_sha256'):trust.token(value[key],r'[0-9a-f]{64}')
    window.validate(value['window_identity'],ACTIONS[stage]);return value

def validate_control(value,expected):
    request_document(expected)
    require(type(value) is dict and set(value)==FIELDS|{'visual_review'})
    visual=value['visual_review'];required=review(expected['stage'])
    require(type(visual) is dict and set(visual)==set(required) and visual==required)
    for name in ('plugin_checked','ai_training_checked','agree_enabled','known_terms_mismatch','new_terms_observed'):require(type(visual[name]) is bool)
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
    else:receipt_document(value,request)
    require({k:request[k] for k in trust.CONTEXT_FIELDS}==expected_context)
    require(digest(read_regular(root/f'stage-{previous}/after.png',limit=2*1024*1024))==value['after_sha256'])
    require(digest(read_regular(root/'display-binding.properties',limit=4096))==request['display_binding_sha256'])
    return digest(raw)

def window_probe(pid,action,environment):
    require(action in ACTIONS.values())
    result=subprocess.run([sys.executable,__file__,'observe-window','--pid',str(pid),'--stage',str(next(k for k,v in ACTIONS.items() if v==action))],
        env=environment,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,timeout=2,check=True)
    require(len(result.stdout)<=2048);return window.validate(json_read(result.stdout),action)

def checkpoint(root,stage,proc,screen,identity,owned,deadline,command,idea,environment):
    stage_number(stage);require(time.monotonic()<deadline and proc.poll() is None)
    expected_context=trust.context(root,command,idea)
    plugin=verify_plugin(root,idea);legal=verify_legal(deadline)
    prior=preceding(root,stage,expected_context)
    folder=root/f'stage-{stage}';new_directory(folder)
    action=ACTIONS[stage];identity.verify();win=window_probe(identity.metadata['ide']['pid'],action,environment)
    screen('SNAPSHOT',folder/'before.png');identity.verify()
    require(window_probe(identity.metadata['ide']['pid'],action,environment)==win)
    raw=read_regular(folder/'before.png',limit=2*1024*1024);clean_png(raw)
    expected=request_document({**expected_context,'schema':1,'stage':stage,'action':action,'protocol':PROTOCOL,'terminal_stage':6,
        'legal_identity':legal,'plugin_binary_sha256':plugin,'preceding_receipt_sha256':prior,
        'screenshot_sha256':digest(raw),'display_binding_sha256':digest(read_regular(identity.binding,limit=4096)),'window_identity':win})
    publish(folder/'window-identity.json',encode(win));publish(folder/'request.json',encode(expected))
    while not (folder/'control.json').exists():
        require(proc.poll() is None)
        if time.monotonic()>=deadline:raise TimeoutError('900秒UI总预算耗尽')
        owned.scan();time.sleep(.2)
    approved=validate_control(trust.read_json(folder/'control.json',4096),expected)
    require(time.monotonic()<deadline and proc.poll() is None)
    require(trust.context(root,command,idea)==expected_context and preceding(root,stage,expected_context)==prior)
    verify_plugin(root,idea);require(verify_legal(deadline)==legal)
    require(digest(read_regular(identity.binding,limit=4096))==expected['display_binding_sha256'])
    identity.verify();require(window_probe(identity.metadata['ide']['pid'],action,environment)==win)
    require(time.monotonic()<deadline and proc.poll() is None)
    screen(action,folder/'after.png',expected['screenshot_sha256'],folder/'performed.txt')
    require(read_regular(folder/'performed.txt',limit=64)==(action+'\n').encode())
    after=read_regular(folder/'after.png',limit=2*1024*1024);clean_png(after)
    publish(folder/'receipt.json',encode(receipt_document({**approved,'after_sha256':digest(after),'status':STATUS,'legal_rechecked':True},expected)))

def receive(root,stage):
    stage_number(stage);expected=request_document(trust.read_json(root/f'stage-{stage}/request.json',4096))
    require(expected['stage']==stage and trust.context(root)=={k:expected[k] for k in trust.CONTEXT_FIELDS})
    require(preceding(root,stage,{k:expected[k] for k in trust.CONTEXT_FIELDS})==expected['preceding_receipt_sha256'])
    deadline=read_ui_deadline(root);output=root/f'stage-{stage}/control.json'
    require(not output.exists() and not output.is_symlink())
    while time.monotonic()<deadline:
        value=fetch_control(os.environ['GITHUB_REPOSITORY'],expected['run_id'],expected['run_attempt'],stage,os.environ['GH_TOKEN'],min(5,deadline-time.monotonic()))
        if value is not None:
            validate_control(value,expected);require(time.monotonic()<deadline);publish(output,encode(value));return
        time.sleep(min(2,max(0,deadline-time.monotonic())))
    raise TimeoutError('UI总预算耗尽；未写插件协议动作记录')

def collect(root,stage,run_id,attempt):
    stage_number(stage);folder=root/f'stage-{stage}'
    expected=request_document(trust.read_json(folder/'request.json',4096))
    require(expected['stage']==stage and expected['run_id']==run_id and expected['run_attempt']==attempt)
    require(root.name=='academy-ui-'+run_id+'-'+attempt)
    require(preceding(root,stage,{k:expected[k] for k in trust.CONTEXT_FIELDS})==expected['preceding_receipt_sha256'])
    raw=read_regular(folder/'before.png',limit=2*1024*1024);require(digest(raw)==expected['screenshot_sha256']);clean=clean_png(raw)
    prefix=f'plugin-stage-{stage}'
    mapping={'schema':1,'before_raw_sha256':digest(raw),'before_uploaded_sha256':digest(clean),'after_raw_sha256':None,'after_uploaded_sha256':None}
    files={prefix+'-request.json':encode(expected),prefix+'-before.png':clean,prefix+'-images.json':encode(mapping)}
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
    if phase=='review':files[f'plugin-stage-{stage}-review-target.json']=encode({'protocol':PROTOCOL,'terminal_stage':6,'action':ACTIONS[stage],
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
    deadline=read_ui_deadline(root);require(time.monotonic()<deadline)
    require(window.observe(expected['pid'],ACTIONS[stage])==expected);require(time.monotonic()<deadline)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('mode',choices=['receive','observe-window','verify-window','stage-artifact','complete','legal-body-check'])
    p.add_argument('--deadline',type=float);p.add_argument('--root',type=Path);p.add_argument('--pid',type=int);p.add_argument('--expected',type=Path)
    p.add_argument('--stage',type=int,choices=[5,6]);p.add_argument('--phase',choices=['review','receipt']);p.add_argument('--run-id');p.add_argument('--run-attempt')
    a=p.parse_args()
    if a.mode=='legal-body-check':print(json.dumps(fetch_legal(a.deadline),separators=(',',':')))
    elif a.mode=='receive':receive(a.root,a.stage)
    elif a.mode=='stage-artifact':stage_artifact(a.root,a.stage,a.phase,a.run_id,a.run_attempt)
    elif a.mode=='observe-window':print(json.dumps(window.observe(a.pid,ACTIONS[stage_number(a.stage)]),separators=(',',':')))
    elif a.mode=='verify-window':verify_window(a.root,a.expected)
    else:
        stage_number(a.stage);deadline=read_ui_deadline(a.root)
        while not (a.root/f'stage-{a.stage}/receipt.json').exists():
            if time.monotonic()>=deadline or (a.root/'result.json').exists():raise RuntimeError('插件正常UI动作未完成')
            time.sleep(.2)
        receipt_document(trust.read_json(a.root/f'stage-{a.stage}/receipt.json',4096),request_document(trust.read_json(a.root/f'stage-{a.stage}/request.json',4096)))
