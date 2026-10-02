#!/usr/bin/env python3
"""Business requests bracketed by refused health connections, never an HTTP error mistaken for outage."""
import argparse,datetime,errno,hashlib,json,pathlib,re,socket,time,urllib.request,urllib.error,urllib.parse
def require(ok,message):
 if not ok:raise ValueError(message)
def local_url(url):
 u=urllib.parse.urlsplit(url)
 require(u.scheme=='http' and u.hostname in ('127.0.0.1','localhost') and u.username is None and u.password is None and not u.query and not u.fragment,'仅允许无凭证/query/fragment的回环HTTP地址')
 return url
def probe(url):
 try:
  with urllib.request.urlopen(url,timeout=1) as response:
   if hasattr(response,'geturl'):require(response.geturl()==url,'health目标发生重定向')
   return {'classification':'REACHABLE_HTTP','http_status':response.status}
 except urllib.error.HTTPError as e:return {'classification':'REACHABLE_HTTP','http_status':e.code}
 except urllib.error.URLError as e:
  reason=e.reason
  if isinstance(reason,ConnectionRefusedError) or isinstance(reason,OSError) and reason.errno==errno.ECONNREFUSED:return {'classification':'CONNECTION_REFUSED'}
  if isinstance(reason,(socket.timeout,TimeoutError)):return {'classification':'INCONCLUSIVE_TIMEOUT','reason':'超时不能证明Collector已停止'}
  return {'classification':'OTHER_CONNECTION_ERROR','reason':type(reason).__name__}
 except (socket.timeout,TimeoutError):return {'classification':'INCONCLUSIVE_TIMEOUT','reason':'超时不能证明Collector已停止'}
def main(argv=None):
 p=argparse.ArgumentParser();p.add_argument('--checkout',default='http://127.0.0.1:18081');p.add_argument('--collector-health',default='http://127.0.0.1:13133');p.add_argument('--output',required=True);p.add_argument('--isolation-record');a=p.parse_args(argv)
 result={'status':'BLOCKED','evidence_type':'BUSINESS_REQUESTS_BRACKETED_BY_REFUSED_HEALTH_PROBES','requests':[],'health_probes':[],'isolation_procedure_status':'NOT_VERIFIED','recovery_status':'NOT_RUN'}
 try:
  require(__debug__,'拒绝Python优化模式');local_url(a.checkout);local_url(a.collector_health)
  require(a.isolation_record,'必须提供操作者隔离记录；端点拒绝连接本身不能证明隔离操作')
  record_bytes=pathlib.Path(a.isolation_record).read_bytes();record=json.loads(record_bytes)
  require(set(record)=={'scope','service','health_endpoint','action','started_at','evidence_sha256'},'隔离记录字段不完整')
  require(record['scope']=='this-lab-only' and record['service']=='collector' and record['health_endpoint']==a.collector_health and record['action'] in ('stop','network-isolate'),'隔离目标或范围不符合本实验')
  started=datetime.datetime.fromisoformat(record['started_at'].replace('Z','+00:00'));require(started.tzinfo is not None,'隔离记录缺时区')
  require(isinstance(record['evidence_sha256'],str) and re.fullmatch('[0-9a-f]{64}',record['evidence_sha256']),'隔离操作证据hash缺失')
  result['isolation_record_sha256']=hashlib.sha256(record_bytes).hexdigest();result['isolation_procedure_status']='OPERATOR_RECORDED_NOT_INDEPENDENTLY_VERIFIED'
  first=probe(a.collector_health);result['health_probes'].append(first);require(first['classification']=='CONNECTION_REFUSED','没有建立连接拒绝：'+first['classification'])
  seen=set()
  for i in range(20):
   req=urllib.request.Request(a.checkout.rstrip('/')+'/checkout',data=b'{"sku":"book","scenario":"ok"}',headers={'Content-Type':'application/json'});started=time.monotonic()
   with urllib.request.urlopen(req,timeout=4) as r:
    if hasattr(r,'geturl'):require(r.geturl()==req.full_url,'业务目标发生重定向')
    body=json.load(r);status=r.status;trace=r.headers.get('X-Trace-Id')
   elapsed=time.monotonic()-started
   require(status==200 and body=={'result':'confirmed','attempts':1},'业务响应不满足正常请求契约')
   require(0<=elapsed<3.5,'请求超出耗时预算')
   require(isinstance(trace,str) and re.fullmatch('[0-9a-f]{32}',trace) and trace!='0'*32 and trace not in seen,'业务trace ID缺失/非法/重用');seen.add(trace)
   result['requests'].append({'sequence':i,'status':status,'elapsed_seconds':elapsed,'trace_id':trace})
  last=probe(a.collector_health);result['health_probes'].append(last);require(last['classification']=='CONNECTION_REFUSED','结束时health不再拒绝连接')
  result['status']='PASS'
  result['limitation']='只证明起止两个health探测拒绝连接及期间业务请求结果；不能证明操作者隔离步骤、全时段停机或零丢失'
 except Exception as e:result.update({'status':'FAIL','reason':repr(e)})
 pathlib.Path(a.output).write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n');return 0 if result['status']=='PASS' else 1
if __name__=='__main__':raise SystemExit(main())
