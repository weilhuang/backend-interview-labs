#!/usr/bin/env python3
"""Serial source-bound replay; no Docker, Java, network, installations or publishing.
Uses only an explicit existing Go executable and a previously prepared module cache.
"""
import argparse, hashlib, json, os, re, shutil, signal, subprocess, sys
from pathlib import Path

TASKS=('request-lifecycle','gin-pipeline')
REQUIRED=('TestRequestContract','TestContextContract','TestRouting','TestActualHTTP','TestServiceResultPreserved','TestClientCancellation','TestConcurrentMemoryStore','TestOutputFailure','TestCallerHTTP','TestMainProcess')

def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def manifest(root):return {p.relative_to(root).as_posix():sha(p) for p in sorted(root.rglob('*')) if p.is_file()}
def main():
 parser=argparse.ArgumentParser()
 parser.add_argument('--go',type=Path,required=True)
 parser.add_argument('--module-cache',type=Path,required=True)
 parser.add_argument('--work',type=Path,required=True)
 parser.add_argument('--evidence',type=Path,required=True)
 parser.add_argument('--source',type=Path,default=Path(__file__).resolve().parents[2])
 args=parser.parse_args();source=args.source.resolve();work=args.work.resolve();evidence=args.evidence.resolve()
 if not args.go.is_absolute() or not args.go.is_file() or not os.access(args.go,os.X_OK):raise SystemExit('INVALID_ENV: explicit executable required')
 if not args.module_cache.is_absolute() or not args.module_cache.is_dir():raise SystemExit('INVALID_ENV: prepared module cache required')
 if work==source or source in work.parents or evidence==source or source in evidence.parents:raise SystemExit('INVALID_ENV: work/evidence must be outside immutable source')
 work.mkdir(parents=True,exist_ok=True);evidence.mkdir(parents=True,exist_ok=True)
 frozen=manifest(source);(evidence/'source-manifest.json').write_text(json.dumps(frozen,sort_keys=True,indent=2)+'\n')
 env=dict(os.environ,GOTOOLCHAIN='local',GOWORK='off',GOENV='off',GOFLAGS='',GOPROXY='off',GOSUMDB='off',GIN_MODE='release',GOMAXPROCS='2',GOMODCACHE=str(args.module_cache),GOPATH=str(work/'gopath'),GOCACHE=str(work/'build-cache'))
 records=[]
 def run(label,cwd,arguments,expected=0,required_text=None,limit=240):
  command=[str(args.go),*arguments]
  process=subprocess.Popen(command,cwd=cwd,env=env,text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,start_new_session=True)
  try:
   output,_=process.communicate(timeout=limit)
   r=subprocess.CompletedProcess(command,process.returncode,output)
  except subprocess.TimeoutExpired as e:
   os.killpg(process.pid,signal.SIGKILL);process.communicate()
   raise RuntimeError(f'CHECK_TIMEOUT: {label}; owned process group terminated') from e
  finally:
   # The new process group contains only this invocation and its own descendants.
   # Clean a surviving child even when go/test returned early on an unexpected error.
   try:os.killpg(process.pid,signal.SIGKILL)
   except ProcessLookupError:pass
  logfile=evidence/(label+'.log');logfile.write_text(r.stdout)
  item={'label':label,'command':command,'cwd':str(cwd),'exit_code':r.returncode,'expected_exit':expected,'log':logfile.name,'log_sha256':sha(logfile)}
  if expected==0 and r.returncode!=0:raise RuntimeError(f'{label} failed: {r.stdout[-3000:]}')
  if expected=='failure' and (r.returncode==0 or any(marker in r.stdout for marker in ['build failed','syntax error','panic: test timed out','CHECK_TIMEOUT','--- SKIP:'])):raise RuntimeError(f'{label} did not fail with business assertion')
  if required_text and any(text not in r.stdout for text in required_text):raise RuntimeError(f'{label} missing expected diagnostic {required_text}')
  records.append(item);return r.stdout
 version=run('toolchain-version',source,['version'])
 if not re.fullmatch(r'go version go1\.27\.1 [A-Za-z0-9_]+/[A-Za-z0-9_]+\s*',version):raise SystemExit('INVALID_ENV: Go1.27.1 only')
 (evidence/'toolchain.json').write_text(json.dumps({'path':str(args.go),'sha256':sha(args.go),'version':version.strip(),'flags':['-buildvcs=false','-mod=readonly','-tags=nomsgpack','-p=1'],'network_during_check':'GOPROXY=off,GOSUMDB=off','cache':str(args.module_cache)},indent=2)+'\n')
 matrix=json.loads((source/'materials/go-http/变异矩阵.json').read_text())
 for name in TASKS:
  original=source/'go-course/http'/name/'go'
  dest=work/(name+'-reference')
  if dest.exists():raise RuntimeError(f'Work destination exists; select a fresh work directory: {dest}')
  shutil.copytree(original,dest)
  flags=['-buildvcs=false','-mod=readonly','-tags=nomsgpack','-p=1']
  run(name+'-build',dest,['build',*flags,'./...'])
  run(name+'-mod-verify',dest,['mod','verify'])
  output=run(name+'-positive',dest,['test',*flags,'-count=1','-timeout=45s','-v','./...'])
  names=REQUIRED+(('TestGinPipeline',) if name=='gin-pipeline' else ())
  for test in names:
   if not re.search(r'^--- PASS: '+re.escape(test)+r' ',output,re.M):raise RuntimeError(f'NOT_RUN missing {test}')
  if '--- SKIP:' in output or '[no test files]' in output:raise RuntimeError('NOT_RUN skip or test-free package')
  run(name+'-vet',dest,['vet',*flags,'./...'])
  run(name+'-race',dest,['test',*flags,'-race','-count=1','-timeout=60s','-v','./...'],limit=360)
  stagefile=next((original/'stages').glob('*.txt'))
  staged=work/(name+'-teaching-stage');shutil.copytree(original,staged);shutil.copyfile(stagefile,staged/'exercise.go')
  run(name+'-teaching-stage-positive',staged,['test',*flags,'-count=1','-timeout=30s','-v','-run','^TestRequestContract$','.'])
  expected='TestContextContract/zero_budget' if name=='request-lifecycle' else 'TestGinPipeline/unauthorized_stops_chain'
  selection='/'.join('^'+re.escape(x)+'$' for x in expected.split('/'))
  run(name+'-teaching-stage-negative',staged,['test',*flags,'-count=1','-timeout=30s','-v','-run',selection,'.'],expected='failure',required_text=['--- FAIL: '+expected,'HTTP_STATUS'])
  # Same test project; replace only the learner-owned file in isolated copies.
  variants=[{'variant':'starter','file':f'go-course/http/{name}/go/starters/exercise.go.txt','expected_test':'TestRequestContract/valid','expected_diagnostic':'HTTP_STATUS'}]+[x for x in matrix if x['task']==name]
  for item in variants:
   candidate=work/(name+'-'+item['variant']);shutil.copytree(original,candidate)
   replacement=source/item['file'];shutil.copyfile(replacement,candidate/'exercise.go')
   label=name+'-'+item['variant']
   run(label+'-compile',candidate,['test',*flags,'-run','^$','./...'])
   selection='/'.join('^'+re.escape(x)+'$' for x in item['expected_test'].split('/'))
   result=run(label+'-negative',candidate,['test',*flags,'-count=1','-timeout=30s','-v','-run',selection,'.'],expected='failure',required_text=['--- FAIL: '+item['expected_test'],item['expected_diagnostic']])
   records[-1]['variant_sha256']=sha(replacement);records[-1]['expected_test']=item['expected_test']
   records[-1]['expected_diagnostic']=item['expected_diagnostic'];records[-1]['outcome']='EXPECTED_BUSINESS_FAILURE'
   if item['variant']=='ignore-parent':
    run(label+'-full-suite-negative',candidate,['test',*flags,'-count=1','-timeout=30s','-v','./...'],expected='failure',required_text=['--- FAIL: TestContextContract/canceled_after_store_success','POSTCHECK_PARENT'])
    records[-1]['variant_sha256']=sha(replacement);records[-1]['expected_test']='TestContextContract/canceled_after_store_success';records[-1]['outcome']='EXPECTED_BUSINESS_FAILURE_NO_TIMEOUT'
   if item['variant']=='omit-postcheck':
    run(label+'-deadline-negative',candidate,['test',*flags,'-count=1','-timeout=30s','-v','-run','^TestContextContract$/^deadline_after_store_success$','.'],expected='failure',required_text=['--- FAIL: TestContextContract/deadline_after_store_success','HTTP_STATUS'])
    records[-1]['variant_sha256']=sha(replacement);records[-1]['expected_test']='TestContextContract/deadline_after_store_success';records[-1]['outcome']='EXPECTED_BUSINESS_FAILURE'
  if manifest(original)!=manifest(dest):raise RuntimeError('Reference copy mutated by Go tools')
 if manifest(source)!=frozen:raise RuntimeError('Source changed during verification')
 summary={'status':'PASS_SCOPED_GO_REPLAY','source_manifest_sha256':sha(evidence/'source-manifest.json'),'records':records,'not_run':['JDK21_JUnit_bridge','unified_root_Gradle','native_Academy_import_Check','IDE_Go_debugger','Docker','TLS_HTTP2_HTTP3','GORM_database','production_auth','production_load']}
 (evidence/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n')
 print(json.dumps({'status':summary['status'],'commands':len(records),'expected_negative_assertions':sum(r['expected_exit']=='failure' for r in records),'source_files':len(frozen)},ensure_ascii=False))
if __name__=='__main__':main()
