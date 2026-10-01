#!/usr/bin/env python3
"""运行每节完整调用方，核对可观察结果；不会把调用通过扩大成所有测试通过。"""
from pathlib import Path
import subprocess,json,os,argparse
ROOT=Path(__file__).resolve().parents[1]
parser=argparse.ArgumentParser();parser.add_argument('--jdk',type=Path,default=Path(os.environ['JAVA_HOME']) if os.environ.get('JAVA_HOME') else None);args=parser.parse_args()
if args.jdk is None:parser.error('请设置JAVA_HOME或使用--jdk指定完整JDK21')
JDK=args.jdk;records=[]
expected={'01-configuration':['最大购买数量：3'],'02-http-contract':['真实HTTP创建成功','"totalFen":300'],'03-transactions':['剩余库存：8，订单数：1'],'04-test-layers':['两件商品报价：300分'],'05-security':['公开接口200，受保护接口匿名401'],'06-runtime-lifecycle':['任务结果：42'],'07-integrated-service':['真实HTTP创建成功','"totalFen":300'],'08-container-di':['订单创建于示例时刻'],'09-bean-lifecycle':['配置名称：企业订单','销毁'],'10-circular-boundary':['早期引用保持身份：true'],'11-aop-proxy':['代理结果：5','退出:charge'],'12-transaction-source':['独立审计'],'13-mvc-source':['"tenant":"acme"','"orderId":7'],'14-autoconfiguration':['欢迎，学习者']}
for item in json.loads((ROOT/'authoring/manifest.json').read_text()):
 task=ROOT/item['path'];cp=(task/'build/verification-classpath.txt').read_text()
 result=subprocess.run([str(JDK/'bin/java'),'-Dserver.address=127.0.0.1','-cp',cp,'labs.frameworks.Usage'],capture_output=True,text=True,timeout=45)
 output=result.stdout+result.stderr;log=ROOT/'build/callers'/f'{item["name"]}.log';log.parent.mkdir(parents=True,exist_ok=True);log.write_text(output)
 assert result.returncode==0,(item['name'],log)
 assert all(s in output for s in expected[item['name']]),(item['name'],'调用结果不符',log)
 records.append({'task':item['name'],'status':'passed','expected_fragments':expected[item['name']]});print(item['name'],'真实调用方通过',flush=True)
(ROOT/'authoring/callers-report.json').write_text(json.dumps({'status':'passed','callers':records},ensure_ascii=False,indent=2)+'\n')
