#!/usr/bin/env python3
"""浏览器同等HTTP调用方，只允许localhost转发端口。"""
import argparse,json,urllib.request,urllib.error
p=argparse.ArgumentParser();p.add_argument('operation',choices=['info','stock','seed','order']);p.add_argument('--request-id',default='demo-001');a=p.parse_args()
import re
if not re.fullmatch('[a-zA-Z0-9_-]{1,40}',a.request_id):p.error('request-id must be 1..40 safe characters')
path={'info':'/info','stock':'/stock','seed':'/seed','order':'/orders?request_id='+a.request_id+'&quantity=2'}[a.operation]
r=urllib.request.Request('http://127.0.0.1:18080'+path,method='POST' if a.operation in ('seed','order') else 'GET')
try:
    with urllib.request.urlopen(r,timeout=5) as response:print(response.status,response.read().decode())
except urllib.error.HTTPError as e:print(e.code,e.read().decode());raise SystemExit(1)
except urllib.error.URLError:print('{"status":"INVALID_ENV","reason":"LOCAL_PORT_FORWARD_UNAVAILABLE"}');raise SystemExit(2)
