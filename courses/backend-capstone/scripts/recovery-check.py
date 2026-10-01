#!/usr/bin/env python3
"""只在当前课程Compose项目杀停两个Java进程，验证已有数据库事实能跨进程恢复。"""
from pathlib import Path
import json,os,subprocess,time,urllib.request,urllib.error
root=Path(__file__).resolve().parents[1];base='http://127.0.0.1:'+os.environ.get('CAPSTONE_HTTP_PORT','8088')
def control(action,service):subprocess.run(['bash',str(root/'scripts/course.sh'),action,service],check=True,timeout=200)
def call(path,value=None,timeout=40):
 request=urllib.request.Request(base+path,data=None if value is None else json.dumps(value).encode(),headers={'Content-Type':'application/json'},method='GET' if value is None else 'POST')
 with urllib.request.urlopen(request,timeout=timeout) as response:return json.load(response)
def replay_until(id, status):
 end=time.monotonic()+50;last=None
 while time.monotonic()<end:
  try:
   call('/api/replay',{},timeout=min(40,max(0.1,end-time.monotonic())))
   view=call('/api/dashboard',timeout=min(10,max(0.1,end-time.monotonic())))
   if any(x['requestId']==id and x['status']==status for x in view['deliveries']):return view
  except (urllib.error.HTTPError,urllib.error.URLError,TimeoutError) as error:
   if isinstance(error,urllib.error.HTTPError) and error.code!=503:raise
   last=error
  time.sleep(0.5)
 raise AssertionError('恢复后投影未在重试预算内追平：'+str(last))
id='process-'+str(time.time_ns());attempted=False
try:
 attempted=True
 call('/api/orders',{'requestId':id,'sku':'book','quantity':1})
 print('故障边界：订单已提交，杀停订单Java进程',flush=True)
 control('crash-service','orders');control('recover-service','orders')
 assert call('/api/orders/'+id+'?fresh=true')['status']=='RESERVED'
 print('订单进程重建后事实保留；杀停配送Java进程并尝试重放',flush=True)
 control('crash-service','delivery')
 try:call('/api/replay',{});raise AssertionError('配送停止时不应伪造成功')
 except urllib.error.HTTPError as error:assert error.code==503
 before=call('/api/dashboard');assert before['projectionLag']>=1
 control('recover-service','delivery')
 recovered=replay_until(id,'RESERVED');assert next(x for x in recovered['deliveries'] if x['requestId']==id)['status']=='RESERVED'
 call('/api/orders/'+id+'/cancel',{})
 final=replay_until(id,'CANCELLED');assert not [x for x in final['audit'] if x['severity']=='ERROR']
 assert next(x for x in final['deliveries'] if x['requestId']==id)['status']=='CANCELLED'
 report={'请求号':id,'订单Java进程SIGKILL后恢复':True,'配送Java进程SIGKILL时重放拒绝伪成功':True,'配送进程重建后同身份重放':True,'取消后审计':True,'边界':'杀停发生于HTTP确认之后或RPC调用之前；精确提交后丢应答窗口另由显式故障注入测试'}
 (root/'build/process-recovery.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n');print(json.dumps(report,ensure_ascii=False),flush=True)
finally:
 # 仅恢复本项目两个Java服务，不删除表或卷；释放本脚本创建的资源。
 for service in ('delivery','orders'):
  try:control('recover-service',service)
  except Exception as error:print('清理时服务尚未恢复：',service,type(error).__name__,flush=True)
 if attempted:
  try:call('/api/orders/'+id+'/cancel',{})
  except urllib.error.HTTPError as error:
   if error.code!=409:print('本次订单需后续按原号取消：',id,'HTTP',error.code,flush=True)
  except Exception as error:print('本次订单需后续按原号取消：',id,type(error).__name__,flush=True)
