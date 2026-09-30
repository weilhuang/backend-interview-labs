#!/usr/bin/env python3
"""只采集本脚本创建的有界JVM，不接受外部PID，不执行堆转储。"""
from pathlib import Path
import argparse,json,os,select,shutil,subprocess,time,sys
ROOT=Path(__file__).resolve().parents[1]
p=argparse.ArgumentParser();p.add_argument('--java-home',type=Path,default=Path(os.environ.get('JAVA_HOME','/workspace/shared/toolchains/jdk-21')));a=p.parse_args()
java=a.java_home/'bin/java';javac=a.java_home/'bin/javac';jcmd=a.java_home/'bin/jcmd';jfr=a.java_home/'bin/jfr'
for tool in [java,javac,jcmd,jfr]:
 if not tool.is_file():raise SystemExit('BLOCKED：完整JDK缺少'+str(tool))
work=ROOT/'build/diagnostics'/time.strftime('%Y%m%d-%H%M%S');work.mkdir(parents=True);classes=work/'classes';classes.mkdir()
version=subprocess.check_output([str(java),'-version'],stderr=subprocess.STDOUT,text=True)
subprocess.run([str(javac),'--release','21','-encoding','UTF-8','-d',str(classes),str(ROOT/'juc/08-virtual-threads/lab/src/labs/VirtualGateway.java'),str(ROOT/'scripts/ConcurrencyDiagnostics.java')],check=True,timeout=20)
process=subprocess.Popen([str(java),'-XX:+StartAttachListener','-Xms32m','-Xmx96m','-cp',str(classes),'ConcurrencyDiagnostics',str(work/'recording.jfr')],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True)
report={'status':'NOT_RUN','java':version.strip(),'pid':process.pid,'scope':'仅脚本创建的合成实验子进程','limits':{'heapMiB':96,'requests':8,'downstreamConcurrency':2,'workloadWaitSeconds':15,'jfrMaxMiB':8},'commands':[],'interpretation':'NOT_REVIEWED；命令通过不代表诊断解释通过'}
try:
 readable,_,_=select.select([process.stdout],[],[],7)
 if not readable:raise RuntimeError('INVALID_ENV：子进程没有及时准备就绪')
 ready=process.stdout.readline();assert ready.startswith('READY pid='),ready
 (work/'ready.txt').write_text(ready)
 for arguments,name in [(['Thread.print','-l'],'platform-threads.txt'),(['Thread.dump_to_file','-format=json',str(work/'all-threads.json')],'thread-dump-command.txt')]:
  try:
   result=subprocess.run([str(jcmd),str(process.pid)]+arguments,text=True,capture_output=True,timeout=4)
   (work/name).write_text(result.stdout+result.stderr);report['commands'].append({'command':arguments,'exitCode':result.returncode})
  except subprocess.TimeoutExpired as error:
   (work/name).write_text('BLOCKED：jcmd超时；保留其他可采集证据\n');report['commands'].append({'command':arguments,'status':'BLOCKED','error':'有界等待超时'})
 output,_=process.communicate(input='\n',timeout=6);(work/'process.log').write_text(ready+output)
 assert process.returncode==0 and '业务合计=28' in output,output
 result=subprocess.run([str(jfr),'summary',str(work/'recording.jfr')],text=True,capture_output=True,timeout=5);(work/'jfr-summary.txt').write_text(result.stdout+result.stderr);assert result.returncode==0
 events=subprocess.run([str(jfr),'print','--events','jdk.ThreadPark,jdk.VirtualThreadStart,jdk.VirtualThreadEnd,jdk.VirtualThreadPinned',str(work/'recording.jfr')],text=True,capture_output=True,timeout=5);(work/'jfr-events.txt').write_text(events.stdout+events.stderr);assert events.returncode==0
 assert (work/'recording.jfr').stat().st_size<12*1024*1024
 report['jfr']='PASS';report['business_result']='PASS';report['status']='PASS' if all(command.get('exitCode')==0 for command in report['commands']) else 'PARTIAL_BLOCKED';report['meaning']='业务与JFR已执行；线程转储按各自命令状态记录；人工解释仍需评阅'
except Exception as error:
 report['status']='BLOCKED';report['error']=str(error);raise
finally:
 if process.poll() is None:
  process.terminate()
  try:process.communicate(timeout=3)
  except subprocess.TimeoutExpired:process.kill();process.communicate(timeout=3)
 report['childExitCode']=process.returncode;(work/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n');print(work)

if report['status'] != 'PASS':
 raise SystemExit('PARTIAL_BLOCKED：存在未成功的采集命令，请查看report.json；已完成的JFR与业务结果仍保留')
