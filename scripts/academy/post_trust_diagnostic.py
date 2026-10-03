"""One passive post-Trust observation; never native acceptance or a new UI action."""
from datetime import datetime, timezone
import math
import os
from pathlib import Path
import re
import time
from display_diagnostic import clean_png, digest, encode, json_read, publish
from safe_io import read_regular, validate_directory, new_directory
from project_trust import CONTEXT_FIELDS, REQUEST_FIELDS, context, request_document, validate_control
import post_trust_stacks as stacks

REPORT='post-trust-diagnostic.json'
PNG='post-trust-diagnostic.png'
MAPPING='post-trust-images.json'
ANCHOR='post-trust-anchor.json'
BUDGET_OWNER='ui-budget-owner.json'
MAX_REPORT=256*1024
LIMIT_SECONDS=90
FALLBACK_SECONDS=60
STATUSES={'COLLECTED_NOT_ACCEPTANCE','PARTIAL_NOT_ACCEPTANCE','UNAVAILABLE_NOT_ACCEPTANCE'}
TRIGGERS={'FIRST_STABLE_POST_TRUST','FALLBACK_60_SECONDS','OBSERVER_DEADLINE','IDE_EXITED','SCAN_UNAVAILABLE'}
SCREEN_STATUSES={'CAPTURED_NOT_ACCEPTANCE','UNAVAILABLE_DEADLINE','UNAVAILABLE_IDE_EXITED','UNAVAILABLE_IDENTITY_OR_CAPTURE'}

def require(ok):
    if not ok:raise ValueError('invalid post-Trust diagnostic')
def token(value,pattern):
    require(type(value) is str and re.fullmatch(pattern,value) is not None);return value
def integer(value,low,high):
    require(type(value) is int and low<=value<=high);return value
def number(value,low,high):
    require(type(value) in (int,float) and math.isfinite(value) and low<=value<=high);return value
def enum(value,choices):
    require(type(value) is str and value in choices);return value
def raw_json(path,limit=MAX_REPORT):return json_read(read_regular(path,limit=limit))
def utc():return datetime.now(timezone.utc).isoformat(timespec='milliseconds')

def budget_document(value):
    """Original fixed supervisor budget; this is not GUI-process authority."""
    from project_trust import validate_context
    from ui_control import checked_budget, UI_BUDGET_SECONDS
    require(type(value) is dict and set(value)=={'schema_version','kind','context','record','record_sha256'})
    integer(value['schema_version'],1,1);require(value['kind']=='DISPLAY_SUPERVISOR_UI_BUDGET_NOT_ACCEPTANCE')
    validate_context(value['context']);token(value['record_sha256'],r'[0-9a-f]{64}')
    record=value['record'];require(type(record) is dict and type(record.get('owner')) is dict)
    owner=record['owner'];require(set(owner)=={'pid','ppid','uid','pgrp','session','start_time'})
    for key in ('pid','ppid','uid','pgrp','session'):integer(owner[key],0 if key=='uid' else 1,2**31-1)
    token(owner['start_time'],r'[0-9]{1,20}')
    deadline=number(record.get('monotonic_deadline'),0,10**10)
    require(checked_budget(record,UI_BUDGET_SECONDS,owner)==deadline)
    return value

def bind_budget_owner(root):
    """Called once at deadline creation by the live display supervisor itself."""
    from ui_control import checked_budget, UI_BUDGET_SECONDS
    from ui_session import process_info
    raw=read_regular(root/'ui-deadline.json',limit=4096);record=json_read(raw)
    observed=process_info(os.getpid())
    deadline=checked_budget(record,UI_BUDGET_SECONDS,observed)
    require(int(observed['start_time'])/os.sysconf('SC_CLK_TCK')<=time.monotonic()<deadline)
    value=budget_document({'schema_version':1,'kind':'DISPLAY_SUPERVISOR_UI_BUDGET_NOT_ACCEPTANCE',
        'context':context(root),'record':record,'record_sha256':digest(raw)})
    publish(root/BUDGET_OWNER,encode(value))

def checked_budget_owner(root,*,live=False):
    from ui_control import checked_budget, UI_BUDGET_SECONDS
    raw=read_regular(root/BUDGET_OWNER,limit=8192);value=budget_document(json_read(raw))
    record_raw=read_regular(root/'ui-deadline.json',limit=4096)
    require(digest(record_raw)==value['record_sha256'] and json_read(record_raw)==value['record'])
    require(value['context']==context(root))
    if live:
        from ui_control import checked_live_budget
        deadline=checked_live_budget(value['record'],UI_BUDGET_SECONDS)
        require(time.monotonic()<deadline)
    return value,digest(raw)

def owner_matches_gui(budget,identity):
    owner=budget['record']['owner']
    require(identity['ppid']==owner['pid'] and identity['uid']==owner['uid'])
    require(int(identity['start_time'])>=int(owner['start_time']))

def collect_budget_owner(root,run_id,attempt):
    """Retain the original typed budget even if a later diagnostic is invalid."""
    root=Path(root);validate_directory(root)
    require(root.name=='academy-ui-'+token(run_id,r'[1-9][0-9]{0,19}')+'-'+token(attempt,r'[1-9][0-9]{0,19}'))
    value,_=checked_budget_owner(root)
    require(value['context']['run_id']==run_id and value['context']['run_attempt']==attempt)
    return encode(value)

def anchor_document(value):
    fields={'schema_version','kind','context','trust_receipt_sha256','display_binding_sha256',
            'anchor_wall_ns','anchor_monotonic','effective_deadline','ui_deadline','budget_owner_sha256'}
    require(type(value) is dict and set(value)==fields)
    integer(value['schema_version'],1,1);require(value['kind']=='POST_TRUST_ANCHOR_NOT_ACCEPTANCE')
    from project_trust import validate_context
    validate_context(value['context'])
    for key in ('trust_receipt_sha256','display_binding_sha256','budget_owner_sha256'):token(value[key],r'[0-9a-f]{64}')
    integer(value['anchor_wall_ns'],0,2**63-1)
    start=number(value['anchor_monotonic'],0,10**10);ui=number(value['ui_deadline'],0,10**10)
    require(value['effective_deadline']==max(start,min(start+LIMIT_SECONDS,ui)))
    number(value['effective_deadline'],start,start+LIMIT_SECONDS)
    return value

def checked_receipt(root):
    raw=read_regular(root/'stage-4/receipt.json',limit=4096);receipt=json_read(raw)
    require(type(receipt) is dict and set(receipt)==REQUEST_FIELDS|{'visual_review','after_sha256','status'})
    request=request_document(raw_json(root/'stage-4/request.json',4096))
    validate_control({k:receipt[k] for k in REQUEST_FIELDS|{'visual_review'}},request)
    require(receipt['status']=='UI_ACTION_PERFORMED_NOT_COURSE_ACCEPTANCE')
    token(receipt['after_sha256'],r'[0-9a-f]{64}')
    require(digest(read_regular(root/'stage-4/after.png',limit=2*1024*1024))==receipt['after_sha256'])
    require(context(root)=={key:request[key] for key in CONTEXT_FIELDS})
    require(digest(read_regular(root/'display-binding.properties',limit=4096))==request['display_binding_sha256'])
    return request,digest(raw)

def bound_ui_identity(root):
    values={}
    for line in read_regular(root/'display-binding.properties',limit=4096).decode('utf-8').splitlines():
        key,separator,value=line.partition('=')
        if key not in {'ide.pid','ide.ppid','ide.uid','ide.pgrp','ide.session','ide.start_time'}:continue
        require(separator=='=' and key not in values);token(value,r'[0-9]{1,20}');values[key]=value
    require(len(values)==6)
    return {key.split('.')[1]:(value if key=='ide.start_time' else integer(int(value),0,2**31-1)) for key,value in values.items()}

def validate_document(value):
    fields={'schema_version','kind','status','context','trust_receipt_sha256','display_binding_sha256','ui_identity','anchor_sha256',
            'anchor_wall_ns','anchor_monotonic','effective_deadline','observer_limit_seconds','fallback_seconds',
            'capture_trigger','scan_count','elapsed_seconds','at_utc','screenshot_status','screenshot_sha256',
            'stacks','stack_availability','dump_process_attribution','budget_owner','budget_owner_sha256'}
    require(type(value) is dict and set(value)==fields)
    integer(value['schema_version'],1,1);require(value['kind']=='POST_TRUST_PASSIVE_DIAGNOSTIC_NOT_ACCEPTANCE')
    enum(value['status'],STATUSES)
    from project_trust import validate_context
    validate_context(value['context'])
    for key in ('trust_receipt_sha256','display_binding_sha256','anchor_sha256','budget_owner_sha256'):token(value[key],r'[0-9a-f]{64}')
    budget=budget_document(value['budget_owner']);require(budget['context']==value['context'])
    require(digest(encode(budget))==value['budget_owner_sha256'])
    identity=value['ui_identity'];require(type(identity) is dict and set(identity)=={'pid','ppid','uid','pgrp','session','start_time'})
    for key in ('pid','ppid','uid','pgrp','session'):integer(identity[key],0 if key in ('uid','ppid') else 1,2**31-1)
    token(identity['start_time'],r'[0-9]{1,20}')
    owner_matches_gui(budget,identity)
    integer(value['anchor_wall_ns'],0,2**63-1)
    start=number(value['anchor_monotonic'],0,10**10);end=number(value['effective_deadline'],start,start+LIMIT_SECONDS)
    owner_born=int(budget['record']['owner']['start_time'])/os.sysconf('SC_CLK_TCK')
    require(owner_born<=start<budget['record']['monotonic_deadline'])
    require(end==min(start+LIMIT_SECONDS,budget['record']['monotonic_deadline']))
    integer(value['observer_limit_seconds'],LIMIT_SECONDS,LIMIT_SECONDS);integer(value['fallback_seconds'],FALLBACK_SECONDS,FALLBACK_SECONDS)
    enum(value['capture_trigger'],TRIGGERS);integer(value['scan_count'],0,91)
    # A late scheduling observation must be truthful, but cannot authorize late reads/captures.
    number(value['elapsed_seconds'],0,3600)
    token(value['at_utc'],r'[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9:.]{8,20}\+00:00')
    enum(value['screenshot_status'],SCREEN_STATUSES)
    if value['screenshot_sha256'] is not None:token(value['screenshot_sha256'],r'[0-9a-f]{64}')
    require((value['screenshot_status']=='CAPTURED_NOT_ACCEPTANCE')==(value['screenshot_sha256'] is not None))
    enum(value['stack_availability'],{'DOCUMENT_AVAILABLE','UNAVAILABLE_DEADLINE','UNAVAILABLE_CAPTURE'})
    require(value['dump_process_attribution']=='NOT_IDENTIFIED_NO_JVM_ATTACH')
    if value['stacks'] is not None:
        require(value['stack_availability']=='DOCUMENT_AVAILABLE')
        clean=stacks.validate_document(value['stacks']);require(clean==value['stacks'])
        require(clean['anchor_wall_ns']==value['anchor_wall_ns'])
    else:require(value['stack_availability']!='DOCUMENT_AVAILABLE')
    captured=value['screenshot_status']=='CAPTURED_NOT_ACCEPTANCE'
    available=value['stack_availability']=='DOCUMENT_AVAILABLE'
    complete=available and value['stacks']['status']=='COLLECTED_NOT_ACCEPTANCE'
    expected='COLLECTED_NOT_ACCEPTANCE' if captured and complete else 'PARTIAL_NOT_ACCEPTANCE' if captured or available else 'UNAVAILABLE_NOT_ACCEPTANCE'
    require(value['status']==expected)
    require(len(encode(value))<=MAX_REPORT)
    return value

class Observer:
    """Ticked by the existing owned UI loop; one immutable deadline, one result."""
    def __init__(self,root,identity,ui_deadline):
        self.root=Path(root);request,receipt_sha=checked_receipt(self.root)
        identity.verify()
        require(identity.metadata['ide']==bound_ui_identity(self.root))
        budget,budget_sha=checked_budget_owner(self.root,live=True)
        owner_matches_gui(budget,identity.metadata['ide'])
        self.run=self.root.parent/('academy-run-'+request['run_id']+'-'+request['run_attempt'])
        self.start=time.monotonic();self.anchor=time.time_ns()
        require(type(ui_deadline) in (int,float) and math.isfinite(ui_deadline))
        require(ui_deadline==budget['record']['monotonic_deadline'])
        self.deadline=max(self.start,min(self.start+LIMIT_SECONDS,ui_deadline))
        self.next_scan=self.start;self.previous=None;self.current=None;self.first_id=None;self.done=False
        self.value={'schema_version':1,'kind':'POST_TRUST_PASSIVE_DIAGNOSTIC_NOT_ACCEPTANCE',
            'status':'UNAVAILABLE_NOT_ACCEPTANCE','context':{k:request[k] for k in CONTEXT_FIELDS},
            'trust_receipt_sha256':receipt_sha,'display_binding_sha256':request['display_binding_sha256'],
            'ui_identity':dict(identity.metadata['ide']),'anchor_wall_ns':self.anchor,'anchor_monotonic':self.start,
            'budget_owner':budget,'budget_owner_sha256':budget_sha,
            'effective_deadline':self.deadline,'observer_limit_seconds':LIMIT_SECONDS,'fallback_seconds':FALLBACK_SECONDS,
            'capture_trigger':'OBSERVER_DEADLINE','scan_count':0,'elapsed_seconds':0,'at_utc':utc(),
            'screenshot_status':'UNAVAILABLE_DEADLINE','screenshot_sha256':None,'stacks':None,
            'stack_availability':'UNAVAILABLE_CAPTURE','dump_process_attribution':'NOT_IDENTIFIED_NO_JVM_ATTACH'}
        anchor={k:self.value[k] for k in ('context','trust_receipt_sha256','display_binding_sha256',
                'anchor_wall_ns','anchor_monotonic','effective_deadline')}
        anchor.update(schema_version=1,kind='POST_TRUST_ANCHOR_NOT_ACCEPTANCE',ui_deadline=ui_deadline,budget_owner_sha256=budget_sha)
        raw=encode(anchor_document(anchor));publish(self.root/ANCHOR,raw);self.value['anchor_sha256']=digest(raw)

    def tick(self,proc,screen,identity):
        if self.done:return
        now=time.monotonic()
        if now>=self.deadline:return self.capture('OBSERVER_DEADLINE',proc,screen,identity)
        if proc.poll() is not None:return self.capture('IDE_EXITED',proc,screen,identity)
        if now-self.start>=FALLBACK_SECONDS:return self.capture('FALLBACK_60_SECONDS',proc,screen,identity)
        if now<self.next_scan:return
        self.next_scan=now+1
        if self.value['scan_count']>=91:return self.capture('OBSERVER_DEADLINE',proc,screen,identity)
        try:
            self.current=stacks.scan(self.run,self.anchor,observed=time.time_ns(),deadline=min(self.deadline,now+1))
            self.value['scan_count']+=1
            stable=stacks.stable_post_ids(self.previous,self.current) if self.previous is not None else ()
            self.previous=self.current
            if stable:
                self.first_id=stable[0]
                return self.capture('FIRST_STABLE_POST_TRUST',proc,screen,identity)
        except InterruptedError:raise
        except Exception:return self.capture('SCAN_UNAVAILABLE',proc,screen,identity)

    def capture(self,trigger,proc,screen,identity):
        require(not self.done);self.done=True;self.value['capture_trigger']=trigger
        try:
            if time.monotonic()>=self.deadline:self.value['stack_availability']='UNAVAILABLE_DEADLINE'
            else:
                scan_result=self.current if trigger=='FIRST_STABLE_POST_TRUST' else None
                if scan_result is None:self.value['scan_count']+=1
                require(self.value['scan_count']<=91)
                self.value['stacks']=stacks.capture(self.run,self.anchor,first_observed_id=self.first_id,
                    scan_result=scan_result,deadline=self.deadline)
                self.value['stack_availability']='DOCUMENT_AVAILABLE'
        except InterruptedError:raise
        except Exception:self.value['stacks']=None;self.value['stack_availability']='UNAVAILABLE_CAPTURE'
        try:
            if proc.poll() is not None:self.value['screenshot_status']='UNAVAILABLE_IDE_EXITED'
            elif time.monotonic()>=self.deadline:self.value['screenshot_status']='UNAVAILABLE_DEADLINE'
            else:
                identity.verify()
                require(identity.metadata['ide']==self.value['ui_identity'])
                require(digest(read_regular(identity.binding,limit=4096))==self.value['display_binding_sha256'])
                screen('SNAPSHOT',self.root/PNG,diagnostic_deadline=self.deadline)
                identity.verify();raw=read_regular(self.root/PNG,limit=2*1024*1024);clean_png(raw)
                self.value['screenshot_sha256']=digest(raw);self.value['screenshot_status']='CAPTURED_NOT_ACCEPTANCE'
        except InterruptedError:raise
        except Exception:
            if self.value['screenshot_sha256'] is None:self.value['screenshot_status']='UNAVAILABLE_IDENTITY_OR_CAPTURE'
        finally:
            self.value['elapsed_seconds']=max(0,round(time.monotonic()-self.start,3));self.value['at_utc']=utc()
        captured=self.value['screenshot_status']=='CAPTURED_NOT_ACCEPTANCE';projected=self.value['stack_availability']=='DOCUMENT_AVAILABLE'
        complete=projected and self.value['stacks'].get('status')=='COLLECTED_NOT_ACCEPTANCE'
        self.value['status']='COLLECTED_NOT_ACCEPTANCE' if captured and complete else 'PARTIAL_NOT_ACCEPTANCE' if captured or projected else 'UNAVAILABLE_NOT_ACCEPTANCE'
        publish(self.root/REPORT,encode(validate_document(self.value)))

def collect(root,run_id,attempt):
    root=Path(root);validate_directory(root)
    value=validate_document(raw_json(root/REPORT))
    require(root.name=='academy-ui-'+token(run_id,r'[1-9][0-9]{0,19}')+'-'+token(attempt,r'[1-9][0-9]{0,19}'))
    require(value['context']['run_id']==run_id and value['context']['run_attempt']==attempt)
    request,receipt_sha=checked_receipt(root)
    anchor_raw=read_regular(root/ANCHOR,limit=8192);anchor=anchor_document(json_read(anchor_raw))
    require(digest(anchor_raw)==value['anchor_sha256'])
    require(all(value[k]==anchor[k] for k in ('context','trust_receipt_sha256','display_binding_sha256',
                    'anchor_wall_ns','anchor_monotonic','effective_deadline')))
    require(value['context']=={k:request[k] for k in CONTEXT_FIELDS} and value['trust_receipt_sha256']==receipt_sha
            and value['display_binding_sha256']==request['display_binding_sha256'])
    require(value['ui_identity']['pid']==request['window_identity']['pid'])
    require(value['ui_identity']==bound_ui_identity(root))
    budget,budget_sha=checked_budget_owner(root)
    require(value['budget_owner']==budget and value['budget_owner_sha256']==anchor['budget_owner_sha256']==budget_sha)
    owner_matches_gui(budget,value['ui_identity'])
    born=int(budget['record']['owner']['start_time'])/os.sysconf('SC_CLK_TCK')
    require(anchor['ui_deadline']==budget['record']['monotonic_deadline'] and born<=anchor['anchor_monotonic']<anchor['ui_deadline'])
    result={REPORT:encode(value)}
    if value['screenshot_status']=='CAPTURED_NOT_ACCEPTANCE':
        raw=read_regular(root/PNG,limit=2*1024*1024);require(digest(raw)==value['screenshot_sha256']);clean=clean_png(raw)
        result[PNG]=clean;result[MAPPING]=encode({'schema_version':1,'original_sha256':digest(raw),'uploaded_sha256':digest(clean)})
    return result

def wait_collect(root,run_id,attempt):
    from ui_control import read_ui_deadline
    root=Path(root);validate_directory(root);output=root/'post-trust-artifact';new_directory(output)
    if (root/REPORT).exists():
        # A finished immutable observation can be collected after its owner exits;
        # no new screenshot, file-body read or process authority is granted here.
        for name,raw in collect(root,run_id,attempt).items():publish(output/name,raw)
        return
    # This waiter consumes the owner's fixed anchor, never granting another 90s window.
    initialization_deadline=min(read_ui_deadline(root),time.monotonic()+2)
    while not (root/ANCHOR).exists():
        if (root/'result.json').exists() or time.monotonic()>=initialization_deadline:raise TimeoutError('post-Trust anchor unavailable')
        time.sleep(.05)
    anchor=anchor_document(raw_json(root/ANCHOR,8192));deadline=min(read_ui_deadline(root),anchor['effective_deadline'])
    while not (root/REPORT).exists():
        if (root/'result.json').exists() or time.monotonic()>=deadline:raise TimeoutError('post-Trust diagnostic unavailable')
        time.sleep(.2)
    for name,raw in collect(root,run_id,attempt).items():publish(output/name,raw)

if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser();parser.add_argument('--root',type=Path,required=True)
    parser.add_argument('--run-id',required=True);parser.add_argument('--run-attempt',required=True)
    args=parser.parse_args();wait_collect(args.root,args.run_id,args.run_attempt)
