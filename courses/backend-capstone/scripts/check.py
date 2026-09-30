#!/usr/bin/env python3
"""真实HTTP幂等、取消、事件重放和读模型检查；只创建本次随机请求，不清空任何数据。"""
import json, os, time, urllib.request, urllib.error
base='http://127.0.0.1:'+os.environ.get('CAPSTONE_HTTP_PORT','8088')
def call(path, value=None):
 data=None if value is None else json.dumps(value).encode()
 request=urllib.request.Request(base+path,data=data,headers={'Content-Type':'application/json'},method='GET' if value is None else 'POST')
 with urllib.request.urlopen(request,timeout=40) as r:return json.load(r)
id='check-'+str(time.time_ns())
command={'requestId':id,'sku':'book','quantity':1}
print('检查依赖：',call('/api/health'))
try:
 first=call('/api/orders',command);second=call('/api/orders',command);assert first==second
 try:call('/api/orders',{**command,'quantity':2});raise AssertionError('冲突请求没有被拒绝')
 except urllib.error.HTTPError as e:assert e.code==409
finally:
 # 取消只针对本脚本生成的请求；即使客户端结果未知也尝试归还自己的库存。
 try:call('/api/orders/'+id+'/cancel',{})
 except urllib.error.HTTPError as e:
  if e.code!=409:raise
call('/api/replay',{})
dashboard=call('/api/dashboard')
assert next(o for o in dashboard['orders'] if o['requestId']==id)['status']=='CANCELLED'
assert next(d for d in dashboard['deliveries'] if d['requestId']==id)['status']=='CANCELLED'
assert not [f for f in dashboard['audit'] if f['severity']=='ERROR'],dashboard['audit']
print('真实HTTP幂等、冲突、取消和Kafka/gRPC投影通过；本次请求：',id)
