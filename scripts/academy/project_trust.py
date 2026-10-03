"""One visually approved normal GUI click for the sealed current100 validation project."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time
from display_diagnostic import clean_png, digest, encode, json_read, publish
from safe_io import read_regular, validate_directory, new_directory
from ui_control import fetch_control, read_ui_deadline
from trust_window import validate as validate_window

ACTION='TRUST_VALIDATION_PROJECT'
SOURCE_MANIFEST='47153c72424adb49502d5ce2adba18df22a1111c13047813d33950075789b8a8'
COUNTS={'courses':1,'sections':15,'tasks':100,'placeholders':159}
CONTEXT_FIELDS={'run_id','run_attempt','tested_sha','source_tree','source_manifest_sha256',
                'archive_sha256','project_relative_path','project_path_sha256'}
REQUEST_FIELDS=CONTEXT_FIELDS|{'schema','stage','action','screenshot_sha256','display_binding_sha256',
                             'window_identity','stage3_receipt_sha256'}
REVIEW={'dialog':'TRUST_AND_OPEN_VALIDATION','parent_folder_trust_checked':False,
        'scope':'CURRENT_VALIDATION_PROJECT_ONLY','button':'TRUST_PROJECT'}

def require(ok):
    if not ok:raise ValueError('invalid project trust binding')
def token(value,pattern):
    require(type(value) is str and re.fullmatch(pattern,value) is not None);return value
def read_json(path,limit=65536):return json_read(read_regular(path,limit=limit))
def paths(ui_root):
    run_id=token(os.environ.get('GITHUB_RUN_ID'),r'[1-9][0-9]{0,19}')
    attempt=token(os.environ.get('GITHUB_RUN_ATTEMPT'),r'[1-9][0-9]{0,19}')
    temp=Path(os.environ['RUNNER_TEMP']);require(temp.is_absolute());validate_directory(temp)
    require(ui_root==temp/('academy-ui-'+run_id+'-'+attempt));validate_directory(ui_root)
    root=temp/('academy-run-'+run_id+'-'+attempt);validate_directory(root)
    project=root/'validation'
    require(not project.is_symlink())
    if project.exists():validate_directory(project)
    return root,project,root/'backend-interview-academy.zip',run_id,attempt

def context(ui_root,command=None,idea=None):
    root,project,archive,run_id,attempt=paths(ui_root)
    ci=read_json(root/'evidence/source-ci.json',256*1024)
    generation=read_json(root/'evidence/generation.json',256*1024)
    report=read_json(root/'evidence/archive.json');summary=read_json(root/'evidence/summary.json',1024*1024)
    require(ci.get('status')=='PASS' and ci.get('sha')==ci.get('tested_sha')==summary.get('commit'))
    require(summary.get('run_id')==run_id and summary.get('run_attempt')==attempt
            and summary.get('repository')=='weilhuang/backend-interview-labs')
    require(generation.get('status')=='PASS' and generation.get('full_manifest_sha256')==SOURCE_MANIFEST)
    require(all(type(generation.get(k)) is int and generation[k]==v for k,v in COUNTS.items()))
    counts=report.get('counts')
    require(report.get('status')=='PASS' and type(counts) is dict and set(counts)==set(COUNTS)
            and all(type(counts[k]) is int and counts[k]==v for k,v in COUNTS.items()))
    archive_hash=digest(read_regular(archive,limit=128*1024*1024));require(report.get('archive_sha256')==archive_hash)
    if command is not None:
        require(idea is not None and command==[str(idea/'bin/idea'),'validateCourse',str(project),'--archive',str(archive),
                    '--tests','true','--links','true','--output-format','json','--output',str(root/'evidence/official-validation.json')])
    return validate_context({'run_id':run_id,'run_attempt':attempt,'tested_sha':ci['sha'],'source_tree':ci['commit_tree'],
        'source_manifest_sha256':SOURCE_MANIFEST,'archive_sha256':archive_hash,
        'project_relative_path':root.name+'/validation','project_path_sha256':digest(os.fsencode(project))})

def validate_context(value):
    require(type(value) is dict and set(value)==CONTEXT_FIELDS)
    for key in ('run_id','run_attempt'):token(value[key],r'[1-9][0-9]{0,19}')
    for key in ('tested_sha','source_tree'):token(value[key],r'[0-9a-f]{40}')
    for key in ('source_manifest_sha256','archive_sha256','project_path_sha256'):token(value[key],r'[0-9a-f]{64}')
    require(value['source_manifest_sha256']==SOURCE_MANIFEST)
    require(value['project_relative_path']=='academy-run-'+value['run_id']+'-'+value['run_attempt']+'/validation')
    return value

def request_document(value):
    require(type(value) is dict and set(value)==REQUEST_FIELDS)
    validate_context({k:value[k] for k in CONTEXT_FIELDS})
    require(type(value['schema']) is int and value['schema']==1 and type(value['stage']) is int and value['stage']==4)
    require(value['action']==ACTION)
    for key in ('screenshot_sha256','display_binding_sha256','stage3_receipt_sha256'):token(value[key],r'[0-9a-f]{64}')
    validate_window(value['window_identity'])
    return value

def validate_control(value,expected):
    request_document(expected)
    require(type(value) is dict and set(value)==REQUEST_FIELDS|{'visual_review'})
    review=value['visual_review'];require(type(review) is dict and set(review)==set(REVIEW))
    require(type(review['parent_folder_trust_checked']) is bool and review==REVIEW)
    require({k:value[k] for k in REQUEST_FIELDS}==expected)
    request_document({k:value[k] for k in REQUEST_FIELDS})
    return value

def window_probe(pid,environment,runner=None):
    # Isolated read-only metadata process bounds Xlib calls even if the server stalls.
    args=[sys.executable,__file__,'observe-window','--pid',str(pid)]
    result=(runner or subprocess.run)(args,env=environment,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,timeout=2,check=True)
    require(len(result.stdout)<=2048);return validate_window(json_read(result.stdout))

def checkpoint(root,proc,screen,identity,owned,deadline,command,idea,environment,runner=None):
    """No automatic approval: prepare, wait, revalidate, then one normal button click."""
    require(time.monotonic()<deadline and proc.poll() is None)
    expected_context=context(root,command,idea)
    stage=root/'stage-4';new_directory(stage)
    before=stage/'before.png';identity.verify()
    window=window_probe(identity.metadata['ide']['pid'],environment,**({'runner':runner} if runner else {}))
    screen('SNAPSHOT',before);identity.verify()
    require(window_probe(identity.metadata['ide']['pid'],environment,**({'runner':runner} if runner else {}))==window)
    raw=read_regular(before,limit=2*1024*1024);clean_png(raw)
    receipt=read_regular(root/'stage-3/receipt.json',limit=4096);r=json_read(receipt)
    require(r.get('run_id')==expected_context['run_id'] and r.get('run_attempt')==expected_context['run_attempt']
            and type(r.get('stage')) is int and r['stage']==3
            and r.get('action')=='DECLINE_USAGE' and r.get('status')=='UI_ACTION_PERFORMED_NOT_ACCEPTANCE')
    expected=request_document({**expected_context,'schema':1,'stage':4,'action':ACTION,
        'screenshot_sha256':digest(raw),'display_binding_sha256':digest(read_regular(identity.binding,limit=4096)),
        'window_identity':window,'stage3_receipt_sha256':digest(receipt)})
    publish(stage/'window-identity.json',encode(window))
    publish(stage/'review-target.json',encode({'action':ACTION,'fixed_target':[596,517],'screen':[1280,900],
        'required_visual_review':REVIEW,'requirement':'Fresh screenshot must show only the validation project Trust dialog, parent-folder checkbox unchecked, and target inside Trust Project. Otherwise do not approve.'}))
    publish(stage/'request.json',encode(expected))
    while not (stage/'control.json').exists():
        require(proc.poll() is None)
        if time.monotonic()>=deadline:raise TimeoutError('900秒UI总预算耗尽')
        owned.scan();time.sleep(.2)
    approved=validate_control(read_json(stage/'control.json',4096),expected)
    require(time.monotonic()<deadline and proc.poll() is None)
    require(context(root,command,idea)==expected_context)
    require(digest(read_regular(identity.binding,limit=4096))==expected['display_binding_sha256'])
    identity.verify();require(window_probe(identity.metadata['ide']['pid'],environment,**({'runner':runner} if runner else {}))==window)
    # The existing Java Robot helper compares the full image twice, rechecks owned
    # display/process identity, and checks this same X11 window immediately before clicking.
    screen(ACTION,stage/'after.png',expected['screenshot_sha256'],stage/'performed.txt')
    require(read_regular(stage/'performed.txt',limit=64)==(ACTION+'\n').encode())
    after=read_regular(stage/'after.png',limit=2*1024*1024);clean_png(after)
    publish(stage/'receipt.json',encode({**approved,'after_sha256':digest(after),
        'status':'UI_ACTION_PERFORMED_NOT_COURSE_ACCEPTANCE'}))

def receive(root):
    expected=request_document(read_json(root/'stage-4/request.json',4096))
    require(context(root)=={k:expected[k] for k in CONTEXT_FIELDS})
    deadline=read_ui_deadline(root);output=root/'stage-4/control.json'
    require(not output.exists() and not output.is_symlink())
    while time.monotonic()<deadline:
        value=fetch_control(os.environ['GITHUB_REPOSITORY'],expected['run_id'],expected['run_attempt'],4,os.environ['GH_TOKEN'],min(5,deadline-time.monotonic()))
        if value is not None:
            validate_control(value,expected)
            require(time.monotonic()<deadline)
            publish(output,encode(value));return
        time.sleep(min(2,max(0,deadline-time.monotonic())))
    raise TimeoutError('UI 总预算耗尽；未写信任动作记录')

def collect(root,run_id,attempt):
    """Strict exact-file projection for public fourth-stage evidence."""
    expected=request_document(read_json(root/'stage-4/request.json',4096))
    require(expected['run_id']==run_id and expected['run_attempt']==attempt)
    require(root.name=='academy-ui-'+run_id+'-'+attempt)
    raw=read_regular(root/'stage-4/before.png',limit=2*1024*1024);require(digest(raw)==expected['screenshot_sha256'])
    clean=clean_png(raw);images={'schema':1,'before_raw_sha256':digest(raw),'before_uploaded_sha256':digest(clean),
                               'after_raw_sha256':None,'after_uploaded_sha256':None}
    result={'project-trust-request.json':encode(expected),'project-trust-before.png':clean,
            'project-trust-images.json':encode(images)}
    try:receipt=read_json(root/'stage-4/receipt.json',4096)
    except FileNotFoundError:return result
    require(type(receipt) is dict and set(receipt)==REQUEST_FIELDS|{'visual_review','after_sha256','status'})
    validate_control({k:receipt[k] for k in REQUEST_FIELDS|{'visual_review'}},expected)
    require(receipt['status']=='UI_ACTION_PERFORMED_NOT_COURSE_ACCEPTANCE')
    token(receipt['after_sha256'],r'[0-9a-f]{64}')
    after=read_regular(root/'stage-4/after.png',limit=2*1024*1024);require(digest(after)==receipt['after_sha256'])
    clean_after=clean_png(after);images.update(after_raw_sha256=digest(after),after_uploaded_sha256=digest(clean_after))
    result.update({'project-trust-receipt.json':encode(receipt),'project-trust-after.png':clean_after,
                   'project-trust-images.json':encode(images)})
    return result

def stage_artifact(root,phase,run_id,attempt):
    require(phase in ('review','receipt'))
    validate_directory(root)
    require(root.name=='academy-ui-'+token(run_id,r'[1-9][0-9]{0,19}')+'-'+token(attempt,r'[1-9][0-9]{0,19}'))
    output=root/('trust-'+phase+'-artifact');new_directory(output)
    if phase=='review':require(not (root/'stage-4/receipt.json').exists())
    files=collect(root,run_id,attempt)
    # All names and bytes come from strict current-request projection, never arbitrary raw JSON.
    for name,raw in files.items():publish(output/name,raw)
    if phase=='review':
        publish(output/'project-trust-review-target.json',encode({'action':ACTION,'fixed_target':[596,517],
                'screen':[1280,900],'required_visual_review':REVIEW}))

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('mode',choices=['receive','observe-window','verify-window','stage-artifact'])
    parser.add_argument('--root',type=Path);parser.add_argument('--pid',type=int);parser.add_argument('--expected',type=Path)
    parser.add_argument('--phase',choices=['review','receipt']);parser.add_argument('--run-id');parser.add_argument('--run-attempt')
    args=parser.parse_args()
    if args.mode=='receive':receive(args.root)
    elif args.mode=='stage-artifact':stage_artifact(args.root,args.phase,args.run_id,args.run_attempt)
    else:
        from trust_window import observe
        if args.mode=='observe-window':print(json.dumps(observe(args.pid),separators=(',',':')))
        else:
            expected=validate_window(read_json(args.expected,2048))
            require(args.expected==args.root/'stage-4/window-identity.json')
            request=request_document(read_json(args.root/'stage-4/request.json',4096))
            validate_control(read_json(args.root/'stage-4/control.json',4096),request)
            require(context(args.root)=={k:request[k] for k in CONTEXT_FIELDS})
            require(expected==request['window_identity'] and time.monotonic()<read_ui_deadline(args.root))
            require(observe(expected['pid'])==expected)
