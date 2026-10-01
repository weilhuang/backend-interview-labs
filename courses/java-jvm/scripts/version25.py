#!/usr/bin/env python3
"""已有JDK25时自选的资料附录验证；无工具就NOT_RUN，不影响V1毕业，也不下载/安装JDK。"""
from pathlib import Path
import os,subprocess,json,re,sys
R=Path(__file__).resolve().parents[1];out=R/'build/java25';out.mkdir(parents=True,exist_ok=True)
def finish(data,code):
 (out/'report.json').write_text(json.dumps(data,ensure_ascii=False,indent=2));print(json.dumps(data,ensure_ascii=False,indent=2));sys.exit(code)
home=os.environ.get('JAVA25_HOME')
if not home:finish({'status':'NOT_RUN','reason':'没有现成JAVA25_HOME：自选资料附录NOT_RUN，不影响JDK21主线毕业；不要求安装/下载JDK'},3)
java=str(Path(home)/'bin/java');javac=str(Path(home)/'bin/javac')
if not Path(java).is_file() or not Path(javac).is_file():finish({'status':'INVALID_ENV','reason':'JAVA25_HOME必须包含完整JDK25'},2)
v=subprocess.run([java,'-version'],capture_output=True,text=True,timeout=10)
if not re.search(r'version "25[.\"]',v.stderr):finish({'status':'INVALID_ENV','reason':'必须使用JDK25，而非当前任意最新版','java':v.stderr},2)
results=[]
for category,flags,runtime in [('final',[],[]),('preview',['--enable-preview'],['--enable-preview']),('incubator',['--add-modules','jdk.incubator.vector'],['--add-modules','jdk.incubator.vector'])]:
 for source in (R/'experiments/java25'/category).glob('*.java'):
  target=out/source.stem;target.mkdir(exist_ok=True)
  cmd=[javac,'--release','25','-encoding','UTF-8']+flags+['-d',str(target),str(source)]
  compile=subprocess.run(cmd,capture_output=True,text=True,timeout=20);(target/'compile.log').write_text(compile.stdout+compile.stderr)
  if compile.returncode:finish({'status':'FAIL','stage':'compile','file':str(source.relative_to(R)),'command':cmd,'results':results},1)
  execute=subprocess.run([java,'-Xmx64m']+runtime+['-cp',str(target),source.stem],capture_output=True,text=True,timeout=10);(target/'run.log').write_text(execute.stdout+execute.stderr)
  if execute.returncode:finish({'status':'FAIL','stage':'run','file':source.name,'results':results},1)
  negative=None
  if category in ['preview','incubator']:
   denied=subprocess.run([javac,'--release','25','-d',str(target/'negative'),str(source)],capture_output=True,text=True,timeout=20)
   (target/'without-required-flag.log').write_text(denied.stdout+denied.stderr)
   if denied.returncode==0:finish({'status':'FAIL','reason':'缺少必要开关的反例意外编译成功','file':source.name},1)
   negative='EXPECTED_FAIL'
  results.append({'file':source.name,'category':category,'command':cmd,'status':'PASS','without_flag':negative,'stdout':execute.stdout})
finish({'status':'PASS','java':v.stderr,'scope':'仅这五个隔离示例；结构化并发与32位平台移除为阅读观察项','results':results},0)
