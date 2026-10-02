"""One read-only current-display PNG and a strict typed receipt; no UI action."""
from datetime import datetime, timezone
import hashlib
import json
import os
import re
import struct
import time
import zlib
import uuid
from safe_io import read_regular, write_new, validate_directory, new_directory, directory_fd

PNG_NAME='post-ui-diagnostic.png'
REPORT_NAME='post-ui-diagnostic.json'
MAX_PNG=2*1024*1024
STATUSES={'CAPTURED_NOT_ACCEPTANCE','UNAVAILABLE_IDE_EXITED','UNAVAILABLE_UI_DEADLINE',
          'UNAVAILABLE_IDENTITY_OR_CAPTURE','UNAVAILABLE_RECEIPT'}

def require(ok):
    if not ok:raise ValueError('invalid owned-display diagnostic')
def digest(raw):return hashlib.sha256(raw).hexdigest()
def encode(value):return (json.dumps(value,sort_keys=True,separators=(',',':'))+'\n').encode()
def json_read(raw):
    def pairs(items):
        value={}
        for key,item in items:require(key not in value);value[key]=item
        return value
    def bad(_):raise ValueError('invalid number')
    return json.loads(raw,object_pairs_hook=pairs,parse_constant=bad)
def token(value,pattern):
    require(type(value) is str and re.fullmatch(pattern,value) is not None);return value

def publish(path,raw):
    """No-follow, complete-before-visible publication, without replacing old output."""
    with directory_fd(path.parent) as directory:
        temporary='.pending-'+uuid.uuid4().hex
        fd=os.open(temporary,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600,dir_fd=directory)
        try:
            with os.fdopen(fd,'wb',closefd=False) as stream:stream.write(raw);stream.flush();os.fsync(fd)
            os.link(temporary,path.name,src_dir_fd=directory,dst_dir_fd=directory,follow_symlinks=False)
        finally:
            os.close(fd);os.unlink(temporary,dir_fd=directory)

def clean_png(raw):
    require(len(raw)<=MAX_PNG and raw.startswith(b'\x89PNG\r\n\x1a\n'))
    out=bytearray(raw[:8]);position=8;tags=[];compressed=bytearray();width=height=color=None
    while position<len(raw):
        require(position+12<=len(raw));size=struct.unpack('>I',raw[position:position+4])[0];end=position+12+size
        require(end<=len(raw));kind=raw[position+4:position+8];data=raw[position+8:end-4]
        require(zlib.crc32(kind+data)&0xffffffff==struct.unpack('>I',raw[end-4:end])[0]);tags.append(kind);require(len(tags)<=256)
        if kind==b'IHDR':
            require(len(tags)==1 and size==13);width,height,depth,color,comp,filt,interlace=struct.unpack('>IIBBBBB',data)
            require((width,height,depth,comp,filt,interlace)==(1280,900,8,0,0,0) and color in (2,6));out.extend(raw[position:end])
        elif kind==b'IDAT':compressed.extend(data);out.extend(raw[position:end])
        elif kind==b'IEND':require(size==0);out.extend(raw[position:end]);position=end;break
        else:require(kind[:1].islower())  # Drop all ancillary metadata; reject unknown critical chunks.
        position=end
    require(tags and tags[0]==b'IHDR' and tags[-1]==b'IEND' and b'IDAT' in tags and position==len(raw))
    stride=1+width*(3 if color==2 else 4);expected=height*stride;stream=zlib.decompressobj();pixels=stream.decompress(bytes(compressed),expected+1)
    require(len(pixels)==expected and stream.eof and not stream.unused_data and not stream.unconsumed_tail)
    require(all(pixels[i] in range(5) for i in range(0,len(pixels),stride)))
    return bytes(out)

def project_report(value):
    require(type(value) is dict and type(value.get('schema_version')) is int and value['schema_version']==1)
    require(type(value.get('status')) is str and value['status'] in STATUSES)
    result={'schema_version':1,'status':value['status'],'run_id':token(value.get('run_id'),r'[1-9][0-9]{0,19}'),
            'run_attempt':token(value.get('run_attempt'),r'[1-9][0-9]{0,19}'),
            'at_utc':token(value.get('at_utc'),r'[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9:.]{8,20}\+00:00')}
    require(value.get('action')=='SNAPSHOT_ONLY' and type(value.get('after_stage')) is int and value['after_stage']==3
            and type(value.get('delay_seconds')) is int and value['delay_seconds']==30)
    result.update(action='SNAPSHOT_ONLY',after_stage=3,delay_seconds=30)
    for name in ('stage3_receipt_sha256','display_binding_sha256','screenshot_sha256'):
        item=value.get(name);result[name]=None if item is None else token(item,r'[0-9a-f]{64}')
    require(result['status']!='CAPTURED_NOT_ACCEPTANCE' or all(result[n] is not None for n in ('stage3_receipt_sha256','display_binding_sha256','screenshot_sha256')))
    return result

def capture(root,proc,screen,identity,ui_deadline):
    """Called once by the existing owned loop,30s after stage3; never waits here."""
    result={'schema_version':1,'status':'UNAVAILABLE_RECEIPT','run_id':os.environ.get('GITHUB_RUN_ID'),
            'run_attempt':os.environ.get('GITHUB_RUN_ATTEMPT'),'at_utc':datetime.now(timezone.utc).isoformat(timespec='milliseconds'),
            'action':'SNAPSHOT_ONLY','after_stage':3,'delay_seconds':30,
            'stage3_receipt_sha256':None,'display_binding_sha256':None,'screenshot_sha256':None}
    try:
        receipt=read_regular(root/'stage-3/receipt.json',limit=4096);value=json_read(receipt)
        require(value.get('run_id')==result['run_id'] and value.get('run_attempt')==result['run_attempt'] and type(value.get('stage')) is int and value['stage']==3
                and value.get('action')=='DECLINE_USAGE' and value.get('status')=='UI_ACTION_PERFORMED_NOT_ACCEPTANCE')
        result['stage3_receipt_sha256']=digest(receipt)
        result['display_binding_sha256']=digest(read_regular(identity.binding,limit=4096))
        if proc.poll() is not None:result['status']='UNAVAILABLE_IDE_EXITED'
        elif time.monotonic()>=ui_deadline:result['status']='UNAVAILABLE_UI_DEADLINE'
        else:
            result['status']='UNAVAILABLE_IDENTITY_OR_CAPTURE';identity.verify()
            screen('SNAPSHOT',root/PNG_NAME)
            identity.verify();raw=read_regular(root/PNG_NAME,limit=MAX_PNG);clean_png(raw)
            result['screenshot_sha256']=digest(raw);result['status']='CAPTURED_NOT_ACCEPTANCE'
    except InterruptedError:raise
    except Exception:pass  # Missing diagnostics never alter native acceptance or cleanup.
    publish(root/REPORT_NAME,encode(project_report(result)))
    return result['status']

def collect(root,run_id,run_attempt):
    """Return exact sanitized bytes; never trust a JSON name/path as a source."""
    report=project_report(json_read(read_regular(root/REPORT_NAME,limit=4096)))
    require(report['run_id']==token(run_id,r'[1-9][0-9]{0,19}') and report['run_attempt']==token(run_attempt,r'[1-9][0-9]{0,19}'))
    require(root.name=='academy-ui-'+report['run_id']+'-'+report['run_attempt'])
    if report['status']=='UNAVAILABLE_RECEIPT':return {REPORT_NAME:encode(report)}
    receipt=read_regular(root/'stage-3/receipt.json',limit=4096);value=json_read(receipt)
    require(type(value) is dict and value.get('run_id')==report['run_id'] and value.get('run_attempt')==report['run_attempt']
            and type(value.get('stage')) is int and value['stage']==3 and value.get('action')=='DECLINE_USAGE'
            and value.get('status')=='UI_ACTION_PERFORMED_NOT_ACCEPTANCE')
    require(report['stage3_receipt_sha256']==digest(receipt))
    require(report['display_binding_sha256']==digest(read_regular(root/'display-binding.properties',limit=4096)))
    # Root name is fixed by the workflow/run guard; receipt must name that same attempt.
    require(root.name=='academy-ui-'+report['run_id']+'-'+report['run_attempt'])
    output={REPORT_NAME:encode(report)}
    if report['status']=='CAPTURED_NOT_ACCEPTANCE':
        raw=read_regular(root/PNG_NAME,limit=MAX_PNG);require(digest(raw)==report['screenshot_sha256']);clean=clean_png(raw)
        report['uploaded_screenshot_sha256']=digest(clean);output[REPORT_NAME]=encode(report);output[PNG_NAME]=clean
    return output


def wait_collect(root,output,run_id,run_attempt):
    """Bounded observation only, for the existing UI artifact step."""
    from ui_control import read_ui_deadline
    token(run_id,r'[1-9][0-9]{0,19}');token(run_attempt,r'[1-9][0-9]{0,19}')
    validate_directory(root);require(root.name=='academy-ui-'+run_id+'-'+run_attempt)
    require(output==root/'diagnostic-artifact');new_directory(output)
    try:
        deadline=min(time.monotonic()+45,read_ui_deadline(root))
        while not (root/REPORT_NAME).exists() and not (root/'result.json').exists() and time.monotonic()<deadline:time.sleep(.2)
        files=collect(root,run_id,run_attempt)
    except InterruptedError:raise
    except Exception:
        files={REPORT_NAME:encode({'schema_version':1,'status':'UNAVAILABLE','run_id':run_id,'run_attempt':run_attempt,'action':'SNAPSHOT_ONLY','reason':'MISSING_INVALID_OR_EXPIRED_DIAGNOSTIC'})}
    for name,raw in files.items():publish(output/name,raw)


if __name__=='__main__':
    import argparse
    from pathlib import Path
    parser=argparse.ArgumentParser()
    parser.add_argument('--root',type=Path,required=True);parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--run-id',required=True);parser.add_argument('--run-attempt',required=True)
    args=parser.parse_args();wait_collect(args.root,args.output,args.run_id,args.run_attempt)
