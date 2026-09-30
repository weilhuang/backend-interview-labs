#!/usr/bin/env python3
"""把真实运行记录缩成学习者可读证据，不复制大转储、不编造缺失工具输出。"""
from pathlib import Path
import json,re,hashlib,yaml
R=Path(__file__).resolve().parents[1]
evidence=R/'build/evidence'
for mode,title,mechanism,repair in [
 ('cpu','CPU热点','本模式只做有界计算并每批停10ms；不能将它写成持续100%CPU事故。执行采样若只有1条，能定位一次采样位置但不足以估算方法CPU占比。','DiagnosticRepairs.finiteChecksum限制工作量；cpuHasFiniteWorkBudget验证范围与校验和。'),
 ('lock','监视器竞争','持锁者在CountDownLatch上等待，竞争者等待同一monitor。JFR JavaMonitorEnter在获得锁后记录此前等待；这是有界竞争链，不是永久循环死锁。','把慢操作移到监视器外，只对计数更新加锁；blockingWorkIsOutsideMonitor用latch证明另一调用可以推进。'),
 ('retention','对象保留','合成静态List保留16个256KiB数组，即4MiB payload，12秒finally清空。业务说明可以预测保留路径，但没有heap dump分析不能把预测写成工具已证实。','boundedRetention限制槽数并在finally清空；retentionCannotGrowWithTotalRequests验证总请求增长不扩大保留槽数。'),
 ('pool','线程池饱和','2个worker被受控依赖阻塞、2个任务排队，第5个明确拒绝。ThreadPark只说明等待，还需结合队列状态与业务入口判断池耗尽原因。','显式拒绝、有界队列、释放依赖后shutdown；saturatedPoolRejectsAndCloses验证拒绝与终止。')]:
 candidates=[p for p in evidence.glob('incident-'+mode+'-*/manifest.json')]
 if not candidates:continue
 path=max(candidates,key=lambda p:p.parent.name);data=json.loads(path.read_text());directory=path.parent
 summary=(directory/'jfr-summary.txt').read_text();counts={}
 for event in ['jdk.ExecutionSample','jdk.JavaMonitorEnter','jdk.ThreadPark']:
  match=re.search(r'^\s*'+re.escape(event)+r'\s+(\d+)',summary,re.M);counts[event]=int(match.group(1)) if match else None
 stdout=(directory/'stdout.txt').read_text();completed='实验已清理，保留块=0' in stdout
 digest=hashlib.sha256((directory/'sample.jfr').read_bytes()).hexdigest()
 doc=f'''# {title} · 作者实际隔离实验档案

日期2026-09-30，Linux x86_64，Eclipse Temurin21.0.12.1+1。证据状态：{data['status']}。这是一份合成实验记录，不是真实生产事故。

## 可复现输入与资源

在课程根运行python scripts/lab.py diagnose --mode {mode}。脚本只使用自己创建的PID，-Xmx96m、最多两个应用工作线程、12秒退出、24秒看门狗、JFR16MiB上限。运行耗时{data['elapsed']:.3f}秒（含工具采集），已观察到清理输出：{completed}。

## 实际观察

{mechanism}

JFR计数：ExecutionSample={counts['jdk.ExecutionSample']}，JavaMonitorEnter={counts['jdk.JavaMonitorEnter']}，ThreadPark={counts['jdk.ThreadPark']}。零事件不证明绝无对应行为；1条执行采样不足以做热点占比或延迟分布结论。

jcmd VM.version在5秒内未完成，尝试显式StartAttachListener后仍超时。因此线程转储、直方图与堆保留链检查保持BLOCKED/NOT_RUN，不填造出来的数据。JFR通过启动参数独立记录成功；没有修改操作系统安全配置。

## 修复与回归

{repair}

ResourceGateTest另外验证正常/异常/中断下许可归还；Future取消不是业务已退出，许可只在实际回调finally释放。自动回归通过说明合同成立，不表示已经测到生产性能改善。

## 证据来源与复核边界

原始材料由本机本次build/evidence/{directory.name}生成；不随课程打包大转储。sample.jfr SHA256={digest}。这是实际文件摘要，不是上游源码SHA。

完整jcmd诊断仍需在允许Attach的隔离JDK21进程重新采集。retention的heap dump需明确加--heap；当前没有宣称已验证保留路径。固定OpenJDK源码断点也未完成，不能把JFR事件当成源码调试截图。
'''
 (R/'diagnostics'/f'{title}事故档案.md').write_text(doc)
# 所有已生成的小型阅读材料附带到课程，禁止纳入build大文件。
p=R/'course-info.yaml';c=yaml.safe_load(p.read_text());known={f['name'] for f in c['additional_files']}
for file in sorted((R/'diagnostics').glob('*.md')):
 name=str(file.relative_to(R))
 if name not in known:c['additional_files'].append({'name':name})
p.write_text(yaml.safe_dump(c,allow_unicode=True,sort_keys=False))
