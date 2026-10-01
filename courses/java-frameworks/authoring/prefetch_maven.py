#!/usr/bin/env python3
"""并行预取官方Maven已声明的具体依赖，只加速本地验证，不改写任何元数据。"""
from pathlib import Path
import urllib.request,xml.etree.ElementTree as E,concurrent.futures,re,os
R=Path(__file__).resolve().parents[1]/'build/maven-cache';NS={'m':'http://maven.apache.org/POM/4.0.0'}
seen=set()
def get(item):
 g,a,v,ext=item;rel=f'{g.replace(".","/")}/{a}/{v}/{a}-{v}.{ext}';dest=R/rel
 if dest.exists():return
 try:
  data=urllib.request.urlopen('https://repo.maven.apache.org/maven2/'+rel,timeout=45).read();dest.parent.mkdir(parents=True,exist_ok=True);tmp=dest.with_name(dest.name+'.prefetch-'+str(os.getpid()));tmp.write_bytes(data);tmp.replace(dest)
 except Exception:pass
seeds=[('org.springframework.boot',a,'3.5.16') for a in ['spring-boot-starter-test','spring-boot-starter-security']]+[('com.h2database','h2','2.3.232')]
for turn in range(5):
 items=set()
 for g,a,v in seeds:
  for ext in ['pom','module','jar']:items.add((g,a,v,ext))
 for p in list(R.rglob('*.pom')):
  try:
   root=E.fromstring(p.read_bytes());props={x.tag.split('}')[1]:x.text for x in root.find('m:properties',NS) or []}
   def val(text):
    if not text:return ''
    for k,v in props.items():text=text.replace('${'+k+'}',v or '')
    return text
   for dep in root.findall('m:dependencies/m:dependency',NS):
    g=dep.findtext('m:groupId','',NS);a=dep.findtext('m:artifactId','',NS);v=val(dep.findtext('m:version','',NS));scope=dep.findtext('m:scope','compile',NS);typ=dep.findtext('m:type','jar',NS)
    if scope in ['test','provided'] or not v or '$' in v or v.startswith('['):continue
    for ext in (['pom'] if typ=='pom' else ['pom','module','jar']):items.add((g,a,v,ext))
  except Exception:pass
 items-=seen;seen|=items
 if not items:break
 print('预取轮次',turn+1,'文件数',len(items),flush=True)
 with concurrent.futures.ThreadPoolExecutor(max_workers=16) as ex:list(ex.map(get,items))
print('预取结束',flush=True)
