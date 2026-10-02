"""公开 JUnit 桥的 27 场景独立验证；不替代 Gradle 或原生 Academy 验收。"""
from pathlib import Path
import sys
if sys.flags.optimize:
    import json
    evidence = Path(__file__).resolve().parents[1] / 'evidence/bridge-ci'
    evidence.mkdir(parents=True, exist_ok=True)
    (evidence / 'final-summary.json').write_text(json.dumps({
        'status': 'FAILED', 'failure': 'OPTIMIZATION_FORBIDDEN: run without -O or PYTHONOPTIMIZE',
        'scenarios': 0
    }) + '\n')
    raise SystemExit(2)
import subprocess, os, json, yaml, shutil, hashlib, time, re
import xml.etree.ElementTree as ET

R = Path(__file__).resolve().parents[1]
C = R
E = R / 'evidence/bridge-ci'
commands, results = [], []

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def source_hashes():
    return {str(p.relative_to(R)): sha(p) for p in sorted(R.rglob('*'))
            if p.is_file() and p.relative_to(R).parts[0] not in {'work', 'evidence'}
            and '__pycache__' not in p.parts and p.suffix != '.pyc'}

def run(command, cwd, tag, timeout=150):
    start = time.monotonic()
    try:
        p = subprocess.run(command, cwd=cwd, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired as exc:
        output = exc.stdout or b''
        if isinstance(output, bytes):
            output = output.decode(errors='replace')
        p = subprocess.CompletedProcess(command, 124, output, '\nBRIDGE_RUNNER_TIMEOUT\n')
    except OSError as exc:
        p = subprocess.CompletedProcess(command, 125, '', str(exc))
    log = E / (tag + '.log')
    log.write_text(p.stdout + p.stderr)
    commands.append({'command': command, 'cwd': str(cwd), 'exit_code': p.returncode,
                     'elapsed_seconds': time.monotonic() - start,
                     'log': str(log.relative_to(R)), 'log_sha256': sha(log)})
    (E / 'actual-commands.json').write_text(json.dumps(commands, ensure_ascii=False, indent=2) + '\n')
    if p.returncode in (124, 125):
        raise RuntimeError('INVALID_ENV: ' + tag + ' runner failure, not business-negative evidence')
    return p

java_home = Path(os.environ.get('JAVA_HOME', ''))
java = str(java_home / 'bin/java')
javac = str(java_home / 'bin/javac')
go = os.environ.get('GO_EXECUTABLE', '')
jar = Path(os.environ.get('JUNIT_CONSOLE_JAR', ''))


EXPECTED = {
    'C13-01': ('greeting', {'explicit', 'helpers'}, {'constant', 'no-trim', 'empty-not-guest'}),
    'C13-02': ('quantity', {'stdlib', 'manual'}, {'ignore-error', 'empty-is-one', 'overflow-zero', 'accept-plus'}),
    'C13-03': ('order-total', {'explicit', 'checked'}, {'unchecked', 'float-money', 'mutate-shared', 'copy-line-reset', 'prevalidate-all-first'}),
}
EXPECTED_JUNIT = {('GoContractTest', 'goFoundationContract()'),
                  ('GoTestBridgeTest', 'rejectsFalseGreen()'), ('GoTestBridgeTest', 'exactVersionOnly()')}
CONTRACT_TEST = ('GoContractTest', 'goFoundationContract()')

def require(condition, message):
    if not condition:
        raise ValueError(message)

def exact(values, expected, label):
    require(len(values) == len(expected) and set(values) == set(expected), 'INVENTORY: ' + label)

def validate_inventory(lessons):
    exact([lesson['id'] for lesson in lessons], EXPECTED, 'lesson IDs')
    for lesson in lessons:
        slug, variants, mutants = EXPECTED[lesson['id']]
        require(lesson['slug'] == slug, 'INVENTORY: lesson slug')
        exact(lesson['variants'], variants, slug + ' variants')
        exact(lesson['mutants'], mutants, slug + ' mutants')

def validate_scenarios(lesson_id, scenarios):
    _, variants, mutants = EXPECTED[lesson_id]
    expected = {'starter': 'BUSINESS_RED', 'missing-go': 'ENVIRONMENT_REJECTED', 'syntax-error': 'COMPILE_REJECTED'}
    expected.update({'answer-' + name + '.go': 'CORRECT' for name in variants})
    expected.update({'mutant-' + name + '.go': 'BUSINESS_RED' for name in mutants})
    exact([name for name, _, _ in scenarios], expected, lesson_id + ' scenario IDs')
    for name, classification, _ in scenarios:
        require(classification == expected[name], 'INVENTORY: wrong scenario classification')

def prepare_xml_dir(path):
    shutil.rmtree(path, ignore_errors=True)
    path.mkdir(parents=True)
    require(not list(path.iterdir()), 'STALE_XML')

def validate_junit(xml, expectation):
    cases = []
    for report in xml.glob('TEST-*.xml'):
        suite = ET.parse(report).getroot()
        require(suite.tag == 'testsuite', 'JUNIT_WRONG_REPORT_ROOT')
        require(int(suite.get('errors', '0')) == 0 and int(suite.get('skipped', '0')) == 0, 'JUNIT_SUITE_SKIP_OR_ERROR')
        cases.extend(suite.findall('.//testcase'))
    exact([(c.get('classname'), c.get('name')) for c in cases], EXPECTED_JUNIT, 'JUnit class/methods')
    require(all(c.find('skipped') is None and c.find('error') is None for c in cases), 'JUNIT_SKIP_OR_ERROR')
    failures = [(c, c.find('failure')) for c in cases if c.find('failure') is not None]
    if expectation == 'CORRECT':
        require(not failures, 'JUNIT_UNEXPECTED_FAILURE')
    else:
        require(len(failures) == 1, 'JUNIT_FAILURE_COUNT')
        case, failure = failures[0]
        require((case.get('classname'), case.get('name')) == CONTRACT_TEST, 'JUNIT_WRONG_FAILURE_TARGET')
        if expectation == 'BUSINESS_RED':
            require(failure.get('type') == 'java.lang.AssertionError', 'JUNIT_NON_BUSINESS_FAILURE')
            message = ''.join(failure.itertext()) + failure.get('message', '')
            require(not any(x in message for x in ['INVALID_ENV', 'CHECK_TIMEOUT', 'syntax error', '[build failed]', 'undefined:']), 'JUNIT_INFRA_AS_BUSINESS')
    return cases, len(failures)

def verify():
    if not os.environ.get('JAVA_HOME') or not java_home.is_absolute() or not Path(java).is_file() or not Path(javac).is_file():
        raise RuntimeError('INVALID_ENV: JAVA_HOME must name a complete JDK 21 with java and javac')
    if not Path(go).is_absolute() or not Path(go).is_file():
        raise RuntimeError('INVALID_ENV: GO_EXECUTABLE must name Go 1.27.1')
    if not jar.is_absolute() or not jar.is_file() or sha(jar) != 'b016ef6b1c3454d6d7c2c88ce081dabf289699686af6622d6e4e2e1b54b4a2fc':
        raise RuntimeError('INVALID_ENV: expected official JUnit Platform Console Standalone 1.11.4 SHA256')
    version = run([javac, '-version'], R, 'javac-version', 15)
    if version.returncode or not re.match(r'javac 21(?:[.\s]|$)', version.stdout + version.stderr):
        raise RuntimeError('INVALID_ENV: javac 21 required')
    version = run([go, 'version'], R, 'go-version', 15)
    if version.returncode or not re.fullmatch(r'go version go1\.27\.1 [\w]+/[\w]+\s*', version.stdout):
        raise RuntimeError('INVALID_ENV: Go 1.27.1 required')
    shutil.rmtree(R / 'work/bridge-ci', ignore_errors=True)
    lessons = json.loads((C/'manifest/lessons.json').read_text())
    validate_inventory(lessons)
    for l in lessons:
     task=C/'overlay/go-course/core'/l['slug'];work=R/'work/bridge-ci'/l['slug'];classes=work/'classes';classes.mkdir(parents=True,exist_ok=True);project=work/'go';shutil.copytree(task/'go',project,dirs_exist_ok=True)
     compilation=[javac,'-J-XX:ActiveProcessorCount=2','-J-Xmx384m','-encoding','UTF-8','--release','21','-cp',str(jar),'-d',str(classes),*[str(p) for p in sorted((task/'src').glob('*.java'))],*[str(p) for p in sorted((task/'test').glob('*.java'))]]
     p=run(compilation,task,l['id']+'-compile-java',60);assert p.returncode==0,p.stdout+p.stderr
     author=(task/'go/exercise.go').read_text();y=yaml.safe_load((task/'task-info.yaml').read_text());h=y['files'][0]['placeholders'][0];b=author.encode('utf-16-le');pre=b[:h['offset']*2].decode('utf-16-le');post=b[(h['offset']+h['length'])*2:].decode('utf-16-le')
     assert '🧪' in pre and len(pre)!=h['offset'] and post.startswith('\t// 练习区结束')
     scenarios=[('starter','BUSINESS_RED',pre+h['placeholder_text']+post)]
     scenarios += [('answer-'+p.stem,'CORRECT',p.read_text()) for p in sorted((task/'go/answers').glob('*.txt'))]
     scenarios += [('mutant-'+p.stem,'BUSINESS_RED',p.read_text()) for p in sorted((task/'go/wrong-solutions').glob('*.txt'))]
     scenarios += [('missing-go','ENVIRONMENT_REJECTED',author),('syntax-error','COMPILE_REJECTED',pre+'\treturn ???\n'+post)]
     validate_scenarios(l['id'], scenarios)
     fixed={str(p.relative_to(task/'go')):sha(p) for p in (task/'go').rglob('*') if p.is_file() and p.name!='exercise.go'}
     for label,expect,source in scenarios:
      assert source.startswith(pre) and source.endswith(post),label
      (project/'exercise.go').write_text(source)
      for path,digest in fixed.items():assert sha(project/path)==digest,(label,path)
      bridgework=work/'go-check';bridgework.mkdir(exist_ok=True)
      for name in ['version.log','go-tests.log']:(bridgework/name).unlink(missing_ok=True)
      tag=l['id']+'-'+label;xml=work/(tag+'-xml');prepare_xml_dir(xml)
      command=[java,'-XX:ActiveProcessorCount=2','-Xmx384m','-Dgo.executable='+ (str(work/'missing-go') if expect=='ENVIRONMENT_REJECTED' else go),'-Dgo.project='+str(project),'-Dgo.work='+str(bridgework),'-jar',str(jar),'execute','--class-path',str(classes),'--scan-class-path','--disable-ansi-colors','--reports-dir',str(xml)]
      p=run(command,task,tag);out=p.stdout+p.stderr
      cases,fails=validate_junit(xml,expect);skips=0
      testlog=bridgework/'go-tests.log';gout=testlog.read_text() if testlog.exists() else None
      if expect=='CORRECT':
       ok=p.returncode==0 and fails==0 and gout is not None
       if ok:
        ok='--- SKIP:' not in gout and '[no test files]' not in gout
        for name in l['required_tests']:ok=ok and bool(re.search(r'^--- PASS: '+re.escape(name)+r' ',gout,re.M))
        for name in l['cases']:ok=ok and bool(re.search(r'^\s+--- PASS: TestContract/'+re.escape(name)+r' ',gout,re.M))
      elif expect=='BUSINESS_RED':
       ok=p.returncode!=0 and fails==1 and gout is not None and '=== RUN   TestContract' in gout and '--- FAIL:' in gout
       ok=ok and ({'C13-01':'GREETING:', 'C13-02':'QUANTITY:', 'C13-03':'TOTAL:'}[l['id']] in (gout or '') or (l['id']=='C13-03' and 'TOTAL_' in (gout or ''))) and not any(marker in (gout or '') for marker in ['[build failed]','syntax error','undefined:','CHECK_TIMEOUT','INVALID_ENV'])
      elif expect=='ENVIRONMENT_REJECTED':ok=p.returncode!=0 and fails==1 and 'INVALID_ENV' in out and gout is None
      else:ok=p.returncode!=0 and fails==1 and gout is not None and '[build failed]' in gout and '=== RUN   TestContract' not in gout
      saved={}
      for name in ['version.log','go-tests.log']:
       path=bridgework/name
       if path.exists():dest=E/(tag+'-'+name);shutil.copyfile(path,dest);saved[name]={'path':str(dest.relative_to(R)),'sha256':sha(dest)}
      record={'lesson':l['id'],'scenario':label,'expected':expect,'status':'PASSED' if ok else 'FAILED','junit_process_exit':p.returncode,'junit_tests':len(cases),'junit_failures':fails,'junit_skips':skips,'exercise_sha256':sha(project/'exercise.go'),'unchanged_go_files_verified':len(fixed),'source_change_limited_to_utf16_region':True,'go_logs':saved,'classification':'Valid business-negative evidence' if expect=='BUSINESS_RED' else 'Environment/compile control; NOT a successful business counterexample' if expect in ['ENVIRONMENT_REJECTED','COMPILE_REJECTED'] else 'Correct implementation passed real Go tests'}
      results.append(record);(E/'scenario-results.json').write_text(json.dumps(results,ensure_ascii=False,indent=2)+'\n');assert ok,(tag,record,out[-4000:])

    assert len(results) == 27, 'Expected exact 27 bridge scenarios'

def main():
    E.mkdir(parents=True, exist_ok=True)
    before = source_hashes()
    (E / 'input-source-hashes.json').write_text(json.dumps(before, ensure_ascii=False, indent=2) + '\n')
    failure = None
    try:
        verify()
    except Exception as exc:
        failure = type(exc).__name__ + ': ' + str(exc)
    finally:
        unchanged = before == source_hashes()
        if not unchanged:
            failure = (failure + '; ' if failure else '') + 'SOURCE_CHANGED'
        summary = {'status': 'FAILED' if failure else 'PASSED', 'failure': failure,
                   'source_unchanged': unchanged, 'source_files_checked': len(before),
                   'compiler': 'javac --release 21; no fallback', 'go': '1.27.1', 'junit_platform': '1.11.4',
                   'scenarios': len(results), 'correct_implementations': sum(r['expected'] == 'CORRECT' for r in results),
                   'student_starters_business_red': sum(r['scenario'] == 'starter' for r in results),
                   'exercise_mutants_business_red': sum(r['scenario'].startswith('mutant-') for r in results),
                   'missing_go_controls': sum(r['expected'] == 'ENVIRONMENT_REJECTED' for r in results),
                   'compile_failure_controls': sum(r['expected'] == 'COMPILE_REJECTED' for r in results),
                   'gradle_integration': 'NOT_RUN', 'native_academy': 'NOT_RUN',
                   'note': '环境与编译失败控制不属于成功的业务反例；重复场景不冒充独立业务用例。'}
        (E / 'final-summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2) + '\n')
        print(json.dumps(summary, ensure_ascii=False, indent=2))
    if failure:
        raise SystemExit(1)

if __name__ == '__main__':
    main()
