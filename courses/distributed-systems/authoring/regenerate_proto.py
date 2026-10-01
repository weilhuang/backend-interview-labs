#!/usr/bin/env python3
"""使用校验哈希的固定官方生成器重建proto代码；普通学习不需要重新生成。"""
from pathlib import Path
import json,hashlib,urllib.request,platform,subprocess,tempfile,sys,os,shutil
R=Path(__file__).resolve().parents[1]
if platform.system()!='Linux' or platform.machine() not in ['x86_64','AMD64']:
 raise SystemExit('该固定生成流程在Linux x86_64验证；其他平台直接使用公开生成代码，勿改用未锁版本生成器')
lock=json.loads((R/'authoring/tools-lock.json').read_text());tools=R/'build/tools';tools.mkdir(parents=True,exist_ok=True)
for item in lock['tools']:
 file=tools/item['filename']
 if not file.exists():
  file.write_bytes(urllib.request.urlopen(item['url'],timeout=60).read())
 if hashlib.sha256(file.read_bytes()).hexdigest()!=item['sha256']:raise SystemExit('生成器哈希不符：'+item['filename'])
 file.chmod(0o755)
base=R/'distributed-course/services/02-grpc'
with tempfile.TemporaryDirectory(prefix='proto-check-',dir=R/'build') as temp:
 out=Path(temp)
 subprocess.run([str(tools/'protoc-4.29.0'),'--proto_path='+str(base/'proto'),'--java_out='+str(out),
  '--plugin=protoc-gen-grpc-java='+str(tools/'protoc-gen-grpc-java'),'--grpc-java_out='+str(out),str(base/'proto/inventory.proto')],check=True)
 generated=list(out.rglob('*.java'))
 if '--check' in sys.argv:
  assert all((base/'src'/p.relative_to(out)).read_bytes()==p.read_bytes() for p in generated),'公开生成代码与固定工具输出不同'
  print('固定proto生成比对通过，文件数：',len(generated))
 else:
  for p in generated:
   target=base/'src'/p.relative_to(out);target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(p,target)
  print('已重新生成协议文件，请运行全课回归并更新课程元数据')
