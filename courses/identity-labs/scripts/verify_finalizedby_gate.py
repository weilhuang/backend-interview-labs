#!/usr/bin/env python3
"""严格验证隔离运行证据。可信Gradle/JDK/测试代码是前提；本解析器不抵御任意恶意执行器。"""
from pathlib import Path
import argparse,datetime,hashlib,json,os,re,shutil,subprocess,time,uuid
import xml.etree.ElementTree as ET

ROOT=Path(__file__).resolve().parents[1]
TASK=Path('identity/01-policy/lab')
SERVICE=Path('materials/identity/identity-lab')
UNIT_TASK=':identity-01-policy-lab:test'
HTTP_TASK=':identity-resource-server:httpAcceptance'
BUILD_TASKS=[':identity-01-policy-lab:compileJava',':identity-01-policy-lab:compileTestJava',':identity-01-policy-lab:jar',
    ':identity-resource-server:compileJava',':identity-resource-server:compileTestJava',':identity-resource-server:verifyProductionPolicyJar']
METHOD='realHttpRequestEnforcesAuthenticationTenantAndWriteRole'
MARKER='C15_HTTP_OWN_ORDER_200'
ASSERTION_TYPE='org.opentest4j.AssertionFailedError'
NEGATIVE_MESSAGE=MARKER+' ==> expected: <200> but was: <401>'
EXCLUDED={'build','.gradle','__pycache__','.git','proposal-evidence','gate-runs'}
class EvidenceError(Exception):pass
def require(condition,message):
    if not condition:raise EvidenceError(message)
def canonical(value):return json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode()
def digest(value):return hashlib.sha256(canonical(value)).hexdigest()
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def source_map(root):
    return {str(p.relative_to(root)):sha(p) for p in sorted(root.rglob('*'))
        if p.is_file() and not (set(p.relative_to(root).parts)&EXCLUDED)}
def method_name(raw):
    require(isinstance(raw,str),'missing testcase method')
    # 两个固定的静态JUnit方法命名形式；不接受任意前缀/子串/动态零用例。
    return raw[:-2] if raw.endswith('()') else raw
def fresh(path,start_ns,end_ns):
    stamp=path.stat().st_mtime_ns
    require(start_ns-2_000_000_000<=stamp<=end_ns+2_000_000_000,'stale/future file: '+str(path))
def read_jsonl(path,start_ns,end_ns):
    require(path.is_file(),'missing receipt: '+str(path));fresh(path,start_ns,end_ns)
    require(path.stat().st_size<=1_000_000,'oversized receipt')
    events=[]
    for line in path.read_text().splitlines():
        require(bool(line.strip()),'empty receipt event')
        event=json.loads(line)
        require(isinstance(event,dict),'invalid receipt object')
        require(type(event.get('time_ms')) is int,'receipt needs integer time_ms')
        require(start_ns/1e6-2000<=event['time_ms']<=end_ns/1e6+2000,'stale/future receipt event')
        events.append(event)
    require(bool(events),'empty receipt')
    return events
def parse_xml(folder,expected,start_ns,end_ns):
    require(folder.is_dir(),'missing XML folder: '+str(folder))
    found={p.name:p for p in folder.glob('TEST-*.xml')}
    require(set(found)=={'TEST-'+s+'.xml' for s in expected},'missing or unexpected suite files')
    results={}
    for suite,methods in expected.items():
        path=found['TEST-'+suite+'.xml'];fresh(path,start_ns,end_ns)
        data=path.read_bytes()
        require(len(data)<=1_000_000 and b'<!DOCTYPE' not in data and b'<!ENTITY' not in data,'unsafe XML')
        root=ET.fromstring(data)
        require(root.tag=='testsuite' and root.get('name')==suite,'wrong suite identity')
        ts=root.get('timestamp')
        require(bool(ts),'missing XML timestamp')
        parsed=datetime.datetime.fromisoformat(ts.replace('Z','+00:00'))
        if parsed.tzinfo is None:parsed=parsed.replace(tzinfo=datetime.timezone.utc)
        require(start_ns/1e9-2<=parsed.timestamp()<=end_ns/1e9+2,'stale/future XML timestamp')
        cases=root.findall('testcase');actual={}
        for c in cases:
            require(c.get('classname')==suite,'wrong testcase class')
            name=method_name(c.get('name'))
            require(name in methods and name not in actual,'unknown or duplicate method: '+name)
            failures=c.findall('failure');errors=c.findall('error');skips=c.findall('skipped')
            require(len(failures)+len(errors)+len(skips)<=1,'multiple outcomes on one method')
            state='failure' if failures else 'error' if errors else 'skipped' if skips else 'success'
            f=failures[0] if failures else None
            actual[name]={'state':state,'failure_type':None if f is None else f.get('type'),
                'failure_message':None if f is None else f.get('message'),
                'failure_text':None if f is None else ''.join(f.itertext())}
        require(set(actual)==set(methods),'missing required methods: '+suite)
        counts={'tests':len(actual),'failures':sum(c['state']=='failure' for c in actual.values()),
            'errors':sum(c['state']=='error' for c in actual.values()),
            'skipped':sum(c['state']=='skipped' for c in actual.values())}
        for key,value in counts.items():require(root.get(key)==str(value),'counter mismatch: '+suite+'/'+key)
        require(counts['tests']>0,'zero executed suite')
        results.update({(suite,name):result for name,result in actual.items()})
    return results
def validate(destination,input_data,result,start_ns,end_ns,contract):
    require(source_map(destination)==input_data['sources'],'source/test/config/lock changed during run')
    require(digest(input_data['sources'])==input_data['source_sha256'],'source binding mismatch')
    unit=parse_xml(destination/TASK/'build/test-results/test',contract['unit'],start_ns,end_ns)
    http=parse_xml(destination/SERVICE/'build/test-results/httpAcceptance',contract['http'],start_ns,end_ns)
    cases={**unit,**http}
    require(all(c['state']=='success' for c in unit.values()),'learner contract not entirely green')
    require(not any(c['state'] in ('error','skipped') for c in cases.values()),'error/skip is never expected')
    negative=input_data['negative']
    failing=[key for key,c in cases.items() if c['state']=='failure']
    expected_key=('labs.identity.IdentityNetworkTest',METHOD)
    if negative:
        require(result.returncode==1,'negative run must have Gradle test failure exit1')
        require(failing==[expected_key],'negative needs exactly one designated assertion failure')
        f=cases[expected_key]
        require(f['failure_type']==ASSERTION_TYPE,'wrong exception type')
        require(f['failure_message']==NEGATIVE_MESSAGE,'wrong marker/assertion direction/value')
        require('labs.identity.IdentityNetworkTest.'+METHOD in (f['failure_text'] or ''),'wrong failure location')
    else:
        require(result.returncode==0,'positive Gradle nonzero exit')
        require(not failing,'positive run is not entirely green')
    receipts=read_jsonl(Path(input_data['receipt']),start_ns,end_ns)
    for event in receipts:
        for key in ['run_id','binding_sha256','source_sha256','config_sha256','locks_sha256']:
            require(event.get(key)==input_data[key],'receipt binding mismatch: '+key)
        require(event.get('kind') in {'start','case','finish','task'},'unknown receipt kind')
    for task,expected_cases in [(UNIT_TASK,unit),(HTTP_TASK,http)]:
        events=[e for e in receipts if e.get('task')==task]
        starts=[e for e in events if e['kind']=='start'];ends=[e for e in events if e['kind']=='finish']
        task_rows=[e for e in events if e['kind']=='task'];test_rows=[e for e in events if e['kind']=='case']
        require(len(starts)==len(ends)==len(task_rows)==1,'missing/duplicate task execution receipts')
        require(starts[0].get('gradle_version')=='8.10.2' and starts[0].get('java_major')=='21','unexpected actual toolchain')
        row=task_rows[0]
        require(row.get('executed') is True and row.get('skipped') is False and row.get('up_to_date') is False
            and row.get('no_source') is False and row.get('skip_message') is None,'cached/skipped/unexecuted task')
        require(len(test_rows)==len(expected_cases),'wrong executed test count')
        seen={}
        for e in test_rows:
            key=(e.get('class'),method_name(e.get('method')))
            require(key in expected_cases and key not in seen,'wrong/duplicate executed testcase receipt')
            expected_result='FAILURE' if expected_cases[key]['state']=='failure' else 'SUCCESS'
            require(e.get('result')==expected_result,'XML/receipt outcome disagreement')
            seen[key]=e
        require(set(seen)==set(expected_cases),'missing executed testcase receipt')
        failures=sum(c['state']=='failure' for c in expected_cases.values())
        require(ends[0].get('tests')==len(expected_cases) and ends[0].get('failed')==failures
            and ends[0].get('skipped')==0 and ends[0].get('successful')==len(expected_cases)-failures,'task totals mismatch')
        require(row.get('failed') is bool(failures),'task failure attribution mismatch')
        require(starts[0]['time_ms']<=ends[0]['time_ms']<=row['time_ms'],'task execution order invalid')
    for task in BUILD_TASKS:
        build_rows=[e for e in receipts if e['kind']=='task' and e.get('task')==task]
        require(len(build_rows)==1,'missing/duplicate required build execution: '+task)
        row=build_rows[0]
        require(row.get('executed') is True and row.get('failed') is False and row.get('skipped') is False
            and row.get('up_to_date') is False and row.get('no_source') is False and row.get('skip_message') is None,
            'required compile/jar/provenance task was not freshly successful: '+task)
    failed_tasks=[e.get('task') for e in receipts if e['kind']=='task' and e.get('failed') is True]
    require(failed_tasks==([HTTP_TASK] if negative else []),'unexpected failing task / compile / infrastructure')
    for e in receipts:
        if e['kind']!='task':require(e.get('task') in {UNIT_TASK,HTTP_TASK},'unexpected test receipt task')
    output=result.stdout+'\n'+result.stderr
    for line in output.splitlines():
        if any(task in line for task in [UNIT_TASK,HTTP_TASK,*BUILD_TASKS]):
            require(not any(x in line for x in ['FROM-CACHE','UP-TO-DATE','NO-SOURCE','SKIPPED']),'cached target in Gradle output')
    if negative:
        require("> Task "+HTTP_TASK+" FAILED" in output,'missing failed httpAcceptance task output')
        require("Execution failed for task '"+HTTP_TASK+"'." in output,'failure not attributed to httpAcceptance')
        require('BUILD FAILED' in output,'missing Gradle failure result')
    trace=read_jsonl(Path(input_data['http_trace']),start_ns,end_ns)
    require(len(trace)==1,'need exactly one actual target HTTP observation')
    t=trace[0]
    require(t.get('run_id')==input_data['run_id'] and t.get('binding_sha256')==input_data['binding_sha256'],'HTTP observation binding mismatch')
    require(t.get('suite')==expected_key[0] and t.get('method')==METHOD and t.get('marker')==MARKER,'wrong HTTP observation identity')
    require(type(t.get('expected')) is int and t['expected']==200,'wrong expected HTTP status')
    require(type(t.get('observed')) is int and t['observed']==(401 if negative else 200),'wrong observed HTTP status')
    return {'unit_cases':len(unit),'http_cases':len(http),'negative':negative,'run_id':input_data['run_id']}
def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--gradle',required=True,help='已批准Gradle8.10.2可执行文件，不安装')
    parser.add_argument('--java-home',required=True,help='已批准JDK21目录')
    parser.add_argument('--output',type=Path,required=True,help='源树外、尚不存在的隔离证据目录')
    args=parser.parse_args();output=args.output.resolve()
    require(not output.is_relative_to(ROOT.resolve()),'output must be outside source tree')
    require(not output.exists(),'refuse existing output; no stale XML reuse')
    output.mkdir(parents=True)
    results=[]
    try:
        gradle=Path(args.gradle).resolve();java=Path(args.java_home).resolve()/'bin/java'
        require(gradle.is_file() and java.is_file(),'approved Gradle/JDK executable missing')
        lock_paths=[TASK/'gradle.lockfile',SERVICE/'gradle.lockfile']
        require(all((ROOT/p).is_file() for p in lock_paths),'fixed shared lock set missing; generate/check locks separately first')
        locks={str(p):sha(ROOT/p) for p in lock_paths};contract=json.loads((ROOT/'gate-contract.json').read_text())
        require(contract['schema']==2,'unsupported gate contract')
        for scenario,variant,negative in [('table-positive','table',False),('explicit-positive','explicit',False),('real-http-negative','table',True)]:
            destination=output/scenario/'source';destination.parent.mkdir()
            shutil.copytree(ROOT,destination,ignore=shutil.ignore_patterns(*EXCLUDED))
            shutil.copyfile(destination/TASK/f'reference/{variant}/Policy.java',destination/TASK/'src/labs/identity/Policy.java')
            sources=source_map(destination);run_id=str(uuid.uuid4())
            config={'scenario':scenario,'negative':negative,'gradle_executable_sha256':sha(gradle),'java_executable_sha256':sha(java),
                'gradle_version':'8.10.2','java_major':'21','contract_sha256':digest(contract),
                'flags':['--no-daemon','--no-build-cache','--no-configuration-cache','--rerun-tasks','--console=plain','--max-workers=1']}
            input_data={'schema':2,'run_id':run_id,'scenario':scenario,'negative':negative,'sources':sources,
                'source_sha256':digest(sources),'config':config,'config_sha256':digest(config),'locks':locks,'locks_sha256':digest(locks),
                'receipt':str(destination.parent/'execution.jsonl'),'http_trace':str(destination.parent/'http.jsonl')}
            input_data['binding_sha256']=digest({k:input_data[k] for k in ['run_id','scenario','source_sha256','config_sha256','locks_sha256']})
            input_file=destination.parent/'input.json';input_file.write_text(json.dumps(input_data,ensure_ascii=False,indent=2)+'\n')
            cmd=[str(gradle),*config['flags'],'-p',str(destination),'clean',UNIT_TASK,
                '-PidentityGateInput='+str(input_file)]
            if negative:cmd.append('-PidentityHttpNegative')
            input_hash=sha(input_file)
            start_ns=time.time_ns()
            try:
                result=subprocess.run(cmd,env={**os.environ,'JAVA_HOME':str(java.parent.parent),'TZ':'UTC'},
                    capture_output=True,text=True,timeout=600)
                end_ns=time.time_ns()
                (destination.parent/'gradle.log').write_text(result.stdout+result.stderr)
                require(sha(input_file)==input_hash,'run input changed during execution')
                require(sha(gradle)==config['gradle_executable_sha256'] and sha(java)==config['java_executable_sha256'],'tool executable changed during run')
                detail=validate(destination,input_data,result,start_ns,end_ns,contract)
                results.append({'scenario':scenario,'status':'PASS','detail':detail,'gradle_exit':result.returncode,
                    'input_sha256':sha(input_file),'binding_sha256':input_data['binding_sha256']})
            except (EvidenceError,ET.ParseError,ValueError,OSError,subprocess.TimeoutExpired) as exc:
                results.append({'scenario':scenario,'status':'FAIL','reason':str(exc),'run_id':run_id})
    except (EvidenceError,ValueError,OSError) as exc:
        results.append({'scenario':'preflight','status':'BLOCKED','reason':str(exc)})
    (output/'gate-results.json').write_text(json.dumps(results,ensure_ascii=False,indent=2)+'\n')
    return 0 if len(results)==3 and all(r['status']=='PASS' for r in results) else 1
if __name__=='__main__':raise SystemExit(main())
