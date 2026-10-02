"""Go基础课独立验证入口，所有结果只代表本次实际执行的源码。"""
from pathlib import Path
import os,json,subprocess,shutil,hashlib,yaml,re
R=Path(__file__).resolve().parents[1];E=R/'evidence';E.mkdir(exist_ok=True)
GO=os.environ.get('GO_EXECUTABLE','')
if not GO or not Path(GO).is_file(): raise SystemExit('INVALID_ENV: GO_EXECUTABLE必须指向真实Go 1.27.1；本次不执行测试')
V=subprocess.check_output([GO,'version'],text=True).strip()
if not re.fullmatch(r'go version go1\.27\.1 [\w]+/[\w]+',V): raise SystemExit('INVALID_ENV: '+V)
env=dict(os.environ,GOTOOLCHAIN='local',GOWORK='off',GOENV='off',GOFLAGS='',GOPROXY='off',GOSUMDB='off',GOCACHE=str(R/'work/go-cache'),GOMODCACHE=str(R/'work/go-mod-cache'),GOMAXPROCS='2')
rows=[]
def run(name,args,cwd,success=True,match=None):
 p=subprocess.run([GO,*args],cwd=cwd,env=env,text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=180)
 (E/(name+'.log')).write_text(p.stdout)
 ok=(p.returncode==0) if success else (p.returncode!=0 and 'FAIL' in p.stdout and not any(x in p.stdout for x in ['build failed','syntax error','undefined:']))
 if match:ok=ok and match in p.stdout
 rows.append(dict(check=name,status='PASSED' if ok else 'FAILED',exit_code=p.returncode,log='evidence/'+name+'.log'))
 if not ok:raise AssertionError(name+'\n'+p.stdout)
 return p.stdout
lessons=json.loads((R/'manifest/lessons.json').read_text())
for l in lessons:
 task=R/'overlay/go-course/core'/l['slug'];g=task/'go';meta=yaml.safe_load((task/'task-info.yaml').read_text());p=meta['files'][0]['placeholders'][0]
 author=(g/'exercise.go').read_text();raw=author.encode('utf-16-le');prefix=raw[:p['offset']*2].decode('utf-16-le');suffix=raw[(p['offset']+p['length'])*2:].decode('utf-16-le')
 assert prefix.endswith('\n') and suffix.startswith('\t// 练习区结束')
 assert '🧪' in prefix and len(prefix)!=p['offset']
 files={f['name'] for f in meta['files']};actual={str(x.relative_to(task)) for x in task.rglob('*') if x.is_file() and x.name not in ['task.md','task-info.yaml']}
 assert files==actual and all(f['visible'] for f in meta['files'])
 assert not re.search(r'(?m)^\s*/[A-Za-z0-9_-]+/', (task/'task.md').read_text())
 work=R/'work'/l['slug'];shutil.rmtree(work,ignore_errors=True);shutil.copytree(g,work)
 (work/'exercise.go').write_text(prefix+p['placeholder_text']+suffix)
 run(l['id']+'-starter-build',['build','-buildvcs=false','./...'],work)
 run(l['id']+'-starter-compile',['test','-run','^$','./...'],work)
 run(l['id']+'-starter-red',['test','-count=1','-v','./...'],work,False,{'C13-01':'GREETING:','C13-02':'QUANTITY:','C13-03':'TOTAL:'}[l['id']])
 for answer in sorted((g/'answers').glob('*.txt')):
  s=answer.read_text();assert s.startswith(prefix) and s.endswith(suffix),answer
  body=s[len(prefix):-len(suffix)];(work/'exercise.go').write_text(prefix+body+suffix)
  out=run(l['id']+'-'+answer.stem+'-test',['test','-count=1','-v','./...'],work)
  assert '[no test files]' not in out and '--- SKIP:' not in out
  for name in l['required_tests']:assert re.search(r'^--- PASS: '+name+r' ',out,re.M),name
  for name in l['cases']:assert re.search(r'^\s+--- PASS: TestContract/'+name+r' ',out,re.M),name
  run(l['id']+'-'+answer.stem+'-vet',['vet','./...'],work)
  run(l['id']+'-'+answer.stem+'-race-repeat',['test','-race','-count=10','./...'],work)
  out=run(l['id']+'-'+answer.stem+'-demo',['run','./cmd/'+l['cmd']],work);assert out==l['output']
 for mutant in sorted((g/'wrong-solutions').glob('*.txt')):
  s=mutant.read_text();assert s.startswith(prefix) and s.endswith(suffix),mutant
  (work/'exercise.go').write_text(s)
  run(l['id']+'-mutant-'+mutant.stem,['test','-count=1','-v','./...'],work,False)
 (work/'exercise.go').write_text(author)
 main=work/'cmd'/l['cmd']/'main.go';original=main.read_text();marker=original.index('func main()')
 main.write_text(original[:marker]+'func main() { _ = os.Stdout }\n')
 run(l['id']+'-caller-missing-invocation',['test','-count=1','-v','./...'],work,False,'MAIN_CALL:');main.write_text(original)
 saved=env.copy();env['GOCACHE']=str(R/'work'/('clean-cache-'+l['slug']));env['GOMODCACHE']=str(R/'work'/('clean-mod-'+l['slug']))
 shutil.rmtree(env['GOCACHE'],ignore_errors=True);shutil.rmtree(env['GOMODCACHE'],ignore_errors=True)
 run(l['id']+'-clean-module',['test','-count=1','-v','./...'],work);env=saved
 rows.append(dict(check=l['id']+'-yaml-utf16-visible-answers',status='PASSED'))
result=dict(candidate_status='SOURCE_CANDIDATE',toolchain=V,checks=rows,java_junit='NOT_RUN_SEE_SEPARATE_CURRENT_EVIDENCE',gradle_integration='NOT_RUN',native_academy='NOT_RUN',go_ide_debugger='NOT_RUN',github_actions='NOT_RUN',business_counts={'table_subcases':sum(len(l['cases']) for l in lessons),'main_process_subcases':6,'top_level_tests':sum(len(l['required_tests']) for l in lessons),'mutants':sum(len(l['mutants']) for l in lessons),'correct_variants':6},note='重复、变体与错解不重复计为独立业务用例；测试结果不得应用于发生变化的源码。')
(E/'verification.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n');print(json.dumps(result,ensure_ascii=False,indent=2))
