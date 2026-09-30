#!/usr/bin/env python3
"""严格JDK21校验公开参考、另一正确写法、可编译起点和错误变体；不冒充容器测试。"""
from pathlib import Path
import argparse,json,os,re,subprocess
import yaml
ROOT=Path(__file__).resolve().parents[1]
p=argparse.ArgumentParser();p.add_argument('--jdk',default=os.environ.get('JAVA_HOME'));p.add_argument('--console',required=True);a=p.parse_args()
jdk=Path(a.jdk);console=Path(a.console).resolve();build=ROOT/'build/variants';build.mkdir(parents=True,exist_ok=True)
mutations={
 '01-contract':('command.quantity() < 1','command.quantity() < 0'),
 '02-reliability':('append(c, Event.of(result));','/* 错解：漏写outbox */'),
 '03-delivery':('        send.run();','        mark.run();\n        send.run();'),
 '04-recovery':('pending >= limit','pending > limit'),
 '05-defense':('if (order.status().equals("RESERVED"))','if (true)')}
alternates={
 '01-contract':('command.quantity() < 1 || command.quantity() > 100','!(command.quantity() >= 1 && command.quantity() <= 100)'),
 '02-reliability':('available>=?','available-? >= 0'),
 '03-delivery':('        send.run();','        Checked transport = send;\n        transport.run();'),
 '04-recovery':('pending >= limit','pending > limit - 1'),
 '05-defense':('reserved.merge(order.sku(), (long) order.quantity(), Long::sum);','reserved.put(order.sku(), reserved.getOrDefault(order.sku(), 0L) + order.quantity());')}
classes={'01-contract':'ContractTest','02-reliability':'ReliabilityTest','03-delivery':'DeliveryTest','04-recovery':'RecoveryTest','05-defense':'AuditTest'}
def run(cmd,name,expected=True):
 r=subprocess.run(list(map(str,cmd)),cwd=ROOT,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,timeout=35)
 (build/(name+'.log')).write_text(r.stdout)
 if (r.returncode==0)!=expected:raise AssertionError(name+'与预期不符\n'+r.stdout)
 return r.stdout
report=[]
for item in json.loads((ROOT/'authoring/manifest.json').read_text()):
 stage=item['module'];task=ROOT/'capstone/stages'/stage;target=item['target'];src=task/f'src/labs/capstone/{target}.java';original=src.read_text()
 cp=(task/'build/test-classpath.txt').read_text();out=build/stage;out.mkdir(exist_ok=True);temp=out/'source'/src.name;temp.parent.mkdir(exist_ok=True);dest=out/'classes';dest.mkdir(exist_ok=True)
 meta=yaml.safe_load((task/'task-info.yaml').read_text());placeholders=next(f['placeholders'] for f in meta['files'] if f['name'].endswith('/'+target+'.java'))
 raw=original.encode('utf-16-le')
 for ph in reversed(placeholders):raw=raw[:ph['offset']*2]+ph['placeholder_text'].encode('utf-16-le')+raw[(ph['offset']+ph['length'])*2:]
 wrong,replacement=mutations[stage];assert wrong in original
 before,after=alternates[stage];assert before in original
 for kind,source,expected in [('reference',original,True),('alternate',original.replace(before,after,1),True),('learner',raw.decode('utf-16-le'),False),('mutation',original.replace(wrong,replacement,1),False)]:
  temp.write_text(source);run([jdk/'bin/javac','--release','21','-encoding','UTF-8','-cp',cp,'-d',dest,temp],stage+'-'+kind+'-compile')
  result=run([jdk/'bin/java','-cp',str(dest)+os.pathsep+cp+os.pathsep+str(console),'org.junit.platform.console.ConsoleLauncher','execute','--select-class','labs.capstone.'+classes[stage],'--disable-banner','--details=summary'],stage+'-'+kind,expected)
  if not expected and not re.search(r'[1-9][0-9]* tests failed',result):raise AssertionError('负例必须因测试断言失败，不是启动错误：'+stage+' '+kind)
 report.append({'阶段':stage,'严格release21':True,'参考解':True,'另一正确写法':True,'起点可编译且被测试拒绝':True,'错解可编译且被测试拒绝':True,'真实容器验证':'另行记录，不能由本脚本推断'})
 print(stage+'：参考/另一正确写法通过，起点/错误变体被拒绝',flush=True)
(ROOT/'authoring/variant-report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
