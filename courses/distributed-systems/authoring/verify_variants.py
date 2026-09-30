#!/usr/bin/env python3
"""真实javac+JUnit验证：每节空实现、典型错误及另一种等价正确实现。"""
from pathlib import Path
import json,re,subprocess,os,argparse,yaml
R=Path(__file__).resolve().parents[1]
parser=argparse.ArgumentParser();parser.add_argument('--jdk',default=os.environ.get('JAVA_HOME','/workspace/shared/toolchains/jdk-21'));parser.add_argument('--module',choices=list({t['name'] for t in json.loads((R/'authoring/manifest.json').read_text())}));args=parser.parse_args()
J=Path(args.jdk)/'bin';tasks=json.loads((R/'authoring/manifest.json').read_text())
CASES={
'01-failure-model':('src/labs/distributed/Lab.java','state = Knowledge.UNKNOWN;','state = Knowledge.NOT_SENT;','return available.compareTo(cap) < 0 ? available : cap;','return java.util.stream.Stream.of(available, cap).min(Duration::compareTo).orElseThrow();',['labs.distributed.LabTest']),
'02-grpc':('src/labs/distributed/grpc/Lab.java','request.getQuantity() < 1','request.getQuantity() < 0','request.getQuantity() < 1','request.getQuantity() <= 0',['labs.distributed.GrpcTest']),
'03-dubbo':('src/labs/distributed/dubbo/BudgetFilter.java','trace == null || !trace.matches("[a-zA-Z0-9_-]{1,64}")','trace == null','trace.matches("[a-zA-Z0-9_-]{1,64}")','java.util.regex.Pattern.matches("[a-zA-Z0-9_-]{1,64}", trace)',['labs.distributed.DubboTest']),
'04-resilience':('src/labs/distributed/Lab.java','tokens -= 1.0;','tokens -= 0.0;','tokens = Math.min(capacity, tokens + elapsed * perNano);','tokens += elapsed * perNano; if (tokens > capacity) tokens = capacity;',['labs.distributed.LabTest']),
'05-idempotency':('src/labs/distributed/idempotency/IdempotencyStore.java','available=available-?','available=available+?','available>=?','available-?>=0',['labs.distributed.IdempotencyTest','labs.distributed.RetryTest']),
'06-transactions':('src/labs/distributed/transactions/TccInventory.java','available=available+?','available=available-?','sold=sold+?','sold=?+sold',['labs.distributed.TransactionTest']),
'07-outbox-cache':('src/labs/distributed/outbox/Projector.java','WHERE sku=? AND revision<?','WHERE sku=? AND revision>?','WHERE sku=? AND revision<?','WHERE sku=? AND ? > revision',['labs.distributed.ProjectionTest']),
'08-capacity':('src/labs/distributed/capacity/Admission.java','if (!permits.tryAcquire())','if (false)','return Math.max(1, (int) Math.ceil(demand));','int whole = (int) demand; return Math.max(1, whole < demand ? whole + 1 : whole);',['labs.distributed.CapacityTest'])
}
RUNNER='''
import org.junit.platform.launcher.core.*;
import org.junit.platform.launcher.listeners.SummaryGeneratingListener;
import static org.junit.platform.engine.discovery.DiscoverySelectors.selectClass;
public class VariantRunner {
 public static void main(String[] args) {
  var builder = LauncherDiscoveryRequestBuilder.request();
  for (String name : args) builder.selectors(selectClass(name));
  var listener = new SummaryGeneratingListener();
  LauncherFactory.create().execute(builder.build(), listener);
  listener.getSummary().printTo(new java.io.PrintWriter(System.out, true));
  listener.getSummary().printFailuresTo(new java.io.PrintWriter(System.out, true));
  System.exit(listener.getSummary().getTestsFoundCount() == 0 ? 2 : listener.getSummary().getTestsFailedCount() > 0 ? 1 : 0);
 }
}
'''
def replace(source,old,new):
 positions=[i for i,c in enumerate(source) if not c.isspace()];compact=''.join(source[i] for i in positions);needle=''.join(old.split())
 if compact.count(needle)!=1:raise AssertionError(('替换片段必须唯一',old,compact.count(needle)))
 index=compact.index(needle);return source[:positions[index]]+new+source[positions[index+len(needle)-1]+1:]
def run(command,log,timeout=90):
 try:
  result=subprocess.run(command,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=timeout)
  log.write_bytes(result.stdout);return result.returncode
 except subprocess.TimeoutExpired as failure:
  log.write_bytes((failure.stdout or b'')+'\n验证进程超时，需查线程/取消问题'.encode());return 124
results=[]
for task in tasks:
 if args.module and task['name'] != args.module:continue
 root=R/task['path'];classpath=os.pathsep.join(part for part in (root/'build/test-classpath.txt').read_text().split(os.pathsep) if Path(part).exists());entry=CASES[task['name']]
 for mode in ['学生起点','典型错误','等价正确']:
  dest=R/'build/variants'/task['name']/mode;classes=dest/'classes';classes.mkdir(parents=True,exist_ok=True)
  files=[]
  meta={f['name']:f for f in yaml.safe_load((root/'task-info.yaml').read_text())['files']}
  for folder in ['src','test']:
   for source in (root/folder).rglob('*.java'):
    if '/grpc/protocol/' in str(source):continue
    relative=str(source.relative_to(root));content=source.read_text()
    if mode=='学生起点' and meta.get(relative,{}).get('placeholders'):
     data=content.encode('utf-16-le')
     for holder in sorted(meta[relative]['placeholders'],key=lambda h:h['offset'],reverse=True):
      start=holder['offset']*2;end=start+holder['length']*2
      data=data[:start]+holder['placeholder_text'].encode('utf-16-le')+data[end:]
     content=data.decode('utf-16-le')
    if relative==entry[0] and mode!='学生起点':content=replace(content,entry[1 if mode=='典型错误' else 3],entry[2 if mode=='典型错误' else 4])
    target=dest/relative;target.parent.mkdir(parents=True,exist_ok=True);target.write_text(content);files.append(str(target))
  runner=dest/'VariantRunner.java';runner.write_text(RUNNER);files.append(str(runner))
  compiled=run([str(J/'javac'),'--release','21','-encoding','UTF-8','-Xlint:all,-serial,-try','-Werror','-cp',classpath,'-d',str(classes)]+files,dest/'compile.log')
  executed=None
  if compiled==0:
   executed=run([str(J/'java'),'-Xmx512m','-Dio.netty.eventLoopThreads=2','-Dzookeeper.nio.numWorkerThreads=2','-Dzookeeper.nio.numSelectorThreads=1','-cp',str(classes)+os.pathsep+classpath,'VariantRunner']+entry[5],dest/'tests.log')
  expected=0 if mode=='等价正确' else 1
  passed=compiled==0 and executed==expected
  row={'unit':task['unit'],'mode':mode,'compile_exit':compiled,'test_exit':executed,'passed':passed}
  results.append(row);print(json.dumps(row,ensure_ascii=False),flush=True)
if args.module:
 prior=json.loads((R/'authoring/variants-report.json').read_text())
 changed={row['unit'] for row in results}
 results=[row for row in prior if row['unit'] not in changed]+results
 results.sort(key=lambda row:(row['unit'],row['mode']))
(R/'authoring/variants-report.json').write_text(json.dumps(results,ensure_ascii=False,indent=2)+'\n')
if not all(x['passed'] for x in results):raise SystemExit('负例/替代实现存在未通过项，查看build/variants日志')
