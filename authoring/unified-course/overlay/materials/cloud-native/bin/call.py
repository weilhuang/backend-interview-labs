#!/usr/bin/env python3
"""已提供的命令行调用方：不依赖curl/jq，仅接受本机实验URL。"""
import argparse,json,pathlib,sys,urllib.parse
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]/'tests'))
from contract import request
p=argparse.ArgumentParser();p.add_argument('path');p.add_argument('--method',choices=['GET','POST'],default='GET');p.add_argument('--port',type=int,default=18085);a=p.parse_args()
if not a.path.startswith('/') or a.path.startswith('//'):p.error('path must be a local API path')
status,body=request('http://127.0.0.1:'+str(a.port),a.path,a.method)
print('HTTP',status);print(json.dumps(body,ensure_ascii=False,indent=2))
sys.exit(0 if status<400 else 1)
