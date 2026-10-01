#!/usr/bin/env python3
"""严格JDK21检查作者、学生起点与固定错解；不包含Docker动态证明。"""
from pathlib import Path
import argparse, json, os, subprocess, shutil
ROOT = Path(__file__).resolve().parents[1]
p = argparse.ArgumentParser(); p.add_argument('--jdk', default=os.environ.get('JAVA_HOME', '')); args = p.parse_args()
JDK = Path(args.jdk)
if not (JDK / 'bin/javac').exists(): raise SystemExit('请传 --jdk 或设置 JAVA_HOME 指向完整JDK21')
BUILD = ROOT / 'build/verification'; BUILD.mkdir(parents=True, exist_ok=True)
DEPS = ROOT / 'build/manual-deps'
CP = os.pathsep.join(str(x) for x in DEPS.glob('*.jar'))
def run(command, name, good=True):
    result = subprocess.run([str(x) for x in command], cwd=ROOT, text=True, capture_output=True)
    (BUILD / (name + '.log')).write_text(result.stdout + result.stderr)
    if (result.returncode == 0) != good:
        raise AssertionError(name + '结果不符合预期：\n' + result.stdout + result.stderr)
    return result
support = BUILD / 'support'; support.mkdir(exist_ok=True)
run([JDK/'bin/javac','--release','21','-encoding','UTF-8','-cp',CP,'-d',support,*sorted((ROOT/'support/src').rglob('*.java'))], 'support-compile')
CP += os.pathsep + str(support)
mutations = {
    'kafka-01-contract': ('event.order(), event.encode()', 'event.id(), event.encode()'),
    'kafka-02-producer': ('ProducerConfig.ACKS_CONFIG, "all"', 'ProducerConfig.ACKS_CONFIG, "1"'),
    'kafka-03-inbox': ('record.offset() + 1', 'record.offset()'),
    'kafka-04-rebalance': ('partitions.forEach(completed::remove);', '/* 错误变体：撤销后没有清理旧位点 */'),
    'kafka-05-transactions': ('if (abort) producer.abortTransaction();', 'if (!abort) producer.abortTransaction();'),
    'kafka-06-recovery': ('SET sent=TRUE', 'SET sent=FALSE'),
    'rocketmq-01-routing': ('return producer.send(RocketClient.message(topic, event));', 'return null;'),
    'rocketmq-02-retry': ('attempt >= maxAttempts', 'attempt > maxAttempts'),
    'rocketmq-03-order-delay': ('setMessageGroup(event.order())', 'setMessageGroup(event.id())'),
    'rocketmq-04-transactions': ('c.commit();', 'c.rollback();'),
    'rocketmq-05-storage': ('!actual.contains(id)', 'actual.contains(id)'),
    'rocketmq-06-comparison': ('if (!seen.add(event.id())) return false;', 'seen.add(event.id());'),
}
report = []
for item in json.loads((ROOT/'authoring/manifest.json').read_text()):
    task = ROOT / item['task']; name = item['module']; out = BUILD / name; out.mkdir(exist_ok=True)
    sources = sorted((task/'src').rglob('*.java')) + sorted((task/'test').rglob('*.java'))
    run([JDK/'bin/javac','--release','21','-encoding','UTF-8','-cp',CP,'-d',out,*sources],name+'-compile')
    command = [JDK/'bin/java','-cp',CP+os.pathsep+str(out),'org.junit.platform.console.ConsoleLauncher','execute','--select-class','LabTest','--disable-banner','--details=summary']
    result = run(command,name+'-unit')
    # 所有起点都实际编译并执行公开单元用例，确保空实现不能靠读取非学习区代码通过。
    lab = task/'src/labs/messaging/Lab.java'; content = lab.read_text()
    begin = content.index('        // 学习区开始\n') + len('        // 学习区开始\n'); end = content.index('        // 学习区结束')
    student = content[:begin]+'        throw new UnsupportedOperationException("TODO：请实现本方法");\n'+content[end:]
    temp = BUILD/'learner-src'/name/'labs/messaging/Lab.java'; temp.parent.mkdir(parents=True,exist_ok=True); temp.write_text(student)
    run([JDK/'bin/javac','--release','21','-encoding','UTF-8','-cp',CP+os.pathsep+str(out),'-d',out,temp],name+'-learner-compile')
    run(command,name+'-learner-rejected',False)
    run([JDK/'bin/javac','--release','21','-encoding','UTF-8','-cp',CP+os.pathsep+str(out),'-d',out,lab],name+'-restore')
    wrong, replacement = mutations[name]
    assert wrong in content, name + '错误变体目标未找到'
    temp.write_text(content.replace(wrong, replacement, 1))
    run([JDK/'bin/javac','--release','21','-encoding','UTF-8','-cp',CP+os.pathsep+str(out),'-d',out,temp],name+'-mutation-compile')
    run(command,name+'-mutation-rejected',False)
    run([JDK/'bin/javac','--release','21','-encoding','UTF-8','-cp',CP+os.pathsep+str(out),'-d',out,lab],name+'-final-restore')
    run(command,name+'-final-unit')
    report.append({'课程':name,'作者严格编译':True,'无容器单测':True,'学生起点可编译':True,'空实现被拒绝':True,'固定错误变体被拒绝':True,'Docker动态':'未运行'})
    print('通过：',name,'作者单测、空实现与错误变体负例',flush=True)
(BUILD/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
print('严格验证完成：',len(report),'节；真实Docker仍未运行')
