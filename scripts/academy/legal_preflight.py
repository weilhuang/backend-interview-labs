"""One exact-source, read-only approved-PDF availability check; no IDE or UI action."""
import hashlib
import json
import math
import os
from pathlib import Path
import re
import signal
import subprocess
import sys
import time
from display_diagnostic import encode, json_read, publish
from safe_io import read_regular, new_directory, validate_directory
from plugin_agreement import LEGAL_ID, verify_legal

PASS='PASS_APPROVED_PDF_AVAILABILITY_NOT_ACCEPTANCE'
FAIL='FAILED_APPROVED_PDF_AVAILABILITY_NOT_ACCEPTANCE'
REF='refs/heads/academy-validation/legal-preflight'
FILES=('plugin_agreement.py','legal_preflight.py','academy-legal.json')

def require(ok):
    if not ok:raise ValueError('invalid legal preflight receipt')
def token(value,pattern):
    require(type(value) is str and re.fullmatch(pattern,value) is not None);return value

def validate(value):
    fields={'schema','kind','status','repository','run_id','run_attempt','commit','tree','legal_identity','checker_sha256','elapsed_seconds','error_code','ui_actions','course_acceptance','event','ref','phase'}
    require(type(value) is dict and set(value)==fields and type(value['schema']) is int and value['schema']==1)
    require(value['kind']=='APPROVED_PDF_AVAILABILITY_PREFLIGHT' and value['repository']=='weilhuang/backend-interview-labs')
    require(value['ref']==REF and ((value['event']=='push' and value['phase']=='') or (value['event']=='workflow_dispatch' and value['phase']=='legal-preflight')))
    for key in ('run_id','run_attempt'):token(value[key],r'[1-9][0-9]{0,19}')
    for key in ('commit','tree'):token(value[key],r'[0-9a-f]{40}')
    require(value['legal_identity']==LEGAL_ID and type(value['legal_identity']) is dict)
    hashes=value['checker_sha256'];require(type(hashes) is dict and set(hashes)==set(FILES))
    for item in hashes.values():token(item,r'[0-9a-f]{64}')
    require(type(value['elapsed_seconds']) in (int,float) and math.isfinite(value['elapsed_seconds']) and 0<=value['elapsed_seconds']<=60)
    require(value['status'] in (PASS,FAIL))
    require((value['status']==PASS and value['error_code'] is None) or (value['status']==FAIL and value['error_code'] in ('TOTAL_DEADLINE','FETCH_OR_IDENTITY_REJECTED','OTHER_FAILURE')))
    require(type(value['ui_actions']) is int and value['ui_actions']==0 and value['course_acceptance']=='NOT_RUN')
    return value

def source_context():
    repo=Path(__file__).resolve().parents[2]
    require(Path(os.environ['GITHUB_WORKSPACE'])==repo)
    require(os.environ['GITHUB_REPOSITORY']=='weilhuang/backend-interview-labs')
    event=os.environ['GITHUB_EVENT_NAME'];ref=os.environ['GITHUB_REF'];phase=os.environ.get('PREFLIGHT_PHASE','')
    require(ref==REF and ((event=='push' and phase=='') or (event=='workflow_dispatch' and phase=='legal-preflight')))
    commit=token(os.environ['GITHUB_SHA'],r'[0-9a-f]{40}')
    def git(name):
        result=subprocess.run(['git','rev-parse','--verify',name],cwd=repo,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,timeout=3,check=True)
        require(len(result.stdout)<=64);return token(result.stdout.decode().strip(),r'[0-9a-f]{40}')
    require(git('HEAD')==commit)
    hashes={name:hashlib.sha256(read_regular(Path(__file__).with_name(name),limit=128*1024)).hexdigest() for name in FILES}
    return {'event':event,'ref':ref,'phase':phase,'repository':os.environ['GITHUB_REPOSITORY'],'run_id':token(os.environ['GITHUB_RUN_ID'],r'[1-9][0-9]{0,19}'),
        'run_attempt':token(os.environ['GITHUB_RUN_ATTEMPT'],r'[1-9][0-9]{0,19}'),'commit':commit,'tree':git('HEAD^{tree}'),'checker_sha256':hashes}

def main():
    context=source_context();temporary=Path(os.environ['RUNNER_TEMP']);require(temporary.is_absolute());validate_directory(temporary)
    out=temporary/('academy-legal-preflight-'+context['run_id']+'-'+context['run_attempt']);new_directory(out)
    value={'schema':1,'kind':'APPROVED_PDF_AVAILABILITY_PREFLIGHT','status':FAIL,**context,'legal_identity':dict(LEGAL_ID),
        'elapsed_seconds':0,'error_code':'OTHER_FAILURE','ui_actions':0,'course_acceptance':'NOT_RUN'}
    started=time.monotonic()
    try:
        require(verify_legal(started+15)==LEGAL_ID);value.update(status=PASS,error_code=None)
    except InterruptedError:raise
    except subprocess.TimeoutExpired:value['error_code']='TOTAL_DEADLINE'
    except (subprocess.CalledProcessError,ValueError):value['error_code']='FETCH_OR_IDENTITY_REJECTED'
    except Exception:value['error_code']='OTHER_FAILURE'
    value['elapsed_seconds']=round(time.monotonic()-started,3)
    raw=encode(validate(value));publish(out/'legal-preflight.json',raw)
    require(validate(json_read(read_regular(out/'legal-preflight.json',limit=8192)))==value)
    # Marker is produced only for this fresh, strictly validated receipt, including
    # a typed failure receipt; no old output is uploaded if collection itself fails.
    with open(os.environ['GITHUB_OUTPUT'],'a') as stream:stream.write('collected=true\n')
    return 0 if value['status']==PASS else 1

if __name__=='__main__':
    def cancelled(*_):raise InterruptedError('legal preflight cancelled')
    signal.signal(signal.SIGTERM,cancelled);signal.signal(signal.SIGINT,cancelled)
    sys.exit(main())
