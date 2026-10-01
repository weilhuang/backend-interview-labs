#!/usr/bin/env python3
"""核对固定Spring标签与官方源码路径，保存摘要而不是复制上游实现。"""
from pathlib import Path
import urllib.request,json,re,hashlib,concurrent.futures,os
os.environ['NO_PROXY']='';os.environ['no_proxy']=''
ROOT=Path(__file__).resolve().parents[1]
def read(url):return urllib.request.urlopen(url,timeout=60).read()
refs={}
for repository,tag in [('spring-framework','v6.2.19'),('spring-boot','v3.5.16'),('spring-security','6.5.11')]:
 try:
  data=json.loads(read(f'https://api.github.com/repos/spring-projects/{repository}/git/ref/tags/{tag}'));obj=data['object']
  if obj['type']=='tag':obj=json.loads(read(obj['url']))['object']
  refs[repository]={'tag':tag,'commit':obj['sha'],'verified':True}
 except Exception as e:refs[repository]={'tag':tag,'verified':False,'error':str(e)}
urls=set()
for p in (ROOT/'framework-course').rglob('task.md'):
 urls.update(re.findall(r'https://github.com/spring-projects/[^)\s]+\.java',p.read_text()))
def verify(url):
 raw=url.replace('https://github.com/','https://raw.githubusercontent.com/').replace('/blob/','/')
 try:
  data=read(raw);return {'url':url,'verified':True,'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest()}
 except Exception as e:return {'url':url,'verified':False,'error':str(e)}
with concurrent.futures.ThreadPoolExecutor(max_workers=8) as ex:files=list(ex.map(verify,sorted(urls)))
report={'references':refs,'files':files,'all_paths_verified':all(x['verified'] for x in files),'source_debugging':'源码链接核验不等于IDE断点验收'}
(ROOT/'authoring/source-verification.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
print('固定源码路径：',sum(x['verified'] for x in files),'/',len(files),'；标签：',refs)
