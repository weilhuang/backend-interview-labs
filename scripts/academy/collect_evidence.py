#!/usr/bin/env python3
"""Copy only bounded no-follow evidence into a new, disjoint artifact directory."""
import argparse
import builtins
import json
from pathlib import Path
import re
from thread_diagnostics import NAME as THREAD_NAME, MAX_OUTPUT as THREAD_LIMIT, strict_json as thread_json, validate_document as thread_document
from display_diagnostic import collect as collect_display, REPORT_NAME as DISPLAY_REPORT
from project_trust import collect as collect_project_trust
from plugin_agreement import collect as collect_plugin_agreement
from profile_control import collect as collect_profile_control
from restart_session import collect as collect_restart_result
from post_trust_diagnostic import collect as collect_post_trust, REPORT as POST_TRUST_REPORT, collect_budget_owner, BUDGET_OWNER
from safe_io import absolute, new_directory, read_regular, validate_directory, write_new
NAMES={'summary.json','toolchain.json','source-ci.json','generation.json','source-contract.json',
       'archive.json','author-changes.json','student-import.json','educator-import.json',
       'student-wrapper-diagnostic.json','educator-wrapper-diagnostic.json',
       'official-validation.json','validation-gate.json','SHA256SUMS','generation.log','failure.log',
       'export.stdout.log','export.stderr.log','validate.stdout.log','validate.stderr.log',
       'export-idea.log','validate-idea.log','export-idea-pretermination.log','validate-idea-pretermination.log','gradle-jvm.jsonl','gradle-jvm-gate.json','unified-source-validation.json','release-gate.json'}
NAMES.add(THREAD_NAME)
BOOTSTRAP_NAMES={'source-ci.json','bootstrap.json','install.log','go-bootstrap.json'}
SUPERVISOR_NAMES={'result.json':'supervisor-result.json','launch-result.json':'supervisor-launch.json',
                  'cleanup-result.json':'supervisor-cleanup.json','worker.stdout.log':'supervisor-worker.stdout.log',
                  'worker.stderr.log':'supervisor-worker.stderr.log','supervisor.log':'supervisor.log'}
SUPERVISOR_LOG_LIMIT=32*1024
SUPERVISOR_JSON_LIMIT=16*1024
MAX_FILE=4*1024*1024
OPERATIONS={'INITIALIZE','OPEN_WORKER_STREAMS','SPAWN_CHILD','REGISTER_ROOT','POLL_CHILD','SCAN_OWNED',
            'CHECK_DEADLINE','CHILD_EXIT_OBSERVED','SPAWN_SUPERVISOR','REGISTER_SUPERVISOR','WRITE_BUDGET',
            'AWAIT_STAGE_1','STOP_REGISTERED_SET','REAP_CHILD','CLEANUP_SUPERVISOR'}
DIAGNOSTIC_CODES={'UNCLASSIFIED_EXCEPTION','OWNERSHIP_UNVERIFIED','PROCESS_METADATA_LIMIT','REGISTRATION_DEADLINE',
                  'CHILD_ENUMERATION_BUDGET','CHILD_METADATA_LIMIT','CHILD_COUNT_LIMIT','REGISTERED_COUNT_LIMIT',
                  'REGISTERED_CLEANUP_INCOMPLETE','CANCELLED','OUTER_DEADLINE','INITIALIZATION_DEADLINE'}
EXCEPTION_TYPES={name for name,value in vars(builtins).items() if isinstance(value,type) and issubclass(value,BaseException)} | {'GateError','BoundaryError','TimeoutExpired','JSONDecodeError','UnknownException'}
STATUSES={'result.json':{'PASS','FAILED'},'launch-result.json':{'CHECKPOINT_REACHED_NOT_ACCEPTANCE','FAILED'},
          'cleanup-result.json':{'UNKNOWN','COMMAND_COMPLETED_NOT_CHILD_CLEANUP_PROOF','FAILED'}}

def enum_value(value,choices):
    if type(value) is not str or value not in choices:raise ValueError('invalid diagnostic enum')
    return value

def optional_integer(value,low,high):
    if value is None:return None
    if type(value) is not int or not low<=value<=high:raise ValueError('invalid diagnostic integer')
    return value

def supervisor_json(data):
    def unique(pairs):
        result={}
        for key,value in pairs:
            if key in result:raise ValueError('duplicate supervisor diagnostic key')
            result[key]=value
        return result
    def invalid_constant(value):raise ValueError('nonfinite supervisor diagnostic number')
    return json.loads(data,object_pairs_hook=unique,parse_constant=invalid_constant)

def supervisor_document(value,source_name):
    """Only these typed scalar facts may cross the public artifact boundary."""
    if type(value) is not dict:raise ValueError('supervisor diagnostic must be an object')
    if type(value.get('schema_version')) is not int or value['schema_version']!=1:raise ValueError('invalid supervisor schema')
    result={'schema_version':1,'status':enum_value(value.get('status'),STATUSES[source_name])}
    for key in ('exit_code','registered_process_count'):
        if key in value:result[key]=optional_integer(value[key],-127 if key=='exit_code' else 0,255 if key=='exit_code' else 512)
    if 'cleanup_verified' in value:
        item=value['cleanup_verified']
        if item is not None and type(item) is not bool:raise ValueError('invalid cleanup boolean')
        result['cleanup_verified']=item
    enums={'operation':OPERATIONS,'cleanup_scope':{'REGISTERED_SET_ONLY','SUPERVISOR_ONLY'},
           'termination':{'UNKNOWN','CHILD_EXIT','SUPERVISOR_EXCEPTION'},
           'observation':{'UNKNOWN','NO_SUPERVISOR_IDENTITY','SUPERVISOR_IDENTITY_NOT_LIVE','SUPERVISOR_EXIT_OBSERVED'},
           'error':EXCEPTION_TYPES,'cleanup_error':EXCEPTION_TYPES|{'OWNERSHIP_UNVERIFIED'}}
    for key,choices in enums.items():
        if key in value:result[key]=enum_value(value[key],choices)
    for key in ('error_details','cleanup_error_details'):
        if key not in value:continue
        item=value[key]
        if type(item) is not dict:raise ValueError('invalid diagnostic details')
        result[key]={'operation':enum_value(item.get('operation'),OPERATIONS),
                     'exception_type':enum_value(item.get('exception_type'),EXCEPTION_TYPES),
                     'code':enum_value(item.get('code'),DIAGNOSTIC_CODES)}
        if 'errno' in item:result[key]['errno']=optional_integer(item['errno'],1,4095)
    if source_name=='result.json':
        result.setdefault('exit_code',None);result.setdefault('cleanup_verified',None)
    return result

def verified_supervisor_success(value,job_status,cleanup_exit):
    return (type(value) is dict and type(value.get('schema_version')) is int and value['schema_version']==1
            and value.get('status')=='PASS' and type(value.get('exit_code')) is int and value['exit_code']==0
            and value.get('cleanup_verified') is True and value.get('cleanup_scope')=='REGISTERED_SET_ONLY'
            and value.get('termination')=='CHILD_EXIT' and value.get('operation')=='CHILD_EXIT_OBSERVED'
            and type(value.get('registered_process_count')) is int and 1<=value['registered_process_count']<=512
            and not any(key in value for key in ('error','error_details','cleanup_error','cleanup_error_details'))
            and type(job_status) is str and job_status=='success' and type(cleanup_exit) is int and cleanup_exit==0)

SENSITIVE_KEY = re.compile(r'(?i)(?:[a-z0-9]+[_-])*(?:authorization|password|passwd|secret|token|api[_-]?key|cookie|credentials?|private[_-]?key)(?:[_-][a-z0-9]+)*')


def sanitize_text(text):
    text=re.sub(r'-----BEGIN [A-Z ]*PRIVATE KEY-----.*?(?:-----END [A-Z ]*PRIVATE KEY-----|$)', '[private key redacted]', text, flags=re.S)
    text=re.sub(r'(https?://)[^/\s@]+@',r'\1[redacted]@',text)
    text=re.sub(r'(https?://[^\s?]+)\?[^\s]+',r'\1?[query redacted]',text)
    text=re.sub(r'(?im)((?:set-)?cookie\s*:\s*)[^\r\n]+',r'\1[redacted]',text)
    # Quoted JSON diagnostics and shell/environment assignments may contain spaces.
    text=re.sub(r'(?i)(["\'](?:[a-z0-9]+[_-])*(?:password|passwd|secret|token|api[_-]?key|cookie|authorization|credentials?)(?:[_-][a-z0-9]+)*["\']\s*:\s*)["\'][^"\']*["\']',r'\1"[redacted]"',text)
    text=re.sub(r'(?i)((?:proxy-)?authorization\s*[:=]\s*)(?:(?:Bearer|Basic)\s+)?[^\r\n,;]+',r'\1[redacted]',text)
    text=re.sub(r'(?i)((?:[a-z0-9]+[_-])*(?:password|passwd|secret|token|api[_-]?key|cookie|credentials?)(?:[_-][a-z0-9]+)*\s*[:=]\s*)(?:"[^"\r\n]*"|\'[^\'\r\n]*\'|[^\s,;]+)',r'\1[redacted]',text)
    text=re.sub(r'\b(?:gh[pousr]_[A-Za-z0-9_]+|github_pat_[A-Za-z0-9_]+|AKIA[A-Z0-9]{16})\b','[redacted]',text)
    text=re.sub(r'\beyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\b','[redacted JWT]',text)
    text=re.sub(r'(?<![\w:/])/(?:Users|home|root|workspace|tmp|opt/hostedtoolcache)(?:/[^\s\'"<>;,\])}]+)+', '[absolute-path]', text)
    text=re.sub(r'\b[A-Za-z]:[\\/](?:[^\s\'"<>;,\])}]+)', '[absolute-path]', text)
    return text


def sanitize_value(value):
    if isinstance(value,str):return sanitize_text(value)
    if isinstance(value,list):return [sanitize_value(v) for v in value]
    if isinstance(value,dict):
        return {sanitize_text(k):('[redacted]' if SENSITIVE_KEY.fullmatch(k) else sanitize_value(v)) for k,v in value.items()}
    return value

def sanitize_log(data):
    return ('[bounded, best-effort redacted diagnostic; never a full profile/environment dump]\n'+sanitize_text(data.decode('utf-8',errors='replace'))).encode()

def collect(run,evidence,bootstrap=None,ui_root=None,job_status=None,cleanup_exit=None):
    job_status=job_status if type(job_status) is str and job_status in {'success','failure','cancelled'} else 'UNKNOWN'
    cleanup_exit=cleanup_exit if type(cleanup_exit) is int and 0<=cleanup_exit<=255 else None
    run=absolute(run);evidence=absolute(evidence)
    if run.is_relative_to(evidence) or evidence.is_relative_to(run):raise ValueError('run and artifact output must be disjoint')
    sources=[run/'evidence']
    if bootstrap is not None:sources.append(absolute(bootstrap))
    if ui_root is not None:sources.append(absolute(ui_root))
    for src in sources:
        if src.is_relative_to(evidence) or evidence.is_relative_to(src) or run==evidence:
            raise ValueError('evidence source and destination overlap')
        # Parent links are rejected even when a leaf name itself is not a link.
        try:validate_directory(src)
        except FileNotFoundError:pass
    new_directory(evidence)  # No existing output, symlink or previous run may be reused.
    copied=[];omitted=[];output={};hashes={};supervisor_availability={}
    for index,src in enumerate(sources):
        if ui_root is not None and src==absolute(ui_root):continue
        for name in sorted(NAMES if index==0 else BOOTSTRAP_NAMES):
            try:data=read_regular(src/name,limit=THREAD_LIMIT if name==THREAD_NAME else MAX_FILE)
            except FileNotFoundError:continue
            except Exception as exc:
                omitted.append({'name':name,'reason':type(exc).__name__});continue
            from hashlib import sha256
            original_sha=sha256(data).hexdigest()
            try:
                if name==THREAD_NAME:
                    data=(json.dumps(thread_document(thread_json(data)),ensure_ascii=True,indent=2)+'\n').encode()
                    if len(data)>THREAD_LIMIT:raise ValueError('thread diagnostic output limit')
                elif name.endswith('.log'):
                    log_limit=256*1024
                    if name in {'export-idea-pretermination.log','validate-idea-pretermination.log'}:
                        log_limit=128*1024
                    elif name in {'export-idea.log','validate-idea.log'}:
                        before=name.replace('-idea.log','-idea-pretermination.log')
                        if before in output:log_limit=128*1024
                    data=sanitize_log(data[-log_limit:])
                    if name in {'export-idea.log','validate-idea.log','export-idea-pretermination.log','validate-idea-pretermination.log'}:
                        data=data[:log_limit].decode('utf-8',errors='ignore').encode()
                elif name.endswith('.json'):data=(json.dumps(sanitize_value(json.loads(data)),ensure_ascii=False,indent=2)+'\n').encode()
                elif name.endswith('.jsonl'):data=('\n'.join(json.dumps(sanitize_value(json.loads(line)),ensure_ascii=False) for line in data.splitlines())+'\n').encode()
            except (ValueError,UnicodeError) as exc:
                omitted.append({'name':name,'reason':'malformed diagnostic '+type(exc).__name__,'original_sha256':original_sha})
                continue
            hashes[name]={'original_sha256':original_sha,'uploaded_sha256':sha256(data).hexdigest()}
            if name in output:
                if output[name]!=data:raise ValueError('conflicting evidence sources: '+name)
                continue
            output[name]=data
    if ui_root is not None:
        from hashlib import sha256
        for source_name,name in sorted(SUPERVISOR_NAMES.items()):
            try:
                data=read_regular(absolute(ui_root)/source_name,
                                  limit=SUPERVISOR_LOG_LIMIT if source_name.endswith('.log') else SUPERVISOR_JSON_LIMIT,
                                  tail=source_name.endswith('.log'))
                original_sha=sha256(data).hexdigest()
                if source_name.endswith('.log'):
                    lines=data.splitlines(keepends=True)
                    # A tail may start mid-secret/line; omit that fragment. Huge
                    # single lines have no useful bounded exception context.
                    if len(data)==SUPERVISOR_LOG_LIMIT:lines=lines[1:]
                    data=b''.join(line if len(line)<=2048 else b'[oversized diagnostic line omitted]\n' for line in lines)
                    data=sanitize_log(data)[-SUPERVISOR_LOG_LIMIT:].decode('utf-8',errors='ignore').encode()
                else:
                    value=supervisor_document(supervisor_json(data),source_name)
                    data=(json.dumps(value,ensure_ascii=False,indent=2)+'\n').encode()
                    if len(data)>SUPERVISOR_JSON_LIMIT:raise ValueError('sanitized supervisor diagnostic exceeds limit')
                output[name]=data;supervisor_availability[name]='COLLECTED'
                hashes[name]={'original_sha256':original_sha,'uploaded_sha256':sha256(data).hexdigest(),
                              'source_digest_scope':'BOUNDED_TAIL' if source_name.endswith('.log') else 'FULL_FILE'}
            except FileNotFoundError:supervisor_availability[name]='MISSING'
            except Exception as exc:
                supervisor_availability[name]='UNAVAILABLE';omitted.append({'name':name,'reason':type(exc).__name__})
    if ui_root is not None:
        current=json.loads(output.get('summary.json',b'{}'))
        try:
            data=collect_budget_owner(absolute(ui_root),current.get('run_id'),current.get('run_attempt'))
            output[BUDGET_OWNER]=data;hashes[BUDGET_OWNER]={'uploaded_sha256':sha256(data).hexdigest()}
        except InterruptedError:raise
        except FileNotFoundError:omitted.append({'name':BUDGET_OWNER,'reason':'MISSING'})
        except Exception:omitted.append({'name':BUDGET_OWNER,'reason':'INVALID_OR_UNAVAILABLE'})
        try:
            current=json.loads(output.get('summary.json',b'{}'))
            for name,data in collect_display(absolute(ui_root),current.get('run_id'),current.get('run_attempt')).items():
                output[name]=data;hashes[name]={'uploaded_sha256':sha256(data).hexdigest()}
        except FileNotFoundError:omitted.append({'name':DISPLAY_REPORT,'reason':'MISSING'})
        except Exception:omitted.append({'name':DISPLAY_REPORT,'reason':'INVALID_OR_UNAVAILABLE'})
        try:
            for name,data in collect_project_trust(absolute(ui_root),current.get('run_id'),current.get('run_attempt')).items():
                output[name]=data;hashes[name]={'uploaded_sha256':sha256(data).hexdigest()}
        except FileNotFoundError:omitted.append({'name':'project-trust-request.json','reason':'MISSING'})
        except Exception:omitted.append({'name':'project-trust-request.json','reason':'INVALID_OR_UNAVAILABLE'})
        try:
            for name,data in collect_post_trust(absolute(ui_root),current.get('run_id'),current.get('run_attempt')).items():
                output[name]=data;hashes[name]={'uploaded_sha256':sha256(data).hexdigest()}
        except InterruptedError:raise
        except FileNotFoundError:omitted.append({'name':POST_TRUST_REPORT,'reason':'MISSING'})
        except Exception:omitted.append({'name':POST_TRUST_REPORT,'reason':'INVALID_OR_UNAVAILABLE'})
        for stage in (5,6):
            try:
                for name,data in collect_plugin_agreement(absolute(ui_root),stage,current.get('run_id'),current.get('run_attempt')).items():
                    output[name]=data;hashes[name]={'uploaded_sha256':sha256(data).hexdigest()}
            except InterruptedError:raise
            except FileNotFoundError:omitted.append({'name':f'plugin-stage-{stage}-request.json','reason':'MISSING'})
            except Exception:omitted.append({'name':f'plugin-stage-{stage}-request.json','reason':'INVALID_OR_UNAVAILABLE'})
        for stage in (7,8,9,10,11):
            try:
                for name,data in collect_profile_control(absolute(ui_root),stage,current.get('run_id'),current.get('run_attempt')).items():
                    output[name]=data;hashes[name]={'uploaded_sha256':sha256(data).hexdigest()}
            except InterruptedError:raise
            except FileNotFoundError:omitted.append({'name':f'profile-stage-{stage}-request.json','reason':'MISSING'})
            except Exception:omitted.append({'name':f'profile-stage-{stage}-request.json','reason':'INVALID_OR_UNAVAILABLE'})
        try:
            data=collect_restart_result(absolute(ui_root))
            output['restart-result.json']=data;hashes['restart-result.json']={'uploaded_sha256':sha256(data).hexdigest()}
        except InterruptedError:raise
        except FileNotFoundError:omitted.append({'name':'restart-result.json','reason':'MISSING'})
        except Exception:omitted.append({'name':'restart-result.json','reason':'INVALID_OR_UNAVAILABLE'})
    if 'summary.json' not in output:
        output['summary.json']=(json.dumps({'status':'NOT_RUN','reason':'official command not reached'})+'\n').encode()
    summary=json.loads(output['summary.json'])
    if not isinstance(summary,dict):raise ValueError('summary must be an object')
    supervisor=json.loads(output['supervisor-result.json']) if 'supervisor-result.json' in output else {}
    if summary.get('status')=='RUNNING':
        summary.update(status='FAIL',observed_status='RUNNING',terminal_reason='OFFICIAL_SUMMARY_UNFINALIZED',
                       initiating_cause='UNKNOWN',final_archive_published=False,release_status='BLOCKED')
    if summary.get('status') in ('PASS','SMOKE_PASS_NOT_RELEASE'):
        verified=verified_supervisor_success(supervisor,job_status,cleanup_exit) if ui_root is not None else job_status=='success' and type(cleanup_exit) is int and cleanup_exit==0
        if not verified:
            summary.update(observed_status=summary['status'],status='FAIL',terminal_reason='SUPERVISOR_OR_CLEANUP_NOT_VERIFIED',
                           final_archive_published=False,release_status='BLOCKED')
    if ui_root is not None:
        summary['supervisor_evidence']={'files':supervisor_availability,
            'status':supervisor.get('status','UNKNOWN'),
            'child_exit_code':supervisor.get('exit_code') if type(supervisor.get('exit_code')) is int else None,
            'cleanup_verified':supervisor.get('cleanup_verified') if type(supervisor.get('cleanup_verified')) is bool else None,
            'cleanup_command_exit_code':cleanup_exit,'job_status_at_collection':job_status}
    updated=(json.dumps(summary,ensure_ascii=False,indent=2)+'\n').encode()
    if updated!=output['summary.json']:
        from hashlib import sha256
        hashes.setdefault('summary.json',{})['uploaded_sha256']=sha256(updated).hexdigest()
        hashes['summary.json']['terminal_finalization']=True
        output['summary.json']=updated
    for name,data in output.items():write_new(evidence/name,data);copied.append(name)
    write_new(evidence/'collection.json',(json.dumps({'copied':copied,'omitted':omitted,'zip_uploaded':False,'hashes':hashes,'status':'PARTIAL' if omitted else 'PASS'},indent=2)+'\n').encode())

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--run',type=Path,required=True);p.add_argument('--evidence',type=Path,required=True);p.add_argument('--bootstrap',type=Path)
    p.add_argument('--ui-root',type=Path);p.add_argument('--job-status',choices=['success','failure','cancelled'])
    p.add_argument('--cleanup-exit',type=int,choices=range(256))
    a=p.parse_args();collect(a.run,a.evidence,a.bootstrap,a.ui_root,a.job_status,a.cleanup_exit)
