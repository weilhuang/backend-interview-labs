"""Bounded bg-wa stack facts from the current validation profile; never raw dumps."""
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import time
from safe_io import directory_fd, read_regular, regular_reader, write_new

NAME='validate-thread-diagnostics.json'
MAX_ENTRIES=256
MAX_SOURCE=1024*1024
MAX_SAMPLE=128*1024
MAX_OUTPUT=256*1024
MAX_THREADS=64
MAX_FRAMES=48
FILE=re.compile(r'thread-dump-(0|[1-9][0-9]{0,9})\.txt\Z')
STATES={'UNKNOWN','NEW','RUNNABLE','BLOCKED','WAITING','TIMED_WAITING','TERMINATED'}
ROLES={'UNKNOWN','MAIN','EDT','COROUTINE_WORKER','POOLED','OTHER'}
CODES={'DIRECTORY_UNAVAILABLE','SCAN_LIMIT','SCAN_DEADLINE','UNSAFE_FILE','SOURCE_SIZE_LIMIT',
       'SOURCE_CHANGED','READ_UNAVAILABLE','MALFORMED_UTF8','NO_STACK_FRAMES','PROJECTION_LIMIT','CONTEXT_UNAVAILABLE','SOURCE_METADATA_INVALID','DUPLICATE_SOURCE_ID'}
CONTEXT_KEYS={'run_id','run_attempt','tested_sha','source_tree','source_manifest_sha256','archive_sha256'}
PREFIX=('java.','javax.','sun.','jdk.','com.intellij.','com.jetbrains.edu.','org.jetbrains.','org.gradle.','kotlin.','kotlinx.','labs.')
FRAME=re.compile(r'(?:[A-Za-z0-9_.-]+(?:@[A-Za-z0-9_.+-]+)?/)?([A-Za-z_$][A-Za-z0-9_.$]*(?:/[0-9A-Fa-fx]+)?(?:\.<(?:init|clinit)>|\.[A-Za-z_$][A-Za-z0-9_$]*))\((Native Method|Unknown Source|[A-Za-z_$][A-Za-z0-9_$.-]{0,127}\.(?:java|kt|groovy|scala)(?::[0-9]{1,7})?)\)\Z')

def require(ok,message='invalid thread diagnostic'):
    if not ok:raise ValueError(message)

def payload(value):return (json.dumps(value,ensure_ascii=True,separators=(',',':'))+'\n').encode()
def digest(raw):return hashlib.sha256(raw).hexdigest()
def strict_json(raw):
    def unique(pairs):
        result={}
        for key,value in pairs:
            require(key not in result);result[key]=value
        return result
    def reject(_):raise ValueError('invalid number')
    return json.loads(raw,object_pairs_hook=unique,parse_constant=reject)
def integer(value,low,high):
    require(type(value) is int and low<=value<=high);return value
def token(value,pattern):
    require(type(value) is str and re.fullmatch(pattern,value) is not None);return value
def enum(value,choices):
    require(type(value) is str and value in choices);return value

CREDENTIAL=re.compile(r'(?i)(?:gh[pousr]_[a-z0-9_]{4,}|github_pat_[a-z0-9_]{4,}|AKIA[A-Z0-9]{16}|AIza[a-z0-9_-]{20,}|(?:glpat|sk|xox[baprs])-[a-z0-9_-]{10,}|eyJ[a-z0-9_-]+\.[a-z0-9_-]+\.[a-z0-9_-]+)')

def normalized_frame(value):
    require(type(value) is str and len(value)<=384)
    match=FRAME.fullmatch(value)
    require(match is not None and match[1].startswith(PREFIX))
    # Module/version prefixes are arbitrary runtime text, not necessary stack facts.
    normalized=match[1]+'('+match[2]+')'
    require(CREDENTIAL.search(normalized) is None)
    return normalized

def project_stacks(raw):
    """Drop arbitrary thread names/messages; retain only known-package frame syntax."""
    text=raw.decode('utf-8');threads=[];current=None;truncated=False;used=0
    for line in text.splitlines():
        if len(line)>1024:continue
        if line.startswith('"'):
            if len(threads)>=MAX_THREADS:truncated=True;break
            name=line.split('"',2)[1] if '"' in line[1:] else ''
            role='MAIN' if name=='main' else 'EDT' if re.fullmatch(r'AWT-EventQueue-[0-9]{1,4}',name) else 'COROUTINE_WORKER' if re.fullmatch(r'DefaultDispatcher-worker-[0-9]{1,4}',name) else 'POOLED' if re.fullmatch(r'ApplicationImpl pooled thread [0-9]{1,4}',name) else 'OTHER'
            current={'role':role,'state':'UNKNOWN','frames':[]};threads.append(current);used+=256
        state=re.fullmatch(r'\s*java\.lang\.Thread\.State: ([A-Z_]+)(?: \([a-z ]{1,40}\))?',line)
        if state and current is not None and state[1] in STATES:current['state']=state[1]
        stripped=line.strip()
        if not stripped.startswith('at '):continue
        try:frame=normalized_frame(stripped[3:])
        except ValueError:continue
        if current is None:current={'role':'UNKNOWN','state':'UNKNOWN','frames':[]};threads.append(current)
        if len(current['frames'])>=MAX_FRAMES:truncated=True;continue
        current['frames'].append(frame)
        used+=len(payload(frame))+48
        if used>MAX_SAMPLE-2048:
            current['frames'].pop();truncated=True;break
    threads=[t for t in threads if t['frames']]
    require(threads,'NO_STACK_FRAMES')
    return threads,truncated

def context(root):
    result={k:None for k in CONTEXT_KEYS}
    try:
        summary=strict_json(read_regular(root/'evidence/summary.json',limit=4*1024*1024))
        for key in ('run_id','run_attempt'):result[key]=token(summary.get(key),r'[1-9][0-9]{0,19}')
        result['tested_sha']=token(summary.get('commit'),r'[0-9a-f]{40}')
        ci=strict_json(read_regular(root/'evidence/source-ci.json',limit=4*1024*1024))
        require(ci.get('sha')==result['tested_sha'] and ci.get('status')=='PASS')
        result['source_tree']=token(ci.get('commit_tree'),r'[0-9a-f]{40}')
        generation=strict_json(read_regular(root/'evidence/generation.json',limit=64*1024))
        require(generation.get('status')=='PASS')
        result['source_manifest_sha256']=token(generation.get('full_manifest_sha256'),r'[0-9a-f]{64}')
        archive=strict_json(read_regular(root/'evidence/archive.json',limit=64*1024))
        require(archive.get('status')=='PASS')
        result['archive_sha256']=token(archive.get('archive_sha256'),r'[0-9a-f]{64}')
        return {'status':'BOUND',**result}
    except Exception:return {'status':'UNAVAILABLE',**{k:None for k in CONTEXT_KEYS}}

def validate_document(value):
    require(type(value) is dict)
    result={'schema_version':integer(value.get('schema_version'),1,1),
            'status':enum(value.get('status'),{'COLLECTED','PARTIAL','NO_ELIGIBLE_FILES','UNAVAILABLE'}),
            'capture_phase':enum(value.get('capture_phase'),{'BEFORE_TERMINATION','FINALIZATION'}),
            'at_utc':token(value.get('at_utc'),r'[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9:.]{8,20}\+00:00')}
    c=value.get('context');require(type(c) is dict)
    result['context']={'status':enum(c.get('status'),{'BOUND','UNAVAILABLE'})}
    for key in sorted(CONTEXT_KEYS):
        item=c.get(key)
        pattern=r'[1-9][0-9]{0,19}' if key in {'run_id','run_attempt'} else r'[0-9a-f]{40}' if key in {'tested_sha','source_tree'} else r'[0-9a-f]{64}'
        result['context'][key]=None if item is None else token(item,pattern)
    require((c['status']=='BOUND')==all(result['context'][k] is not None for k in CONTEXT_KEYS))
    scan=value.get('scan');require(type(scan) is dict and type(scan.get('truncated')) is bool)
    result['scan']={'examined':integer(scan.get('examined'),0,MAX_ENTRIES),'eligible':integer(scan.get('eligible'),0,MAX_ENTRIES),'truncated':scan['truncated']}
    omissions=value.get('omissions');require(type(omissions) is list and len(omissions)<=MAX_ENTRIES+2)
    result['omissions']=[enum(x,CODES) for x in omissions]
    samples=value.get('samples');require(type(samples) is list and len(samples)<=2);result['samples']=[];identifiers=set();selections=set()
    for sample in samples:
        require(type(sample) is dict and type(sample.get('projection_truncated')) is bool)
        row={'selection':enum(sample.get('selection'),{'EARLIEST_MTIME','LATEST_MTIME','ONLY'}),
             'source_id':integer(sample.get('source_id'),0,2147483647),'source_mtime_ns':integer(sample.get('source_mtime_ns'),0,2**63-1),
             'source_bytes':integer(sample.get('source_bytes'),1,MAX_SOURCE),'source_sha256':token(sample.get('source_sha256'),r'[0-9a-f]{64}'),
             'projection_truncated':sample['projection_truncated'],'threads':[]}
        require(row['source_id'] not in identifiers and row['selection'] not in selections);identifiers.add(row['source_id']);selections.add(row['selection'])
        threads=sample.get('threads');require(type(threads) is list and 1<=len(threads)<=MAX_THREADS)
        for thread in threads:
            require(type(thread) is dict);frames=thread.get('frames');require(type(frames) is list and 1<=len(frames)<=MAX_FRAMES)
            clean=[]
            for frame in frames:
                clean.append(normalized_frame(frame))
            row['threads'].append({'role':enum(thread.get('role'),ROLES),'state':enum(thread.get('state'),STATES),'frames':clean})
        require(len(payload(row))<=MAX_SAMPLE);result['samples'].append(row)
    require(len(payload(result))<=MAX_OUTPUT)
    require(value['status']!='COLLECTED' or (samples and not omissions and not scan['truncated']))
    require(value['status']!='NO_ELIGIBLE_FILES' or not samples)
    return result

def snapshot(root,phase):
    """No recursive walk, filename output, signals, subprocesses or profile copying."""
    root=Path(root);require(phase in {'BEFORE_TERMINATION','FINALIZATION'})
    value={'schema_version':1,'status':'UNAVAILABLE','capture_phase':phase,'at_utc':datetime.now(timezone.utc).isoformat(timespec='milliseconds'),
           'context':context(root),'scan':{'examined':0,'eligible':0,'truncated':False},'omissions':[],'samples':[]}
    if value['context']['status']!='BOUND':value['omissions'].append('CONTEXT_UNAVAILABLE')
    candidates=[];seen=set();deadline=time.monotonic()+1
    directory=root/'validate-profile/log/bg-wa'
    try:
        with directory_fd(directory) as fd:
            with os.scandir(fd) as entries:
                for entry in entries:
                    if value['scan']['examined']>=MAX_ENTRIES:
                        value['scan']['truncated']=True;value['omissions'].append('SCAN_LIMIT');break
                    if time.monotonic()>=deadline:
                        value['scan']['truncated']=True;value['omissions'].append('SCAN_DEADLINE');break
                    value['scan']['examined']+=1;match=FILE.fullmatch(entry.name)
                    if match is None or int(match[1])>2147483647:continue
                    ident=int(match[1])
                    if ident in seen:value['omissions'].append('DUPLICATE_SOURCE_ID');continue
                    seen.add(ident)
                    info=os.stat(entry.name,dir_fd=fd,follow_symlinks=False)
                    if not stat.S_ISREG(info.st_mode) or info.st_nlink!=1 or info.st_uid!=os.getuid():value['omissions'].append('UNSAFE_FILE');continue
                    if not 0<=info.st_mtime_ns<=2**63-1:value['omissions'].append('SOURCE_METADATA_INVALID');continue
                    value['scan']['eligible']+=1
                    if not 0<info.st_size<=MAX_SOURCE:value['omissions'].append('SOURCE_SIZE_LIMIT');continue
                    candidates.append((info.st_mtime_ns,int(match[1]),entry.name,info.st_ino,info.st_size))
    except Exception:value['omissions'].append('DIRECTORY_UNAVAILABLE')
    # Timestamp supplies chronology; a validated bounded numeric ID resolves ties.
    if value['scan']['truncated'] or 'DUPLICATE_SOURCE_ID' in value['omissions']:candidates=[]  # A partial listing cannot establish the true extremes.
    candidates.sort(key=lambda row:row[:2]);chosen=[]
    if candidates:chosen=[('ONLY',candidates[0])] if len(candidates)==1 else [('EARLIEST_MTIME',candidates[0]),('LATEST_MTIME',candidates[-1])]
    for selection,(mtime,ident,name,inode,size) in chosen:
        try:
            with regular_reader(directory/name) as stream:
                before=os.fstat(stream.fileno());require((before.st_mtime_ns,before.st_ino,before.st_size)==(mtime,inode,size),'SOURCE_CHANGED')
                raw=stream.read(MAX_SOURCE+1);after=os.fstat(stream.fileno())
                require(len(raw)==size and (after.st_mtime_ns,after.st_ino,after.st_size)==(mtime,inode,size),'SOURCE_CHANGED')
            threads,truncated=project_stacks(raw)
            value['samples'].append({'selection':selection,'source_id':ident,'source_mtime_ns':mtime,'source_bytes':size,'source_sha256':digest(raw),'projection_truncated':truncated,'threads':threads})
            if truncated:value['omissions'].append('PROJECTION_LIMIT')
        except UnicodeError:value['omissions'].append('MALFORMED_UTF8')
        except Exception as exc:value['omissions'].append(str(exc) if type(exc) is ValueError and str(exc) in {'SOURCE_CHANGED','NO_STACK_FRAMES'} else 'READ_UNAVAILABLE')
    value['status']=('PARTIAL' if value['omissions'] or value['scan']['truncated'] else 'COLLECTED') if value['samples'] else 'UNAVAILABLE' if value['omissions'] else 'NO_ELIGIBLE_FILES'
    clean=validate_document(value);write_new(root/'evidence'/NAME,payload(clean));return {'status':clean['status'],'samples':len(clean['samples']),'capture_phase':phase}
