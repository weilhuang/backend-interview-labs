#!/usr/bin/env python3
"""Actual HTTP/Jaeger evidence only; metrics and Collector reliability are separate NOT_RUN checks."""
import argparse,json,math,pathlib,re,time,urllib.request,urllib.error,urllib.parse
def require(ok,message):
 if not ok:raise ValueError(message)
def validate_url(url):
 u=urllib.parse.urlsplit(url)
 require(u.scheme=='http' and u.hostname in ('127.0.0.1','localhost') and not u.username and not u.password and not u.query and not u.fragment,'仅允许无凭证/query/fragment的回环HTTP URL')
 return url.rstrip('/')
def valid_id(value,size):return isinstance(value,str) and re.fullmatch('[0-9a-f]{'+str(size)+'}',value) is not None and value!='0'*size
def tags(span):
 items=span.get('tags');require(isinstance(items,list),'缺少span tags')
 result={}
 for x in items:
  require(isinstance(x,dict) and 'key' in x and 'value' in x,'无效tag')
  require(x['key'] not in result,'重复tag key')
  require(not any(v in str(x['key']).lower() for v in ('authorization','cookie','password','payload','baggage','email','http.request.header','http.response.header')),'禁止敏感或原始请求属性')
  result[x['key']]=x['value']
 return result
def validate_trace(payload,trace_id,scenario,body):
 count=5 if scenario=='retry' else 3
 require(valid_id(trace_id,32),'无效响应trace ID')
 require(isinstance(body,dict),'业务响应必须为JSON对象')
 if scenario=='fail':require(body=={'result':'inventory_unavailable'},'503响应体不符合业务契约')
 else:require(body=={'result':'confirmed','attempts':2 if scenario=='retry' else 1},'响应结果/尝试次数不符合业务契约')
 require(not payload.get('errors'),'Jaeger查询返回errors')
 traces=payload.get('data');require(isinstance(traces,list) and len(traces)==1,'必须返回唯一目标trace')
 trace=traces[0];require(trace.get('traceID')==trace_id,'trace顶层ID不匹配')
 spans=trace.get('spans');require(isinstance(spans,list) and len(spans)==count,'span数量不符合场景')
 processes=trace.get('processes');require(isinstance(processes,dict),'缺少service/process映射')
 by_id={};attrs={};parents={};children={}
 for s in spans:
  sid=s.get('spanID');require(valid_id(sid,16) and sid not in by_id,'span ID非法或重复')
  require(s.get('traceID')==trace_id,'混入不同trace')
  start=s.get('startTime');duration=s.get('duration')
  require(type(start) is int and start>0 and type(duration) is int and duration>=0,'span起点/持续时间非法')
  proc=processes.get(s.get('processID'),{});require(proc.get('serviceName') in ('checkout','inventory'),'未知或缺少service.name')
  t=tags(s);require(t.get('span.kind') in ('server','client'),'缺少SERVER/CLIENT角色')
  by_id[sid]=s;attrs[sid]=(proc['serviceName'],t);children[sid]=[]
 for sid,s in by_id.items():
  refs=s.get('references');require(isinstance(refs,list) and len(refs)<=1,'父引用必须唯一')
  if refs:
   ref=refs[0];require(ref.get('refType')=='CHILD_OF' and ref.get('traceID')==trace_id,'非法或跨trace父引用')
   parent=ref.get('spanID');require(parent in by_id and parent!=sid,'父引用不存在/自循环')
   parents[sid]=parent;children[parent].append(sid)
 roots=set(by_id)-set(parents);require(len(roots)==1,'必须有且仅有一个根')
 root=next(iter(roots));seen=set();active=set()
 def visit(sid):
  require(sid not in active,'检测到父子环');require(sid not in seen,'重复可达span')
  active.add(sid);seen.add(sid)
  for child in children[sid]:visit(child)
  active.remove(sid)
 visit(root);require(seen==set(by_id),'存在孤立或环状子图')
 require(attrs[root][0]=='checkout' and attrs[root][1]['span.kind']=='server' and by_id[root].get('operationName')=='POST /checkout','根必须是checkout SERVER')
 clients=children[root];require(len(clients)==(2 if scenario=='retry' else 1),'checkout客户端尝试数错误')
 seen_attempts=set()
 def check_status(sid,expected):
  t=attrs[sid][1];require(type(t.get('http.response.status_code')) is int and t['http.response.status_code']==expected,'HTTP span状态不匹配')
  require('error' not in t or type(t['error']) is bool,'error标签必须为boolean')
  require('otel.status_code' not in t or t['otel.status_code'] in ('ERROR','OK','UNSET',0,1,2),'未知otel.status_code')
  if 'error' in t and 'otel.status_code' in t:require(t['error']==(t['otel.status_code'] in ('ERROR',2)),'错误标记互相矛盾')
  error=t.get('error') is True or t.get('otel.status_code') in ('ERROR',2)
  require(error==(expected>=400),'span错误标签与真实响应不一致')
 check_status(root,503 if scenario=='fail' else 200)
 for cid in clients:
  service,t=attrs[cid];require(service=='checkout' and t['span.kind']=='client' and by_id[cid].get('operationName')=='GET /inventory/{sku}','库存CLIENT服务/角色/操作错误')
  attempt=t.get('lab.attempt');require(type(attempt) is int and attempt not in seen_attempts,'重试attempt缺失/重复');seen_attempts.add(attempt)
  require(len(children[cid])==1,'每个CLIENT必须对应一个库存SERVER')
  iid=children[cid][0];service,it=attrs[iid]
  require(service=='inventory' and it['span.kind']=='server' and by_id[iid].get('operationName')=='GET /inventory/{sku}' and not children[iid],'库存SERVER服务/角色/叶子关系错误')
  expected=503 if scenario=='fail' or (scenario=='retry' and attempt==1) else 200
  check_status(cid,expected);check_status(iid,expected)
  # Only compare same-process clock intervals; cross-service absolute clocks may be skewed.
  r,c=by_id[root],by_id[cid]
  require(r['processID']==c['processID'],'本fixture checkout SERVER/CLIENT应属于同一process')
  require(r['startTime']<=c['startTime'] and c['startTime']+c['duration']<=r['startTime']+r['duration']+1,'同进程CLIENT跨度超出SERVER')
 require(seen_attempts==({1,2} if scenario=='retry' else {1}),'重试序号集合错误')
 return {'span_count':count,'services':['checkout','inventory'],'topology':'checkout SERVER -> checkout CLIENT -> inventory SERVER','metrics_status':'NOT_RUN'}
def request(url,body=None):
 req=urllib.request.Request(url,data=None if body is None else json.dumps(body).encode(),headers={'Content-Type':'application/json'})
 try:
  with urllib.request.urlopen(req,timeout=5) as r:
   if hasattr(r,'geturl'):require(validate_url(r.geturl()).split('/')[2]==validate_url(url).split('/')[2],'拒绝跨目标重定向')
   return r.status,dict(r.headers),json.load(r)
 except urllib.error.HTTPError as e:return e.code,dict(e.headers),json.load(e)
def main(argv=None):
 p=argparse.ArgumentParser();p.add_argument('--checkout',default='http://127.0.0.1:18081');p.add_argument('--jaeger',default='http://127.0.0.1:16686');p.add_argument('--output',required=True);p.add_argument('--wait-seconds',type=float,default=20);a=p.parse_args(argv)
 result={'status':'BLOCKED','evidence_type':'HTTP_AND_TRACE_QUERY_ONLY','metrics_status':'NOT_RUN','collector_reliability_status':'NOT_RUN','cases':[]}
 try:
  require(__debug__,'拒绝Python优化模式');checkout=validate_url(a.checkout);jaeger=validate_url(a.jaeger);require(0<a.wait_seconds<=60,'等待预算越界')
  seen=set()
  for scenario,status in [('ok',200),('fail',503),('retry',200)]:
   code,headers,body=request(checkout+'/checkout',{'sku':'book','scenario':scenario});require(code==status,'业务HTTP状态错误')
   trace=next((v for k,v in headers.items() if k.lower()=='x-trace-id'),None);require(valid_id(trace,32) and trace not in seen,'trace ID缺失/重用');seen.add(trace)
   deadline=time.monotonic()+a.wait_seconds
   while True:
    qstatus,_,payload=request(jaeger+'/api/traces/'+trace);require(qstatus==200,'Jaeger查询HTTP状态错误')
    if payload.get('data'):break
    require(time.monotonic()<deadline,'目标trace未在预算内可查询');time.sleep(.25)
   detail=validate_trace(payload,trace,scenario,body)
   result['cases'].append({'scenario':scenario,'status':'PASS','trace_id':trace,'http_status':code,**detail,'raw_query':payload})
  result['status']='PASS'
 except (urllib.error.URLError,TimeoutError,ConnectionError) as e:result.update({'status':'BLOCKED','reason':repr(e)})
 except Exception as e:result.update({'status':'FAIL','reason':repr(e)})
 pathlib.Path(a.output).write_text(json.dumps(result,indent=2)+'\n');return 0 if result['status']=='PASS' else 1
if __name__=='__main__':raise SystemExit(main())
