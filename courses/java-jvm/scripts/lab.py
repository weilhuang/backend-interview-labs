#!/usr/bin/env python3
"""只对子进程做有界实验；不接受外部PID，不读取真实业务目录。"""
from pathlib import Path
import argparse,subprocess,os,shutil,time,json,sys,re,math,threading
R=Path(__file__).resolve().parents[1]
p=argparse.ArgumentParser();p.add_argument('action',choices=['doctor','compile','usage','bytecode','layout','gc','diagnose','modules','migration']);p.add_argument('--mode',choices=['cpu','lock','retention','pool'],default='cpu');p.add_argument('--heap',action='store_true',help='仅为本脚本retention子进程生成隔离堆快照，最多96MiB堆');a=p.parse_args()
H=os.environ.get('JAVA_HOME');B=Path(H)/'bin' if H else None

def tool(name):return str(B/name) if B else shutil.which(name)
def run(cmd,timeout=30):
 result=subprocess.run(cmd,text=True,capture_output=True,timeout=timeout)
 if result.returncode:raise RuntimeError('命令失败：'+str(cmd)+'\n'+result.stdout+result.stderr)
 return result.stdout+result.stderr
needed=['java','javac']+(['javap'] if a.action=='bytecode' else [])+(['jcmd','jfr'] if a.action=='diagnose' else [])
missing=[name for name in needed if not tool(name) or not Path(tool(name)).exists()]
if missing:print('INVALID_ENV：需要完整JDK21工具：'+','.join(missing));sys.exit(2)
version=run([tool('java'),'-version']);print(version.strip());
if not re.search(r'version "21[.\"]',version):print('INVALID_ENV：主线必须使用JDK21');sys.exit(2)
if a.action=='doctor':print('PASS：JDK21工具就绪；诊断需256MiB空闲磁盘，课程不需要Docker或前端');sys.exit(0)
classes=R/'build/labs/classes';classes.mkdir(parents=True,exist_ok=True)
files=sorted(str(f) for f in (R/'jvm').glob('*/lab/src/**/*.java'))
run([tool('javac'),'--release','21','-encoding','UTF-8','-d',str(classes)]+files)
base=[tool('java'),'-Xms32m','-Xmx96m','-XX:MaxDirectMemorySize=16m','-XX:ActiveProcessorCount=2','-cp',str(classes)]
if a.action=='compile':print('PASS：已编译全部主线调用端');sys.exit(0)
if a.action=='usage':
 for f in (R/'jvm').glob('*/lab/src/**/*Usage.java'):print(run(base+['labs.jvm.'+f.stem],15))
elif a.action=='bytecode':
 output=run([tool('javap'),'-c','-p','-v','-classpath',str(classes),'labs.jvm.LoaderLab']);(R/'build/labs/bytecode.txt').write_text(output);print(output)
 print(run(base+['labs.jvm.LoaderLabUsage']))
elif a.action=='layout':
 import zipfile
 evidence=R/'build/evidence'/('layout-'+str(time.time_ns()));evidence.mkdir(parents=True)
 agent=evidence/'size-agent.jar'
 with zipfile.ZipFile(agent,'w') as jar:
  jar.writestr('META-INF/MANIFEST.MF','Manifest-Version: 1.0\nPremain-Class: labs.jvm.SizeAgent\n\n')
  jar.write(classes/'labs/jvm/SizeAgent.class','labs/jvm/SizeAgent.class')
 observations=[]
 for label,options in [('default',[]),('uncompressed-oops',['-XX:-UseCompressedOops'])]:
  flags=run([tool('java'),'-Xmx96m']+options+['-XX:+PrintFlagsFinal','-version'])
  (evidence/(label+'-flags.txt')).write_text(flags)
  result=run(base[:1]+options+['-javaagent:'+str(agent)]+base[1:]+['labs.jvm.LayoutProbe'])
  (evidence/(label+'-sizes.txt')).write_text(result)
  observations.append({'configuration':label,'options':options,'result':result})
 (evidence/'report.json').write_text(json.dumps({'status':'OBSERVED','java':version,'observations':observations,'boundary':'Instrumentation实现相关近似浅大小；不推断深大小、字段偏移或逃逸优化'},ensure_ascii=False,indent=2));print('布局观察：',evidence)
elif a.action=='gc':
 evidence=R/'build/evidence'/('gc-'+str(time.time_ns()));evidence.mkdir(parents=True)
 reports=[];checksums=[]
 for collector in ['G1','Serial']:
  log=evidence/(collector+'.log');cmd=base[:1]+['-Xms32m','-Xmx32m','-XX:ActiveProcessorCount=2','-XX:+Use'+collector+'GC','-Xlog:gc*:file='+str(log)+':uptime,level,tags:filecount=1,filesize=4M','-cp',str(classes),'labs.jvm.AllocationWorkloadUsage']
  start=time.monotonic();output=run(cmd,30);elapsed=time.monotonic()-start;(evidence/(collector+'-stdout.txt')).write_text(output);checksums.append(output)
  pauses=[float(x) for x in re.findall(r'Pause[^\n]*? ([0-9.]+)ms\s*$',log.read_text(),re.M)]
  values=sorted(pauses);q=lambda p:values[max(0,math.ceil(len(values)*p)-1)] if values else None
  reports.append({'collector':collector,'command':cmd,'wall_seconds':elapsed,'pause_samples':len(values),'p50_ms':q(.5),'p95_ms':q(.95),'p99_ms':q(.99),'max_ms':max(values) if values else None,'observation_status':'OBSERVED' if values else 'INSUFFICIENT_SAMPLES','allocated_bytes_per_run':268435456,'allocation_bytes_per_wall_second':268435456/elapsed})
 assert checksums[0]==checksums[1],'不同收集器业务结果不一致'
 (evidence/'report.json').write_text(json.dumps({'java':version,'business':'PASS','observations':reports,'note':'单次冷启动微型实验；wall含启动；无请求延迟指标，不可推导生产优劣'},ensure_ascii=False,indent=2));print('业务结果相同，观察材料：',evidence)
elif a.action=='diagnose':
 if a.heap and a.mode!='retention':raise SystemExit('--heap只允许retention模式')
 evidence=R/'build/evidence'/('incident-'+a.mode+'-'+str(time.time_ns()));evidence.mkdir(parents=True)
 if shutil.disk_usage(evidence).free<256*1024*1024:raise SystemExit('INVALID_ENV：空闲磁盘不足256MiB')
 recording=evidence/'sample.jfr';cmd=base[:1]+['-XX:+StartAttachListener','-XX:StartFlightRecording=filename='+str(recording)+',maxsize=16m,dumponexit=true,settings=profile']+base[1:]+['labs.jvm.IncidentMain',a.mode]
 stdout=open(evidence/'stdout.txt','w');process=subprocess.Popen(cmd,stdout=stdout,stderr=subprocess.STDOUT,text=True);started=time.monotonic()
 # 看门狗是最终保护；进程正常退出时取消，不触及其他PID。
 timer=threading.Timer(24,lambda:process.kill() if process.poll() is None else None);timer.start()
 try:
  ready=False
  for _ in range(100):
   if 'READY' in (evidence/'stdout.txt').read_text():ready=True;break
   if process.poll() is not None:break
   time.sleep(.05)
  if not ready:raise RuntimeError('实验未进入就绪态')
  pid=str(process.pid)
  attach_errors=[]
  for label,command in [('vm-version','VM.version'),('vm-flags','VM.flags'),('threads','Thread.print -l'),('histogram','GC.class_histogram')]:
   try:(evidence/(label+'.txt')).write_text(run([tool('jcmd'),pid]+command.split(),5))
   except (RuntimeError,subprocess.TimeoutExpired) as error:
    attach_errors.append(str(error));(evidence/'jcmd-blocked.txt').write_text(str(error));break
  if a.heap and not attach_errors:
   try:(evidence/'heap-command.txt').write_text(run([tool('jcmd'),pid,'GC.heap_dump',str(evidence/'isolated.hprof')],8))
   except (RuntimeError,subprocess.TimeoutExpired) as error:attach_errors.append(str(error))
  process.wait(timeout=max(1,22-(time.monotonic()-started)))
  if process.returncode:raise RuntimeError('实验进程异常退出')
  (evidence/'jfr-summary.txt').write_text(run([tool('jfr'),'summary',str(recording)],10))
  (evidence/'jfr-events.txt').write_text(run([tool('jfr'),'print','--events','jdk.ExecutionSample,jdk.JavaMonitorEnter,jdk.ThreadPark','--stack-depth','12',str(recording)],10))
  (evidence/'manifest.json').write_text(json.dumps({'status':'PARTIAL_BLOCKED' if attach_errors else 'COLLECTED','jcmd_errors':attach_errors,'java':version,'command':cmd,'pid':process.pid,'mode':a.mode,'heap_dump_requested':a.heap,'review':'NOT_REVIEWED：证据存在不等于诊断结论成立','elapsed':time.monotonic()-started},ensure_ascii=False,indent=2));print('已收集隔离实验材料（jcmd部分受阻）' if attach_errors else '已收集隔离实验材料：',evidence)
 finally:
  if process.poll() is None:process.terminate()
  try:process.wait(timeout=2)
  except subprocess.TimeoutExpired:process.kill();process.wait(timeout=2)
  timer.cancel();stdout.close()
elif a.action=='modules':
 root=R/'experiments/modules';out=R/'build/modules';out.mkdir(parents=True,exist_ok=True)
 cmd=[tool('javac'),'--release','21','--module-source-path',str(root/'src'),'-d',str(out)]
 run(cmd+[str(f) for f in (root/'src').rglob('*.java')]);print(run([tool('java'),'--module-path',str(out),'-m','orders.app/orders.app.Main']))
 bad=subprocess.run([tool('javac'),'--release','21','--module-path',str(out),'--add-modules','orders.core','-d',str(out/'negative'),str(root/'negative/Forbidden.java')],capture_output=True,text=True,timeout=20)
 (R/'build/modules/negative.log').write_text(bad.stdout+bad.stderr);assert bad.returncode!=0 and 'not visible' in bad.stderr,'未导出包反例未命中预期诊断';print('PASS：公开API可用，未导出包在编译期被拒绝')
elif a.action=='migration':
 out=R/'build/migration';out.mkdir(parents=True,exist_ok=True)
 run([tool('javac'),'--release','8','-encoding','UTF-8','-d',str(out),str(R/'experiments/java8/LegacyReport.java')]);legacy=run([tool('java'),'-cp',str(out),'LegacyReport']).strip()
 modern=R/'jvm/05-migration/lab/src/labs/jvm';run([tool('javac'),'--release','17','-encoding','UTF-8','-d',str(out)]+[str(f) for f in modern.glob('*.java')]);current=run([tool('java'),'-cp',str(out),'labs.jvm.MigrationReportUsage'])
 assert '纽约营业日总额='+legacy in current;print('PASS：--release8与--release17编译，并在JDK21运行相同业务样例；不是实际JDK8/17运行验证')
