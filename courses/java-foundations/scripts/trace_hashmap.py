#!/usr/bin/env python3
"""只启动课程自己的JDI子进程；网络/调试器受限时留下BLOCKED而非伪造证据。"""
from pathlib import Path
import os,subprocess,json,hashlib,platform,time,sys,signal
R=Path(__file__).resolve().parents[1];out=R/'build/hashmap-trace'/('run-'+str(time.time_ns()));out.mkdir(parents=True,exist_ok=True)
if sys.platform!='linux':
 data={'status':'INVALID_ENV','reason':'自动JDI脚本仅验证Linux；其他系统请按题面使用IDE断点，不启动额外进程'}
 (out/'report.json').write_text(json.dumps(data,ensure_ascii=False,indent=2));print(json.dumps(data,ensure_ascii=False));sys.exit(2)
home=os.environ.get('JAVA_HOME');binary=Path(home)/'bin' if home else None
java=str(binary/'java') if binary else 'java';javac=str(binary/'javac') if binary else 'javac'
files=list((R/'diagnostics/src').rglob('*.java'))+[R/'c01/05-real-hash-map/lab/src/labs/foundation/HashMapRoutes.java']
metadata={'status':'NOT_RUN','platform':platform.platform(),'utc':time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()),'reading_reference':'OpenJDK21 GA 890adb6410dab4606a4f26a942aed02fb2f55387','boundary':'动态执行是当前补丁JDK，不冒充GA二进制'}
try:
 metadata['runtime']=subprocess.run([java,'-version'],capture_output=True,text=True,timeout=10).stderr
 classes=out/'classes';classes.mkdir(exist_ok=True)
 c=subprocess.run([javac,'--release','21','--add-modules','jdk.jdi','-g','-encoding','UTF-8','-d',str(classes)]+list(map(str,files)),capture_output=True,text=True,timeout=20);(out/'compile.log').write_text(c.stdout+c.stderr)
 if c.returncode:raise RuntimeError('调试辅助程序编译失败')
 process=subprocess.Popen([java,'-Xmx128m','--add-modules','jdk.jdi','-cp',str(classes),'labs.foundation.TraceHashMap',str(classes)],stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,start_new_session=True)
 try:
  stdout,stderr=process.communicate(timeout=25)
 except subprocess.TimeoutExpired:
  os.killpg(process.pid,signal.SIGKILL);process.communicate();raise
 run=subprocess.CompletedProcess(process.args,process.returncode,stdout,stderr)
 (out/'trace.log').write_text(run.stdout+run.stderr)
 if run.returncode:raise RuntimeError('JDI启动/执行失败，见trace.log')
 for method in ['treeifyBin','getTreeNode','split','treeify','untreeify']:
  if method not in run.stdout:raise RuntimeError('未观测到所要求入口：'+method)
 metadata['status']='OBSERVED';metadata['methods']=['treeifyBin','resize','treeify','getTreeNode','find','split','untreeify']
 if home and (Path(home)/'lib/src.zip').exists():metadata['runtime_src_zip_sha256']=hashlib.sha256((Path(home)/'lib/src.zip').read_bytes()).hexdigest()
except (OSError,RuntimeError,subprocess.TimeoutExpired) as error:metadata['status']='BLOCKED';metadata['reason']=str(error)
(out/'report.json').write_text(json.dumps(metadata,ensure_ascii=False,indent=2));print(json.dumps(metadata,ensure_ascii=False,indent=2));sys.exit(0 if metadata['status']=='OBSERVED' else 2)
