#!/usr/bin/env python3
"""验证官方固定标签与实际源码路径，记录原始字节哈希，避免引用移动主干。"""
from pathlib import Path
import urllib.request,os,json,hashlib,concurrent.futures
os.environ['NO_PROXY']='';os.environ['no_proxy']=''
R=Path(__file__).resolve().parents[1]
SOURCES=[
 ('grpc/grpc-java','v1.71.0',['core/src/main/java/io/grpc/internal/ClientCallImpl.java','core/src/main/java/io/grpc/internal/RetriableStream.java','stub/src/main/java/io/grpc/stub/ClientCalls.java','stub/src/main/java/io/grpc/stub/ServerCalls.java']),
 ('apache/dubbo','dubbo-3.3.6',['dubbo-cluster/src/main/java/org/apache/dubbo/rpc/cluster/support/FailoverClusterInvoker.java','dubbo-config/dubbo-config-api/src/main/java/org/apache/dubbo/config/ReferenceConfig.java','dubbo-rpc/dubbo-rpc-api/src/main/java/org/apache/dubbo/rpc/filter/ContextFilter.java','dubbo-registry/dubbo-registry-zookeeper/src/main/java/org/apache/dubbo/registry/zookeeper/ZookeeperRegistry.java']),
 ('resilience4j/resilience4j','v2.3.0',['resilience4j-circuitbreaker/src/main/java/io/github/resilience4j/circuitbreaker/internal/CircuitBreakerStateMachine.java','resilience4j-bulkhead/src/main/java/io/github/resilience4j/bulkhead/internal/SemaphoreBulkhead.java']),
 ('mysql/mysql-connector-j','9.2.0',['src/main/user-impl/java/com/mysql/cj/jdbc/MysqlXAConnection.java']),
 ('apache/kafka','3.9.1',['clients/src/main/java/org/apache/kafka/clients/producer/internals/Sender.java','clients/src/main/java/org/apache/kafka/clients/producer/internals/TransactionManager.java']),
 ('redis/redis','7.4.7',['src/db.c','src/eval.c']),
 ('redis/jedis','v5.2.0',['src/main/java/redis/clients/jedis/Jedis.java']),
]
def get(url):
 req=urllib.request.Request(url,headers={'User-Agent':'backend-interview-labs-source-verifier'})
 return urllib.request.urlopen(req,timeout=40).read()
def verify(item):
 repo,tag,files=item; entry={'repository':repo,'tag':tag,'files':[]}
 try:
  obj=json.loads(get(f'https://api.github.com/repos/{repo}/git/ref/tags/{tag}'))['object']
  if obj['type']=='tag':obj=json.loads(get(obj['url']))['object']
  sha=obj['sha'];entry['commit']=sha
  for path in files:
   raw=get(f'https://raw.githubusercontent.com/{repo}/{sha}/{path}')
   entry['files'].append({'path':path,'sha256':hashlib.sha256(raw).hexdigest(),'bytes':len(raw),'url':f'https://github.com/{repo}/blob/{sha}/{path}'})
  entry['status']='verified'
 except Exception as failure:entry['status']='failed';entry['error']=str(failure)
 return entry
with concurrent.futures.ThreadPoolExecutor(max_workers=7) as pool: result=list(pool.map(verify,SOURCES))
(R/'authoring/source-verification.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
for item in result:print(item['repository'],item['status'],item.get('commit'),item.get('error',''))
