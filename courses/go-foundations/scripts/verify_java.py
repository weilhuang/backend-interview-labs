"""独立JUnit桥验证入口；使用已准备的JDK21、JUnit与固定Go工具链。"""
from pathlib import Path
import subprocess,os,json,yaml,shutil,hashlib,argparse
R=Path(__file__).resolve().parents[1]
parser=argparse.ArgumentParser();parser.add_argument('--lesson');parser.add_argument('--evidence-dir',default='java');args=parser.parse_args()
E=R/'evidence'/args.evidence_dir;E.mkdir(parents=True,exist_ok=True)
selected=[l for l in json.loads((R/'manifest/lessons.json').read_text()) if not args.lesson or l['id']==args.lesson]
J=Path(os.environ['JAVA_HOME'])/'bin';JAR=Path(os.environ['JUNIT_CONSOLE_JAR']);GO=os.environ['GO_EXECUTABLE'];rows=[]
for l in selected:
 t=R/'overlay/go-course/core'/l['slug'];w=R/'work/java'/l['slug'];w.mkdir(parents=True,exist_ok=True);classes=w/'classes';classes.mkdir(exist_ok=True)
 p=subprocess.run([str(J/'javac'),'-encoding','UTF-8','--release','21','-cp',str(JAR),'-d',str(classes),*[str(x) for x in (t/'src').glob('*.java')],*[str(x) for x in (t/'test').glob('*.java')]],text=True,capture_output=True)
 (E/(l['id']+'-compile.log')).write_text(p.stdout+p.stderr);assert p.returncode==0,p.stderr
 y=yaml.safe_load((t/'task-info.yaml').read_text());hole=y['files'][0]['placeholders'][0];author=(t/'go/exercise.go').read_text();b=author.encode('utf-16-le');starter=(b[:hole['offset']*2]+hole['placeholder_text'].encode('utf-16-le')+b[(hole['offset']+hole['length'])*2:]).decode('utf-16-le')
 project=w/'go';shutil.rmtree(project,ignore_errors=True);shutil.copytree(t/'go',project)
 variants={'starter':starter,**{p.stem:p.read_text() for p in (t/'go/answers').glob('*.txt')},'invalid-env':author}
 if (t/'go/wrong-solutions/prevalidate-all-first.go.txt').is_file():variants['mutant-prevalidate']=(t/'go/wrong-solutions/prevalidate-all-first.go.txt').read_text()
 for label,source in variants.items():
  (project/'exercise.go').write_text(source);reports=E/(l['id']+'-'+label+'-xml')
  command=[str(J/'java'),'-XX:ActiveProcessorCount=2','-Xmx384m','-Dgo.executable='+ (GO if label!='invalid-env' else str(w/'missing-go')),'-Dgo.project='+str(project),'-Dgo.work='+str(w/'go-check'),'-jar',str(JAR),'execute','--class-path',str(classes),'--scan-class-path','--disable-ansi-colors','--reports-dir',str(reports)]
  p=subprocess.run(command,text=True,capture_output=True,timeout=150);out=p.stdout+p.stderr;(E/(l['id']+'-'+label+'.log')).write_text(out)
  if label in ['starter','mutant-prevalidate']:ok=p.returncode!=0 and 'Go业务测试失败' in out and '[         2 tests successful' in out and '[         1 tests failed' in out
  elif label=='invalid-env':ok=p.returncode!=0 and 'INVALID_ENV' in out and '[         1 tests failed' in out
  else:ok=p.returncode==0 and '[         3 tests successful' in out and '[         0 tests failed' in out
  rows.append(dict(check=l['id']+'-'+label,status='PASSED' if ok else 'FAILED',exit_code=p.returncode,log=str((E/(l['id']+'-'+label+'.log')).relative_to(R))))
  assert ok,out
(E/'verification.json').write_text(json.dumps(dict(candidate_status='SOURCE_CANDIDATE',jdk=subprocess.check_output([str(J/'java'),'-version'],stderr=subprocess.STDOUT,text=True),checks=rows,scope=[l['id'] for l in selected],source_hashes={str(p.relative_to(R)):hashlib.sha256(p.read_bytes()).hexdigest() for l in selected for p in sorted((R/'overlay/go-course/core'/l['slug']).rglob('*')) if p.is_file() and (p.suffix in ['.java','.go'] or p.name=='go.mod')},native_academy='NOT_RUN',gradle_integration='NOT_RUN'),ensure_ascii=False,indent=2)+'\n')
print(json.dumps(rows,ensure_ascii=False,indent=2))
