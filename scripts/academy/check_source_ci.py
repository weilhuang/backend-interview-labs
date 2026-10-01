#!/usr/bin/env python3
"""Read-only exact-tested-commit gate; PR API head_sha is never checkout proof."""
import argparse
import ast
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from gates import require, dump, sha, unique_pairs
from safe_io import read_regular

REPOSITORY='weilhuang/backend-interview-labs'
SMOKE_REF='refs/heads/academy-validation/smoke'
FULL_REF='refs/heads/academy-validation/full'
ALLOWED_REFS={SMOKE_REF,FULL_REF,'refs/heads/main'}
MAX_DOWNLOAD=8*1024*1024
class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,req,fp,code,msg,headers,newurl):return None

def decode(data):return json.loads(data,object_pairs_hook=unique_pairs)

def api(path,raw=False):
    url='https://api.github.com/repos/'+REPOSITORY+'/'+path
    request=urllib.request.Request(url,headers={'Accept':'application/vnd.github+json','Authorization':'Bearer '+os.environ['GH_TOKEN'],
        'X-GitHub-Api-Version':'2022-11-28','User-Agent':'academy-official-ci-readonly'})
    opener=urllib.request.build_opener(NoRedirect())
    try:
        with opener.open(request,timeout=10) as response:
            data=response.read(MAX_DOWNLOAD+1);require(len(data)<=MAX_DOWNLOAD,'API response exceeds bound');return data if raw else decode(data)
    except urllib.error.HTTPError as exc:
        if not raw or exc.code not in (301,302,303,307,308):raise ValueError('GitHub API returned HTTP '+str(exc.code)) from None
        location=exc.headers.get('Location','');parsed=urllib.parse.urlparse(location)
        require(parsed.scheme=='https' and parsed.hostname and not parsed.username and not parsed.password,'unsafe artifact redirect')
        require(parsed.hostname.endswith(('.blob.core.windows.net','.actions.githubusercontent.com','.s3.amazonaws.com')),'unknown artifact download host')
        # Fresh request/opener: bearer token NEVER follows the signed redirect.
        signed_request=urllib.request.Request(location,headers={'User-Agent':'academy-official-ci-readonly'})
        try:
            with urllib.request.build_opener(NoRedirect()).open(signed_request,timeout=15) as response:
                data=response.read(MAX_DOWNLOAD+1);require(len(data)<=MAX_DOWNLOAD,'artifact download exceeds bound');return data
        except urllib.error.HTTPError as error:raise ValueError('Artifact download returned HTTP '+str(error.code)) from None
        except Exception as error:raise ValueError('Artifact download failed: '+type(error).__name__) from None

def parse_evidence_archive(data,artifact):
    require(artifact.get('digest')=='sha256:'+sha(data),'source CI artifact digest mismatch or missing')
    require(len(data)==artifact['size_in_bytes'],'source artifact byte count mismatch')
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        names=archive.namelist();require(names==['evidence.json'],'source artifact must contain exactly evidence.json')
        info=archive.getinfo('evidence.json');require(info.file_size<=1024*1024,'aggregate evidence too large')
        require((info.external_attr>>16)&0o170000 != 0o120000,'source artifact symlink')
        require(archive.testzip() is None,'source artifact CRC error')
        return decode(archive.read(info))

def validate_source_evidence(evidence,run,tested_sha,suites):
    require(evidence.get('repository')==REPOSITORY and evidence.get('schema_version')==1,'source evidence identity/schema mismatch')
    require(evidence.get('run_id')==run['id'] and evidence.get('run_attempt')==run.get('run_attempt',1),'source evidence run/attempt mismatch')
    require(evidence.get('head_sha')==run['head_sha'],'source evidence API head mismatch')
    require(evidence.get('tested_sha')==tested_sha,'source evidence tested SHA differs from packaging checkout')
    require(evidence.get('errors')==[],'source aggregate has errors')
    require(set(evidence.get('suites',{}))==set(suites),'source aggregate suite inventory mismatch')
    require(all(row.get('status')=='passed' for row in evidence['suites'].values()),'some source suites did not pass')

def verify_jobs(jobs,expected):
    require(jobs['total_count']==len(jobs['jobs']),'source job list was truncated')
    # GitHub appends these two existing matrix values to reusable-workflow job
    # display names. Match exact qualified aliases only; never strip arbitrary
    # parenthesized values, which could accept a different JDK/course matrix.
    matrix_aliases={
        'java-pilot / real-java-pilot (21)': 'real-java-pilot',
        'java-foundations / real-java-foundations (java-foundations)': 'real-java-foundations',
    }
    names=[matrix_aliases.get(j['name'],j['name'].split(' / ')[-1]) for j in jobs['jobs']]
    require(len(names)==len(set(names)) and set(names)==set(expected),
            'source job inventory mismatch: missing='+repr(sorted(set(expected)-set(names)))+
            ', unexpected='+repr(sorted(set(names)-set(expected))))
    require(all(j['status']=='completed' and j['conclusion']=='success' for j in jobs['jobs']),'source jobs contain skipped/failed/incomplete status')

def check(repo_root):
    repo=os.environ['GITHUB_REPOSITORY'];commit=os.environ['GITHUB_SHA'];ref=os.environ['GITHUB_REF'];event=os.environ['GITHUB_EVENT_NAME']
    require(repo==REPOSITORY and ref in ALLOWED_REFS,'repository/ref not approved for packaging')
    require((event=='push' and ref in {SMOKE_REF,FULL_REF}) or (event=='workflow_dispatch' and ref=='refs/heads/main'),'unapproved packaging trigger')
    require(os.environ.get('GITHUB_API_URL','https://api.github.com')=='https://api.github.com','unexpected API host')
    def git(*args):
        child_env={k:v for k,v in os.environ.items() if k in {'PATH','HOME','LANG','LC_ALL','TZ'}}
        return subprocess.check_output(['git',*args],cwd=repo_root,text=True,env=child_env).strip()
    require(git('rev-parse','HEAD')==commit,'actual checkout differs from GITHUB_SHA')
    raw_commit=git('cat-file','-p','HEAD').split('\n\n',1)[0].splitlines()
    local_tree=next(line.split()[1] for line in raw_commit if line.startswith('tree '))
    local_parents=[line.split()[1] for line in raw_commit if line.startswith('parent ')]
    details=api('git/commits/'+commit)
    require(details['sha']==commit and details['tree']['sha']==local_tree and [p['sha'] for p in details['parents']]==local_parents,'local/remote commit tree or parents mismatch')
    # A fixed validation branch must still target this exact commit; moving it
    # while this queued run starts invalidates the run instead of racing it.
    branch=urllib.parse.quote(ref.removeprefix('refs/heads/'),safe='/')
    current_ref=api('git/ref/heads/'+branch)
    require(current_ref['object']['sha']==commit,'validation branch has moved away from this run SHA')
    plan_path=repo_root/'scripts/ci/plan.py';tree=ast.parse(read_regular(plan_path,limit=1024*1024))
    constants={}
    for node in tree.body:
        if isinstance(node,ast.Assign):
            for target in node.targets:
                if isinstance(target,ast.Name) and target.id in {'SUITES','REAL_JOBS'}:constants[target.id]=ast.literal_eval(node.value)
    require(set(constants)=={'SUITES','REAL_JOBS'},'source CI inventory is not a literal supported schema')
    expected={n for group in constants['REAL_JOBS'].values() for n in group}|{'PR累计验收范围','文档元数据与门禁自测','CI验收总门禁'}
    runs=api('actions/workflows/ci.yml/runs?per_page=20')['workflow_runs']
    allowed_heads={commit,*local_parents}
    candidates=[r for r in runs if r.get('path')=='.github/workflows/ci.yml' and r['head_sha'] in allowed_heads and r['event'] in ('push','workflow_dispatch','pull_request')]
    require(candidates,'no bounded source CI candidate for this tested commit')
    rejected=[]
    candidates=sorted(candidates,key=lambda r:(r['run_number'],r.get('run_attempt',1)),reverse=True)
    for run in candidates[:5]:
        require(run['status']=='completed','newer plausible source run is incomplete; no older-green fallback')
        artifacts=api(f"actions/runs/{run['id']}/artifacts?per_page=100")
        require(artifacts['total_count']==len(artifacts['artifacts']),'source artifacts list truncated')
        name=f"ci-evidence-{run['id']}-{run.get('run_attempt',1)}"
        matches=[a for a in artifacts['artifacts'] if a['name']==name]
        if len(matches)!=1 or matches[0].get('expired'):
            raise ValueError('newer plausible source run lacks unique unexpired aggregate proof')
        artifact=matches[0];require(artifact['size_in_bytes']<=MAX_DOWNLOAD,'source artifact exceeds bound')
        require(artifact.get('workflow_run',{}).get('id')==run['id'],'artifact run mismatch')
        data=api(f"actions/artifacts/{artifact['id']}/zip",raw=True);evidence=parse_evidence_archive(data,artifact)
        if evidence.get('tested_sha')!=commit:
            rejected.append({'id':run['id'],'reason':'different actually tested commit'});continue
        require(run['conclusion']=='success','matching tested commit has failed source CI; no older-green fallback')
        validate_source_evidence(evidence,run,commit,constants['SUITES'])
        jobs=api(f"actions/runs/{run['id']}/jobs?filter=latest&per_page=100");verify_jobs(jobs,expected)
        return {'status':'PASS','sha':commit,'tested_sha':commit,'api_head_sha':run['head_sha'],'commit_tree':local_tree,'commit_parents':local_parents,
                'run_id':run['id'],'run_attempt':run.get('run_attempt',1),'url':run['html_url'],'event':run['event'],
                'artifact_id':artifact['id'],'artifact_sha256':sha(data),'source_aggregate':evidence,
                'jobs':[{'name':j['name'],'status':j['status'],'conclusion':j['conclusion']} for j in jobs['jobs']]}
    raise ValueError('No exact-tested complete green source CI in bounded scan: '+json.dumps(rejected))

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--report',type=Path,required=True);p.add_argument('--repo',type=Path,default=Path('.'));a=p.parse_args()
    try:result=check(a.repo)
    except Exception as exc:result={'status':'FAIL','sha':os.environ.get('GITHUB_SHA'),'error':f'{type(exc).__name__}: {exc}'}
    dump(a.report,result);print(json.dumps(result,ensure_ascii=False));sys.exit(0 if result['status']=='PASS' else 1)
