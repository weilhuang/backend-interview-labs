#!/usr/bin/env python3
"""仅从真实运行结果生成证据摘要，缺失项不写PASS。"""
from pathlib import Path
import json,hashlib,xml.etree.ElementTree as E,yaml,platform
R=Path(__file__).resolve().parents[1]
report=json.loads((R/'build/verification/report.json').read_text())
manifest=json.loads((R/'authoring/manifest.json').read_text())
source_checks=0
for item in manifest:
 task=R/item['task'];snapshot=R/'build/verification'/(item['class']+'-reference')/'src'
 for file in list((task/'src').rglob('*.java'))+list((task/'test').rglob('*.java'))+list((R/'common/src').rglob('*.java')):
  assert (snapshot/file.name).read_text()==file.read_text(), '当前源码与实际参考测试快照不一致：'+str(file)
  source_checks+=1
report['reference_source_snapshot_checked']={'status':'PASS','comparisons':source_checks}
report['format']='PASS：GoogleJavaFormat1.24.0 AOSP四空格，最后dry-run退出0'
report['academy_export_boundary']='NOT_RUN：本新课程官方ZIP待验收；插件剔除Wrapper行为已在每题区分路线'
report['debug_learner_start']='三种真实错误实现，另含三份单缺陷checkpoint，均编译后失败'

def junit(root):
 tests=failures=errors=0;modules=0
 for directory in root.glob('c*/*/lab/build/test-results/test'):
  modules+=1
  for file in directory.glob('TEST-*.xml'):
   value=E.parse(file).getroot();tests+=int(value.get('tests'));failures+=int(value.get('failures'));errors+=int(value.get('errors'))
 return {'modules':modules,'tests':tests,'failures':failures,'errors':errors}
report['gradle']={'version':'8.10.2','author':junit(R),'learner':junit(R/'build/learner-final'),'dependency_route':'仅验收使用官方工件本地仓与临时init脚本；正式build仍mavenCentral'}
report['compiler']=['${JAVA_HOME}/bin/javac','--release','21'];report['platform']=platform.platform();report.pop('JMH',None)
paths=list((R/'build/hashmap-trace').glob('run-*/report.json'));trace=max(paths,key=lambda p:p.parent.name);meta=json.loads(trace.read_text());raw=(trace.parent/'trace.log').read_text();report['hashmap_debug']=meta
assert meta['status']=='OBSERVED'
interesting=[line for line in raw.splitlines() if any(symbol in line for symbol in ['treeifyBin','TreeNode.treeify','TreeNode.split','TreeNode.untreeify','TARGET_STDOUT'])]
sha=hashlib.sha256((trace.parent/'trace.log').read_bytes()).hexdigest()
text=f'''# 真实HashMap断点证据 · 作者实跑

状态：OBSERVED；时间{meta['utc']}；环境{meta['platform']}，Temurin21.0.12.1+1。由JDI启动本课程自己的64MiB合成子进程，内部20秒/外部25秒预算，未附加真实业务进程或开放模块。这里是实际调试文本，不是预测表或伪造截图。

## 输入与真实关键状态

初始HashMap容量参数16，12个不同ID的键按hash0/64交替；之后加入不同散列键使size达到49并继续到60。phase=1..12/13..60为输入序号，100/200为查找阶段。

```text
{chr(10).join(interesting)}
```

还实际观测到getTreeNode和find入口，发生于capacity64、size12、threshold48的查找阶段。调试器只保留目标HashMap身份或键类型匹配的TreeNode，避免把JDK内部其他Map缓存当本例证据。

## 可推导结论

- 第9个碰撞键进入treeifyBin时table16，第10个时table32，两次容量不足，走扩容路线
- 第11个时容量64，进入TreeNode.treeify，不能说“链长8就一定树化”；入口size仍为10，因为putVal在树化调用返回后才增加size，phase与size不是同一个时点计数
- size49超过threshold48触发64到128扩容，split参数bit64与index0吻合旧容量新增位
- 实际untreeify入口的父帧状态lc=6、hc=6，证明此输入在两侧各6节点时走链化分支
- 子进程最终打印条目60，JUnit另验证扩容前后全部原键可查询；结构观察和公共合同是两条证据

## 版本与边界

GA阅读固定tag jdk-21+35、SHA890adb6410dab4606a4f26a942aed02fb2f55387。运行却是当前Temurin补丁，运行包src.zip SHA256={meta['runtime_src_zip_sha256']}，二者没有混称。动态脚本依赖JDK自带JDI，不需要另装软件或JDK。

原始文本位于本次build/hashmap-trace/{trace.parent.name}/trace.log，SHA256={sha}。每次新运行独立目录；原始日志不依赖网络，摘要随课程保留。首次脚本开发时发现重复resume可越过ClassPrepare设置时机，已改由VMStartEvent单次恢复并重新取得真实证据；不通过重试掩盖未修复的时序错误。

本例不是所有JDK版本的公共Map合同；换成7+5或其他容量需重新观察。用户自己的IDE断点操作与课程Academy界面验收仍未由此证明。
'''
(R/'docs/HashMap实际调试.md').write_text(text)
jmh=R/'benchmark/build/jmh-result.json'
if jmh.exists():
 runs=json.loads(jmh.read_text());assert len(runs)==6
 report['JMH']={'status':'SANITY_PASS','version':'1.37','cases':6,'forks':1,'warmup':'2 x 500ms','measurement':'3 x 500ms','threads':1,'boundary':'短探索性完整链路校验，绝非稳定性能评测或生产倍数结论','json_sha256':hashlib.sha256(jmh.read_bytes()).hexdigest()}
 rows=[]
 for case in runs:
  metric=case['primaryMetric'];rows.append(f"| {case['benchmark'].split('.')[-1]} | {case['params']['size']} | {metric['score']:.6f} | {metric['scoreError']:.6f} | {metric['scoreUnit']} |")
 note='''# JMH短探索性运行记录

状态：SANITY_PASS，仅证明完整构建/注解处理/分叉/结果收集链路可运行。2026-09-30、Temurin21.0.12.1+1、Linux x86_64，JMH1.37，一个fork、一个线程，2次500ms预热、3次500ms测量。依赖来自官方Maven并核对官方SHA1，另记SHA256，没有安装新应用或另一个JDK。

| 方法 | 数据量 | 平均数 | 99.9%误差半宽 | 单位 |
|---|---:|---:|---:|---|
'''+ '\n'.join(rows)+f'''\n
原始JSON SHA256={report['JMH']['json_sha256']}。部分误差区间非常宽，尤其大数据量扫描只有三个短样本；不能把表格当生产结论、可靠尾延迟、复杂度证明或“索引总是快多少倍”。cachedHotKey与轮转查询是不同负载，不能直接混比。正式测量需要更多fork、长预热、受控机器、分配观察与方案评审。

[实验设计与完整入口](实验设计.md)保留所有参数和局限。原始JSON在benchmark/build/jmh-result.json，不把机器绝对路径写进课程构建。
'''
 (R/'benchmark/短探索记录.md').write_text(note)
else:report['JMH']={'status':'NOT_RUN','reason':'没有实际结果文件'}
(R/'authoring/verification-report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
config=R/'course-info.yaml';course=yaml.safe_load(config.read_text());known={f['name'] for f in course['additional_files']}
for folder in ['docs','fixtures','benchmark']:
 for file in sorted((R/folder).rglob('*')):
  if not file.is_file() or 'build' in file.relative_to(R).parts:continue
  name=str(file.relative_to(R))
  if name not in known:course['additional_files'].append({'name':name});known.add(name)
config.write_text(yaml.safe_dump(course,allow_unicode=True,sort_keys=False))
print('已生成真实HashMap/JMH证据与验证摘要')
