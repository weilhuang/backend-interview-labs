#!/usr/bin/env python3
"""仅供云端开发验证的只读Maven镜像桥；不替代课程的正常Maven Central配置。"""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import urllib.request, urllib.error, urllib.parse, threading, sys
CACHE=Path(__file__).resolve().parents[1]/'build/maven-cache'; CACHE.mkdir(parents=True,exist_ok=True)
LOCKS={}; GUARD=threading.Lock()
class Handler(BaseHTTPRequestHandler):
 def do_HEAD(self): self.serve(False)
 def do_GET(self): self.serve(True)
 def serve(self,body):
  relative=urllib.parse.urlsplit(self.path).path.lstrip('/')
  if '..' in relative.split('/') or not relative: self.send_error(400);return
  dest=CACHE/relative
  with GUARD: lock=LOCKS.setdefault(relative,threading.Lock())
  try:
   with lock:
    if not dest.exists():
     data=urllib.request.urlopen('https://repo.maven.apache.org/maven2/'+relative,timeout=60).read()
     dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes(data)
   data=dest.read_bytes();self.send_response(200);self.send_header('Content-Length',str(len(data)));self.end_headers()
   if body:self.wfile.write(data)
  except urllib.error.HTTPError as ex:self.send_error(ex.code)
  except Exception as ex:self.send_error(502,str(ex))
 def log_message(self,*args):pass
server=ThreadingHTTPServer(('127.0.0.1',int(sys.argv[1]) if len(sys.argv)>1 else 18763),Handler)
print('只读Maven验证桥已启动',server.server_address,flush=True);server.serve_forever()
