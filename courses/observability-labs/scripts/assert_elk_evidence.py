#!/usr/bin/env python3
"""Validate complete, hashed operator-collected evidence; file contents never prove collection origin."""
import argparse,datetime,hashlib,json,math,pathlib,re
INDEX='course-observability-fixture'
TYPES={'@timestamp':'date','event_id':'keyword','event':'keyword','service':'keyword','route':'keyword','status':'integer','trace_id':'keyword','span_id':'keyword','duration_ms':'double'}
class MissingEvidence(ValueError):pass
def require(ok,message):
 if not ok:raise ValueError(message)
def load_file(path):return pathlib.Path(path).read_text()
def verify_files(manifest,files):
 if not {'schema_version','stdout_stderr_captured','log_files_complete','rotation_gap','logger_levels','config_debug','query','files','run_id','collection_started_at','collection_finished_at'}<=set(manifest):raise MissingEvidence('采集元数据字段不完整')
 require(manifest.get('schema_version')==1,'采集manifest版本错误')
 require(isinstance(manifest['run_id'],str) and re.fullmatch('[a-zA-Z0-9_-]{1,64}',manifest['run_id']),'run_id不合法')
 start=datetime.datetime.fromisoformat(manifest['collection_started_at'].replace('Z','+00:00'));end=datetime.datetime.fromisoformat(manifest['collection_finished_at'].replace('Z','+00:00'))
 require(start.tzinfo is not None and end.tzinfo is not None and end>=start,'采集时间窗无效')
 require(manifest.get('stdout_stderr_captured') is True and manifest.get('log_files_complete') is True and manifest.get('rotation_gap') is False,'日志采集范围/轮转不完整')
 levels=manifest.get('logger_levels',{})
 for key in ('root','logstash.filters.json','logstash.filters.ruby'):require(str(levels.get(key,'')).upper() in ('INFO','WARN','ERROR'),'解析器/根logger可能打印完整event')
 require(manifest.get('config_debug') is False,'禁止config.debug')
 query=manifest.get('query',{})
 require(query.get('index')==INDEX,'查询index不明确或有过滤/alias范围')
 body=query.get('body',{})
 require(set(body)=={'query','track_total_hits','size','sort'} and body['query']=={'match_all':{}} and body['track_total_hits'] is True and type(body['size']) is int and 2<=body['size']<=1000 and body['sort']==[{'@timestamp':'asc'}],'要求全索引match_all、exact total、足够size、明确排序')
 declared=manifest.get('files',{});require(set(declared)==set(files),'所有必要输出/日志都必须在采集manifest中')
 for role,path in files.items():
  item=declared[role];data=pathlib.Path(path).read_bytes()
  require(item.get('sha256')==hashlib.sha256(data).hexdigest(),'采集文件hash不匹配: '+role)
  require(item.get('name')==pathlib.Path(path).name,'采集文件名不匹配: '+role)
 return body
def validate(response,mapping,quarantine,logs):
 require(response.get('timed_out') is False and not response.get('terminated_early',False),'查询超时/提前终止')
 shards=response.get('_shards',{});require(type(shards.get('total')) is int and shards['total']>0 and shards.get('successful')==shards['total'] and shards.get('failed')==0,'分片结果不完整')
 block=response.get('hits',{});total=block.get('total',{})
 require(type(total.get('value')) is int and total=={'value':2,'relation':'eq'},'必须证明exact总文档数为2，不能拿一页数量当总量')
 hits=block.get('hits',[]);require(len(hits)==2,'响应分页不完整')
 expected_ids={'11111111-1111-1111-1111-111111111111','22222222-2222-2222-2222-222222222222'}
 require({h.get('_id') for h in hits}==expected_ids,'文档ID缺失/重复/额外')
 timestamps=[]
 for h in hits:
  require(h.get('_index')==INDEX,'命中其他index')
  d=h.get('_source',{});require(set(d)==set(TYPES),'文档字段集合错误')
  require(d.get('event_id')==h['_id'] and d.get('event')=='http.completed','业务事件标识错误')
  checkout=h['_id'].startswith('1')
  require(d.get('service')==('checkout' if checkout else 'inventory') and d.get('route')==('/checkout' if checkout else '/inventory/{sku}'),'服务/路由错误')
  require(type(d.get('status')) is int and d['status']==(200 if checkout else 503),'状态字段错误')
  require(d.get('trace_id')=='a'*32 and d.get('span_id')==('b'*16 if checkout else 'c'*16),'关联ID错误')
  require(type(d.get('duration_ms')) in (int,float) and math.isfinite(d['duration_ms']) and d['duration_ms']==(12.5 if checkout else 2.5),'耗时字段错误')
  ts=datetime.datetime.fromisoformat(d['@timestamp'].replace('Z','+00:00'));require(ts.utcoffset()==datetime.timedelta(0),'必须UTC时间');timestamps.append(ts)
 require(timestamps==sorted(timestamps),'事件时间未排序')
 require(not quarantine.strip(),'非法输入应丢弃；旧隔离输出必须为空')
 require(set(mapping)=={INDEX},'mapping范围不明确')
 m=mapping[INDEX].get('mappings',{});require(m.get('dynamic')=='strict','mapping不是strict')
 props=m.get('properties',{});require(set(props)==set(TYPES) and all(props[k]=={'type':v} for k,v in TYPES.items()),'mapping字段或类型不完整')
 combined=json.dumps(response)+json.dumps(mapping)+quarantine+''.join(logs.values())
 require('synthetic-quarantine-secret' not in combined,'合成敏感内容泄漏到输出或Logstash自身日志')
 require(not any(re.search(r'(\[|\"level\"\s*:\s*\")\s*(DEBUG|TRACE)',v) for v in logs.values()),'日志包含DEBUG/TRACE输出')
 self_logs=''.join(v for k,v in logs.items() if k.startswith('logstash_log_'))
 require(self_logs.count('C12_REJECTED_INVALID_EVENT')==3,'必须从完整自身日志确认3条固定拒绝标记')
 return {'unique_documents':2,'rejected_events':3}
def main(argv=None):
 p=argparse.ArgumentParser();p.add_argument('--search-response',required=True);p.add_argument('--quarantine',required=True);p.add_argument('--mapping-response',required=True);p.add_argument('--collection-manifest');p.add_argument('--logstash-stdout');p.add_argument('--logstash-stderr');p.add_argument('--logstash-log',action='append');p.add_argument('--output',required=True);a=p.parse_args(argv)
 result={'status':'BLOCKED','evidence_type':'ASSERTIONS_OVER_HASHED_OPERATOR_FILES','collection_origin_status':'NOT_VERIFIED'}
 try:
  require(__debug__,'拒绝Python优化模式')
  if not (a.collection_manifest and a.logstash_stdout and a.logstash_stderr and a.logstash_log):raise MissingEvidence('缺少查询/采集元数据或Logstash stdout/stderr/完整日志')
  files={'search':a.search_response,'mapping':a.mapping_response,'quarantine':a.quarantine,'logstash_stdout':a.logstash_stdout,'logstash_stderr':a.logstash_stderr}
  files.update({f'logstash_log_{i}':v for i,v in enumerate(a.logstash_log)})
  require(len({str(pathlib.Path(x).resolve()) for x in files.values()})==len(files),'证据文件不能重复冒充不同通道')
  manifest=json.loads(load_file(a.collection_manifest));verify_files(manifest,files)
  logs={k:load_file(v) for k,v in files.items() if k.startswith('logstash_')}
  detail=validate(json.loads(load_file(a.search_response)),json.loads(load_file(a.mapping_response)),load_file(a.quarantine),logs)
  result.update({'status':'PASS',**detail,'file_sha256':{k:hashlib.sha256(pathlib.Path(v).read_bytes()).hexdigest() for k,v in files.items()},'limitation':'仅校验所提供文件及声明的采集范围；真实来源仍须操作者执行记录审阅'})
 except (MissingEvidence,OSError) as e:result.update({'status':'BLOCKED','reason':repr(e)})
 except Exception as e:result.update({'status':'FAIL','reason':repr(e)})
 pathlib.Path(a.output).write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n');return 0 if result['status']=='PASS' else 1
if __name__=='__main__':raise SystemExit(main())
