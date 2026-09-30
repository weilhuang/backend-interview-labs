#!/usr/bin/env python3
"""云端验证预取已固定依赖，只保存官方原始字节，不修改POM或证书校验。"""
from pathlib import Path
import urllib.request,xml.etree.ElementTree as E,concurrent.futures,re,os
os.environ['NO_PROXY']='';os.environ['no_proxy']=''
R=Path(__file__).resolve().parents[1]/'build/maven-cache'; NS={'m':'http://maven.apache.org/POM/4.0.0'}
seen=set()
seeds=[('org.apache.dubbo',a,'3.3.6') for a in ['dubbo','dubbo-registry-zookeeper','dubbo-remoting-zookeeper-curator5']]+[('org.apache.curator','curator-test','5.7.1')]+[('io.github.resilience4j',a,'2.3.0') for a in ['resilience4j-circuitbreaker','resilience4j-bulkhead','resilience4j-ratelimiter']]+[('redis.clients','jedis','5.2.0')]
def get(item):
 g,a,v,ext=item; rel=f'{g.replace(".","/")}/{a}/{v}/{a}-{v}.{ext}'; dest=R/rel
 if dest.exists():return True
 try:
  data=urllib.request.urlopen('https://repo.maven.apache.org/maven2/'+rel,timeout=20).read();dest.parent.mkdir(parents=True,exist_ok=True);tmp=dest.with_name(dest.name+'.tmp-'+str(os.getpid()));tmp.write_bytes(data);tmp.replace(dest);return True
 except Exception:return False
for turn in range(7):
 items={(g,a,v,ext) for g,a,v in seeds for ext in ['pom','jar']}
 for p in list(R.rglob('*.pom')):
  try:
   root=E.fromstring(p.read_bytes()); props={x.tag.split('}')[1]:x.text for x in root.find('m:properties',NS) or []}
   props['project.version']=root.findtext('m:version','',NS)
   def val(t):
    if not t:return ''
    for k,v in props.items():t=t.replace('${'+k+'}',v or '')
    return t
   deps=root.findall('m:dependencies/m:dependency',NS)+root.findall('m:parent',NS)
   for d in deps:
    g=val(d.findtext('m:groupId','',NS));a=val(d.findtext('m:artifactId','',NS));v=val(d.findtext('m:version','',NS));scope=d.findtext('m:scope','compile',NS);typ=d.findtext('m:type','jar',NS)
    if d.findtext('m:optional','false',NS)=='true' or scope in ['test','provided'] or not v or '$' in v or v.startswith('['):continue
    for ext in (['pom'] if typ=='pom' or d.tag.endswith('parent') else ['pom','jar']):items.add((g,a,v,ext))
  except Exception: pass
 items-=seen;seen|=items
 if not items:break
 print('预取轮次',turn+1,'文件数',len(items),flush=True)
 with concurrent.futures.ThreadPoolExecutor(max_workers=24) as ex: print('成功或已缓存',sum(ex.map(get,items)),flush=True)
