#!/usr/bin/env python3
"""真实javac+JVM策略断言；正确变体必须通过，starter/错误解必须编译成功后被语义断言杀死。"""
import argparse,json,pathlib,shutil,subprocess,tempfile
if not __debug__:raise RuntimeError("Grading requires Python assertions")
from verification_guard import claim_report,require_selection,VerificationSetupError
ROOT=pathlib.Path(__file__).resolve().parents[1]
VARIANTS={
 'reference-expression':({},True),
 'reference-explicit-ready':({'CloudPolicy.java':'answers/CloudPolicy-explicit.java.txt'},True),
 'reference-explicit-address':({'AddressPolicy.java':'answers/AddressPolicy-explicit.java.txt'},True),
 'starter-ready-always-true':({'CloudPolicy.java':'starter/CloudPolicy.java.txt'},False),
 'starter-localhost':({'AddressPolicy.java':'starter/AddressPolicy.java.txt'},False),
}
def run(evidence):
    selected=require_selection(VARIANTS,['reference-expression','reference-explicit-ready','reference-explicit-address','starter-ready-always-true','starter-localhost'],'Java policy variants')
    if len(selected)!=5:raise VerificationSetupError('Full policy matrix requires all reference and starter variants')
    context=claim_report(evidence)
    results=[];report={'run_id':context['run_id'],'status':'FAIL','scope':'JDK21 policy contracts only; Docker image and network variants NOT_RUN','selected':selected,'variants':results}
    expected_assertions={'starter-ready-always-true':'java.lang.AssertionError: ready requires dependency+seed and rejects draining:',
                         'starter-localhost':'java.lang.AssertionError: container must use injected service DNS'}
    try:
        for name in selected:
            overrides,expected=VARIANTS[name]
            with tempfile.TemporaryDirectory(prefix='c11-policy-') as directory:
                path=pathlib.Path(directory);src=path/'src';shutil.copytree(ROOT/'src',src)
                for target,source in overrides.items():shutil.copy2(ROOT/source,src/'labs'/target)
                classes=path/'classes';classes.mkdir()
                sources=[str(p) for p in (src/'labs').glob('*.java')]+[str(ROOT/'test-java/labs/PolicyContractTest.java')]
                compile=subprocess.run(['javac','--release','21','-encoding','UTF-8','-d',str(classes)]+sources,capture_output=True,text=True,timeout=30)
                if compile.returncode:raise VerificationSetupError(name+': javac failed; this is not a killed wrong solution')
                test=subprocess.run(['java','-cp',str(classes),'labs.PolicyContractTest'],capture_output=True,text=True,timeout=10)
                if expected and test.returncode:raise VerificationSetupError(name+': reference policy did not pass')
                if not expected and (test.returncode==0 or expected_assertions[name] not in test.stderr):
                    raise VerificationSetupError(name+': expected named policy assertion was not observed')
                results.append({'name':name,'compile':'PASS','expected_test_pass':expected,'observed':'PASS' if expected else 'EXPECTED_SEMANTIC_FAILURE','stdout':test.stdout,'stderr':test.stderr})
        if len(results)!=len(selected):raise VerificationSetupError('Incomplete policy matrix')
        report['status']='PASS'
    finally:evidence.write_text(json.dumps(report,indent=2)+'\n')
    print('PASS',len(results),'policy variants')
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--evidence',type=pathlib.Path,required=True);a=p.parse_args();a.evidence.parent.mkdir(parents=True,exist_ok=True);run(a.evidence)
