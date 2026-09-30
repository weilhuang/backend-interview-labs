#!/usr/bin/env python3
"""使用已提供的官方格式器；不下载。同步变异替换片段以保留可复现负例。"""
from pathlib import Path
import argparse,subprocess,json,hashlib,os
R=Path(__file__).resolve().parents[1]
p=argparse.ArgumentParser();p.add_argument('--formatter',type=Path,required=True);args=p.parse_args()
assert hashlib.sha256(args.formatter.read_bytes()).hexdigest()=='812f805f58112460edf01bf202a8e61d0fd1f35c0d4fabd54220640776ec57a1'
m=json.loads((R/'authoring/manifest.json').read_text());temp=R/'build/formatted-mutants';temp.mkdir(parents=True,exist_ok=True)
for item in m:
 source=(R/item['task']/item['source']).read_text()
 for i,(old,new) in enumerate(item['mutations']):
  assert source.count(old)==1,(item['id'],old)
  (temp/f'{item["class"]}-{i}.java').write_text(source.replace(old,new))
files=[]
for root in ['c00','c01','common','diagnostics','benchmark','authoring/alternatives']:
 files += [f for f in (R/root).rglob('*.java') if 'build' not in f.relative_to(R).parts]
files += list(temp.glob('*.java'))
java=str(Path(os.environ['JAVA_HOME'])/'bin/java') if os.environ.get('JAVA_HOME') else 'java'
subprocess.run([java,'-jar',str(args.formatter.resolve()),'--aosp','--replace']+list(map(str,files)),check=True)
for item in m:
 source=(R/item['task']/item['source']).read_text();mutations=[]
 for i in range(len(item['mutations'])):
  variant=(temp/f'{item["class"]}-{i}.java').read_text();a=0
  while source[a]==variant[a]:a+=1
  tail=0
  while source[-tail-1]==variant[-tail-1]:tail+=1
  start=max(0,a-40);end=min(len(source),len(source)-tail+40);vend=min(len(variant),len(variant)-tail+40)
  while source.count(source[start:end])!=1:start=max(0,start-40);end=min(len(source),end+40);vend=min(len(variant),vend+40)
  old=source[start:end];new=variant[start:vend];assert source.replace(old,new)==variant;mutations.append([old,new])
 item['mutations']=mutations
(R/'authoring/manifest.json').write_text(json.dumps(m,ensure_ascii=False,indent=2)+'\n')
