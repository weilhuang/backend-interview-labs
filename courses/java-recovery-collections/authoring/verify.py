#!/usr/bin/env python3
"""运行真正的JUnit5：参考解及替代正确解通过，未完成实现和错误变体失败。

使用指定的JUnit控制台JAR，不下载依赖。临时副本不修改作者答案。
独立JUnit测试不等于Academy界面验收。
"""
from pathlib import Path
import argparse, hashlib, json, re, shutil, subprocess, sys
from validate_course import ROOT, read_yaml, student_source, validate

p=argparse.ArgumentParser()
p.add_argument('--junit-console',type=Path,required=True)
p.add_argument('--java-module-compiler',action='store_true',help='缺少javac启动器时，使用已有jdk.compiler模块')
p.add_argument('--source-target-only',action='store_true',help='缺少ct.sym时显式降级为source/target21；不代表--release21验证')
args=p.parse_args()
jar=args.junit_console.resolve()
expected='b016ef6b1c3454d6d7c2c88ce081dabf289699686af6622d6e4e2e1b54b4a2fc'
assert hashlib.sha256(jar.read_bytes()).hexdigest()==expected, 'Unexpected JUnit 1.11.4 standalone jar digest'
validate()
work=ROOT/'build/verification'
if work.exists():shutil.rmtree(work)
work.mkdir(parents=True)
manifest=json.loads((ROOT/'authoring/manifest.json').read_text())
compiler=['java','com.sun.tools.javac.Main'] if args.java_module_compiler else ['javac']
flags=['-source','21','-target','21'] if args.source_target_only else ['--release','21']
report={'metadata':'passed','compiler':compiler,'compiler_flags':flags,'jdk21_release_verified':not args.source_target_only,'junit_console_sha256':expected,'gradle':'not run by this script','idea_academy':'not run','tasks':[]}

def run_case(name, entries, expected_pass):
    directory=work/name
    directory.mkdir(parents=True)
    files=[]
    for relative,contents in entries:
        path=directory/relative
        path.parent.mkdir(parents=True,exist_ok=True)
        path.write_text(contents,encoding='utf-8')
        files.append(str(path))
    classes=directory/'classes'
    classes.mkdir()
    compile_result=subprocess.run(compiler+flags+['-encoding','UTF-8','-cp',str(jar),'-d',str(classes)]+files,text=True,capture_output=True,timeout=60)
    (directory/'compile.log').write_text(compile_result.stdout+compile_result.stderr)
    if compile_result.returncode:
        raise RuntimeError(f'{name}: did not compile. See {directory}/compile.log')
    test_result=subprocess.run(['java','-jar',str(jar),'execute','--class-path',str(classes),'--scan-class-path','--disable-banner','--disable-ansi-colors','--details','summary'],text=True,capture_output=True,timeout=60)
    output=test_result.stdout+test_result.stderr
    (directory/'junit.log').write_text(output)
    counts={key:int(re.search(r'\[\s*(\d+) tests '+key+r'\s*\]',output).group(1)) for key in ['found','successful','failed']}
    assert counts['found']>0, f'{name}: no tests discovered'
    if expected_pass:
        assert test_result.returncode==0 and counts['failed']==0, f'{name}: reference failed; see {directory}/junit.log'
    else:
        assert test_result.returncode==1 and counts['failed']>0, f'{name}: negative case escaped or engine errored; see {directory}/junit.log'
    print(name,counts,flush=True)
    return counts

all_entries=[]
for item in manifest:
    task=ROOT/item['task']
    for key in ['source','usage','test','examples']:
        all_entries.append((item['task']+'/'+item[key],(task/item[key]).read_text()))
report['reference']=run_case('reference',all_entries,True)
report['caller_usage']=[]
for item in manifest:
    result=subprocess.run(['java','-cp',str(work/'reference/classes'),'labs.'+item['class']+'Usage'],capture_output=True,text=True,timeout=10)
    assert result.returncode==0,(item['class'],result.stderr)
    assert result.stdout==item['usage_expected_output'],(item['class'],result.stdout)
    report['caller_usage'].append({'class':item['class']+'Usage','status':'passed','stdout':result.stdout})

for item in manifest:
    task=ROOT/item['task']; config=read_yaml(task/'task-info.yaml')
    source=(task/item['source']).read_text(); tests=(task/item['test']).read_text(); examples=(task/item['examples']).read_text()
    placeholders=next(f['placeholders'] for f in config['files'] if f['name']==item['source'])
    stub=student_source(source,placeholders)
    record={'task':item['task'],'unmodified_learner':run_case('stub-'+item['class'],[(item['source'],stub),(item['test'],tests),(item['examples'],examples)],False),'mutants':[]}
    for index,(old,new) in enumerate(item['mutations']):
        assert source.count(old)==1,(item['task'],old)
        mutated=source.replace(old,new)
        record['mutants'].append(run_case('mutant-'+item['class']+'-'+str(index),[(item['source'],mutated),(item['test'],tests),(item['examples'],examples)],False))
    record['alternative_correct'] = run_case('alternative-'+item['class'], [(item['source'], (ROOT/item['alternative']).read_text()), (item['test'], tests), (item['examples'], examples)], True)
    report['tasks'].append(record)
# 故意构造死循环，必须被实际报告为超时失败。
hash_task=next(item for item in manifest if item['class']=='HashIndex')
loop_source=(ROOT/hash_task['task']/hash_task['source']).read_text().replace('return hash ^ (hash >>> 16);', 'while (true) { Thread.onSpinWait(); }')
probe_test="""import labs.HashIndex;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.Timeout;
import java.util.concurrent.TimeUnit;
class TimeoutProbeTest {
 @Test @Timeout(value=250, unit=TimeUnit.MILLISECONDS, threadMode=Timeout.ThreadMode.SEPARATE_THREAD)
 void nonterminatingLearnerIsRejected() { HashIndex.spread(1); }
}
"""
report['timeout_probe']=run_case('timeout-probe', [(hash_task['source'],loop_source),('test/TimeoutProbeTest.java',probe_test)], False)
assert 'timed out after' in (work/'timeout-probe/junit.log').read_text()
report['alternative_correct_implementations_passed']=len(report['tasks'])
report['status']='passed'
report['untouched_learner_tasks_rejected']=len(report['tasks'])
report['mutants_rejected']=sum(len(x['mutants']) for x in report['tasks'])
(work/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
print('PASS. Report:',work/'report.json')
