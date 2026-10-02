"""只mock subprocess边界，不启动Java/Gradle/HTTP。控制样本通过不代表真实运行通过。"""
import datetime,importlib.util,json,os,shutil,subprocess,sys,tempfile,time,unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
import xml.etree.ElementTree as ET
ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('identity_gate_r2',ROOT/'scripts/verify_finalizedby_gate.py')
gate=importlib.util.module_from_spec(spec);spec.loader.exec_module(gate)
CONTRACT=json.loads((ROOT/'gate-contract.json').read_text())
ORIGIN='labs.identity.ProductionPolicyOriginTest'
HTTP='labs.identity.IdentityNetworkTest'
POLICY='labs.identity.PolicyTest'
PROBES=[
'positive_network_suite_missing','positive_network_suite_zero_tests','positive_wrong_unit_suite',
'positive_missing_origin_methods','negative_reversed_http_direction','negative_infrastructure_error',
'negative_skipped_frontend','negative_fake_401_message','stale_xml_timestamp_and_mtime',
'missing_locks','missing_receipt','wrong_run_id','wrong_binding_hash','wrong_source_hash','wrong_config_hash','wrong_lock_hash',
'wrong_actual_toolchain','missing_build_receipt','cached_compile','missing_http_observation','wrong_observed_http_status','counter_mismatch',
'duplicate_case','unexpected_suite','cached_task','up_to_date_task','no_source_task',
'wrong_assertion_type','extra_compile_failure','wrong_failure_task','source_changed','input_changed','timeout',
'negative_exit_zero','negative_exit_signal','stale_receipt_time','missing_case_receipt','zero_test_finish'
]
def write_xml(folder,suite,cases,mode,stale):
    folder.mkdir(parents=True,exist_ok=True)
    counts={'tests':len(cases),'failures':sum(c['state']=='failure' for c in cases),
        'errors':sum(c['state']=='error' for c in cases),'skipped':sum(c['state']=='skipped' for c in cases)}
    if mode=='counter_mismatch':counts['tests']+=1
    root=ET.Element('testsuite',name=suite,**{k:str(v) for k,v in counts.items()},
        timestamp='2000-01-01T00:00:00' if stale else datetime.datetime.now(datetime.timezone.utc).isoformat())
    for row in cases:
        c=ET.SubElement(root,'testcase',name=row['method']+'()',classname=suite)
        if row['state']!='success':
            status=row['state'];node=ET.SubElement(c,status,type=row.get('type',''),message=row.get('message',''))
            node.text=row.get('message','')+'\n at '+suite+'.'+row['method']+'(IdentityNetworkTest.java:38)'
    p=folder/('TEST-'+suite+'.xml');ET.ElementTree(root).write(p,encoding='utf-8',xml_declaration=True)
    if stale:os.utime(p,(946684800,946684800))
def fake_process(cmd,mode,**kwargs):
    required=['--no-build-cache','--no-configuration-cache','--rerun-tasks','--console=plain']
    assert all(x in cmd for x in required)
    dest=Path(cmd[cmd.index('-p')+1])
    input_path=Path(next(x.split('=',1)[1] for x in cmd if x.startswith('-PidentityGateInput=')))
    data=json.loads(input_path.read_text());negative=data['negative']
    if mode=='timeout' and negative:raise subprocess.TimeoutExpired(cmd,600)
    unit={c:[{'method':m,'state':'success'} for m in methods] for c,methods in CONTRACT['unit'].items()}
    http={c:[{'method':m,'state':'success'} for m in methods] for c,methods in CONTRACT['http'].items()}
    if negative:
        http[HTTP][0].update(state='failure',type=gate.ASSERTION_TYPE,message=gate.NEGATIVE_MESSAGE)
    if not negative:
        if mode=='positive_network_suite_missing':http.pop(HTTP)
        if mode=='positive_network_suite_zero_tests':http[HTTP]=[]
        if mode=='positive_wrong_unit_suite':unit={'unrelated.SmokeTest':[{'method':'arithmeticOnly','state':'success'}]}
        if mode=='positive_missing_origin_methods':
            http[ORIGIN]=[{'method':m,'state':'success'} for m in ['unrelatedFirst','unrelatedSecond']]
    if negative:
        if mode=='negative_reversed_http_direction':http[HTTP][0]['message']=gate.MARKER+' ==> expected: <401> but was: <200>'
        if mode=='negative_infrastructure_error':http[HTTP][1].update(state='error',type='java.net.ConnectException',message='Connection refused')
        if mode=='negative_skipped_frontend':http[HTTP][1].update(state='skipped',message='fixture unavailable')
        if mode=='negative_fake_401_message':http[HTTP][0]['message']='java.net.ConnectException: localhost port 40123'
        if mode=='wrong_assertion_type':http[HTTP][0]['type']='java.net.ConnectException'
    if mode=='duplicate_case':unit[POLICY].append(dict(unit[POLICY][0]))
    if mode=='unexpected_suite':http['unrelated.Extra']=[{'method':'extra','state':'success'}]
    stale=mode=='stale_xml_timestamp_and_mtime'
    for suite,cases in unit.items():write_xml(dest/gate.TASK/'build/test-results/test',suite,cases,mode,stale)
    for suite,cases in http.items():write_xml(dest/gate.SERVICE/'build/test-results/httpAcceptance',suite,cases,mode,stale)
    common={k:data[k] for k in ['run_id','binding_sha256','source_sha256','config_sha256','locks_sha256']}
    mutations={'wrong_run_id':'run_id','wrong_binding_hash':'binding_sha256','wrong_source_hash':'source_sha256','wrong_config_hash':'config_sha256','wrong_lock_hash':'locks_sha256'}
    if mode in mutations:common[mutations[mode]]='wrong'
    now=int(time.time()*1000);events=[]
    def emit(**event):events.append({**common,'time_ms':now,**event})
    for task in gate.BUILD_TASKS:
        if mode=='missing_build_receipt' and task==gate.BUILD_TASKS[0]:continue
        cached=mode=='cached_compile' and task==gate.BUILD_TASKS[0]
        emit(kind='task',task=task,executed=True,skipped=cached,up_to_date=False,no_source=False,skip_message='FROM-CACHE' if cached else None,failed=False)
    for task,classes in [(gate.UNIT_TASK,unit),(gate.HTTP_TASK,http)]:
        rows=[(suite,c) for suite,cs in classes.items() for c in cs]
        failures=sum(c['state'] in ['failure','error'] for _,c in rows);skips=sum(c['state']=='skipped' for _,c in rows)
        emit(kind='start',task=task,gradle_version='9.0' if mode=='wrong_actual_toolchain' else '8.10.2',java_major='21')
        for suite,c in rows:
            emit(kind='case',task=task,**{'class':suite,'method':c['method']+'()','result':'SUCCESS' if c['state']=='success' else 'SKIPPED' if c['state']=='skipped' else 'FAILURE'})
        emit(kind='finish',task=task,tests=0 if mode=='zero_test_finish' else len(rows),failed=failures,skipped=skips,successful=len(rows)-failures-skips)
        emit(kind='task',task=task,executed=True,skipped=mode=='cached_task',up_to_date=mode=='up_to_date_task',
            no_source=mode=='no_source_task',skip_message='FROM-CACHE' if mode=='cached_task' else None,failed=failures>0)
    if mode=='extra_compile_failure' and negative:
        emit(kind='task',task=':identity-resource-server:compileJava',executed=True,skipped=False,up_to_date=False,no_source=False,skip_message=None,failed=True)
    if mode=='stale_receipt_time':
        for e in events:e['time_ms']=946684800000
    if mode=='missing_case_receipt':events.pop(next(i for i,e in enumerate(events) if e['kind']=='case'))
    if mode!='missing_receipt':Path(data['receipt']).write_text(''.join(json.dumps(e)+'\n' for e in events))
    if mode!='missing_http_observation':
        trace={'run_id':data['run_id'],'binding_sha256':data['binding_sha256'],'suite':HTTP,'method':gate.METHOD,
            'marker':gate.MARKER,'expected':200,'observed':500 if mode=='wrong_observed_http_status' else 401 if negative else 200,'time_ms':now}
        Path(data['http_trace']).write_text(json.dumps(trace)+'\n')
    if mode=='source_changed':(dest/gate.TASK/'src/labs/identity/Policy.java').write_text('changed after run')
    if mode=='input_changed':input_path.write_text('{}')
    code=1 if negative else 0
    if negative and mode=='negative_exit_zero':code=0
    if negative and mode=='negative_exit_signal':code=139
    stdout=("> Task "+gate.HTTP_TASK+" FAILED\nExecution failed for task '"+gate.HTTP_TASK+"'.\nBUILD FAILED") if negative else 'BUILD SUCCESSFUL'
    if mode=='wrong_failure_task' and negative:stdout="Execution failed for task ':identity-resource-server:compileJava'.\nBUILD FAILED"
    return SimpleNamespace(returncode=code,stdout=stdout,stderr='')
def run_probe(mode):
    with tempfile.TemporaryDirectory(prefix='identity-r2-mock-') as tmp:
        root=Path(tmp)/'fixture';shutil.copytree(ROOT,root,ignore=shutil.ignore_patterns('__pycache__','build','.gradle'))
        for lock in [gate.TASK/'gradle.lockfile',gate.SERVICE/'gradle.lockfile']:
            if mode!='missing_locks':(root/lock).write_text('# MOCK BOUNDARY ONLY; not a usable dependency lock\n')
        gradle=Path(tmp)/'mock-gradle';gradle.write_text('# not executable in this test\n')
        java=Path(tmp)/'mock-jdk/bin/java';java.parent.mkdir(parents=True);java.write_text('# not executed\n')
        output=Path(tmp)/'output'
        argv=['verify_finalizedby_gate.py','--gradle',str(gradle),'--java-home',str(java.parent.parent),'--output',str(output)]
        with patch.object(gate,'ROOT',root),patch.object(sys,'argv',argv),patch.object(gate.subprocess,'run',lambda cmd,**kw:fake_process(cmd,mode,**kw)):
            code=gate.main()
        rows=json.loads((output/'gate-results.json').read_text())
        return code,rows
class GateMockRegression(unittest.TestCase):
    def test_complete_current_bound_mock_is_accepted(self):
        code,rows=run_probe('control')
        self.assertEqual(code,0,rows);self.assertEqual([r['status'] for r in rows],['PASS']*3)
    def test_nine_original_false_green_probes_and_extended_boundaries_rejected(self):
        for probe in PROBES:
            with self.subTest(probe=probe):
                code,rows=run_probe(probe)
                self.assertNotEqual(code,0,(probe,rows))
                self.assertTrue(any(r['status']!='PASS' for r in rows),(probe,rows))
if __name__=='__main__':unittest.main(verbosity=2)
