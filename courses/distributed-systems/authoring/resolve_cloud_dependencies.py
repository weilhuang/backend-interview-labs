#!/usr/bin/env python3
"""在受控云端以官方HTTPS预取缺失坐标，再用本地只读仓库严格构建；不关闭TLS。"""
import subprocess,os,re,urllib.request,concurrent.futures
from pathlib import Path
R=Path(__file__).resolve().parents[1];os.chdir(R)
os.environ['NO_PROXY']='';os.environ['no_proxy']=''
cache=R/'build/maven-cache'
env=dict(os.environ,JAVA_HOME='/workspace/shared/toolchains/jdk-21',GRADLE_USER_HOME='/workspace/shared/gradle-home-dist',GRADLE_OPTS='-Dorg.gradle.native=false -Dorg.gradle.vfs.watch=false',LAB_MAVEN_REPOSITORY=cache.as_uri())
command=['/workspace/shared/toolchains/gradle-8.10.2/bin/gradle','--no-daemon','testClasses','integrationTestClasses','verificationClasspath','--continue','--write-locks']
def get(rel):
 dest=cache/rel
 if dest.exists():return True
 try:
  raw=urllib.request.urlopen('https://repo.maven.apache.org/maven2/'+rel,timeout=25).read()
  dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes(raw);return True
 except Exception as e:return False
for turn in range(12):
 print('离线解析轮次',turn+1,flush=True)
 run=subprocess.run(command,env=env,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=240)
 log=run.stdout.decode();(R/'build-compile.log').write_text(log)
 if run.returncode==0:print('全模块编译和类路径导出通过',flush=True);break
 paths=set(re.findall(r'file:[^\s]*?/maven-cache/([^\s]+\.(?:pom|jar))',log))
 if not paths:
  print(log[-12000:],flush=True);raise SystemExit(run.returncode)
 print('下载缺失官方文件',len(paths),flush=True)
 with concurrent.futures.ThreadPoolExecutor(max_workers=16) as pool: print('成功',sum(pool.map(get,paths)),flush=True)
else:raise SystemExit('解析仍未完成，请检查最后具体缺失坐标')
