# C03作者验收记录

日期：2026-09-30。环境：Linux x86_64、完整Eclipse Temurin21.0.12.1+1、默认--release21、Gradle8.10.2、JUnit Jupiter5.11.4/Platform1.11.4。不会以JRE编译模块的受限模式冒充本次完整JDK结果。

## 已实际运行

- 7个任务、10个UTF-16答案占位；全部完整解与页内代码、可见副本同步
- 参考实现30个JUnit测试全部通过；7个完整调用端实际退出成功
- 7个学习者占位起点编译成功，分别有预期断言/待实现失败
- 7种替代正确实现全部通过；19个错误变异全部被公开测试击杀
- 全部主线Java源码/测试/Usage与替代解使用GoogleJavaFormat1.24.0 AOSP四空格，dry-run检查通过
- 真实Gradle8.10.2 test：7模块、30测试、0失败；使用官方依赖本地仓和临时init脚本进行离线解析
- 全新普通学习者目录真实Gradle --continue test：7模块均失败，30测试中21个预期失败，0编译错误；这不是插件生成归档
- javap实际反汇编；JDK21 --release8与--release17编译/业务样例对照；公开模块调用成功、未导出包反例编译失败
- G1与Serial在相同32MiB堆、相同4096*65536字节payload负载下业务校验一致，日志与停顿分位数实际产生。单次冷启动、尾样本少，不推导性能优劣
- 本课自建premain Instrumentation探针对默认/关闭压缩对象引用两组记录浅大小、完整VM参数。浅大小不是深大小/规范固定布局，也不能证明逃逸分析优化
- CPU、锁、保留、池四种12秒隔离进程均产出JFR、jfr summary/print和最终清理输出；最终格式化后重新采集
- JDK25资料附录的缺失环境分支实际输出NOT_RUN并退出3；只有已有25环境才自选运行，不是V1毕业要求，不安装/下载其他JDK

## 明确未通过或未运行

- Wrapper直接首次下载因Network is unreachable失败；本地官方Gradle分发实跑通过不等于网络下载已恢复
- jcmd Attach：四模式VM.version超过5秒，显式StartAttachListener后仍如此。JFR独立采集成功，但线程转储、直方图、heap dump/保留链检查均未完成；不修改安全设置绕过
- IDEA2026.1.5特定build/Academy插件组合：本课程的预览、Check、提示、重置、插件导出与干净导入NOT_RUN
- 实际JDK8/17虚拟机运行、JDK25编译运行、固定GA源码IDE断点、非Linux脚本和用户独立掌握度：NOT_RUN

## 可复核证据

verification-report.json保留逐任务计数与状态。原始编译/JUnit日志在build/verification；真实Gradle日志在build/gradle-final.log和build/gradle-learner.log；实验材料在build/evidence。大型JFR/heap文件不提交，四份中文事故档案保留实际计数与JFR文件SHA256，工具缺失处如实注明。

本次没有启动Docker、打开业务端口、安装软件、访问用户电脑、推送GitHub或触碰其他课程源码。作者脚本只按给定JAR验证，不要求学习者依赖工作区外文件。临时离线依赖映射不写入正式build.gradle。
