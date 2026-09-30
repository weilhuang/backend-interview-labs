# C00/C01作者最终验收记录

日期：2026-09-30。实际环境：Linux6.18.44 x86_64、Eclipse Temurin21.0.12.1+1、--release21、Gradle8.10.2、JUnit Jupiter5.11.4/Platform1.11.4。没有借用JRE编译模块受限结果，也没有另装JDK/应用。

## 已通过的自动与构建检查

- 16单元、29个UTF-16答案占位，全部src/test/Usage可见；每节页内标准解与solutions副本对应源码
- 参考实现52个JUnit测试通过；16个完整Usage实际运行成功
- 16个未填写学习者起点全部编译成功后按预期失败；C00-06保留三种真实错误实现，而非三个空函数，并另提供三份单缺陷checkpoint
- 16种替代正确实现全部通过
- 33个独立错误变异全部被公开测试击杀，含舍入、尾空字段、批次提交、主异常覆盖、边界/引用、哈希迁移、TopK顺序与缓存键边界
- 真Gradle8.10.2最终作者test：16模块、52测试、0失败；完整CLI默认fixture输出真实验证
- 全新普通学习者目录真Gradle --continue test：16模块全部按预期失败，52测试中47失败、0编译错误。JUnit errors=0不能解释为没有预期作答失败
- Java源/测试/Usage/共同fixture/替代解/JDI/JMH以GoogleJavaFormat1.24.0 AOSP四空格统一；最终dry-run检查
- 本地Markdown链接、课程附加文件、答案可见性与普通材料化目录完整性已检查

作者测试通过明确提供且SHA固定的JUnit JAR进行；Gradle验收仅使用官方Maven工件的本地仓和临时init脚本，正式build.gradle仍是mavenCentral。临时缓存/绝对路径/第三方依赖不作为课程源码交付。

## 真实源码调试

JDI启动自己的64MiB合成JVM，记录HashMap.treeifyBin/resize与TreeNode.treeify/getTreeNode/find/split/untreeify。实际证据包括16/32容量下先扩容，64容量树化，49条目引起64到128扩容，bit64拆分与lc=6/hc=6时两次untreeify；最终子进程输出60条目。

首次脚本开发发现重复resume可能越过ClassPrepare设置断点的时机，已修复为VMStartEvent单次恢复，再运行取得证据。最终源代码的自动脚本只支持已验证Linux；其他系统手工IDE路线未测试。GA源码阅读SHA与当前补丁src.zip SHA分开记录，不把补丁调试冒充GA二进制。详见docs/HashMap实际调试.md和原始build/hashmap-trace/run-*/trace.log。

## JMH仅完成短探索性链路校验

官方Maven的JMH1.37/core/注解处理器及确切传递依赖已核对官方SHA1，并记录SHA256，全部放build目录。实际Gradle编译注解处理后，三个benchmark×两个数据规模共6种组合跑完，1fork、1线程、2次500ms预热、3次500ms测量，输出JSON。

状态SANITY_PASS，不是稳定性能评测；部分99.9%误差半宽很大，不能把本结果当生产倍数、P99延迟或复杂度证明。cachedHotKey与轮转查询不同负载，禁止混比。细节见benchmark/短探索记录.md与实验设计.md。

## 仍未宣称完成的发布门禁

- 本新课程的Academy预览、Check、提示、重置、官方ZIP导出、干净导入：NOT_RUN，不能借试点或其他课程结果代替
- 当前已知Academy2026.9官方ZIP剔除gradlew/gradlew.bat/wrapper.jar，只保留properties；题面和README已区分源码CLI与导入后Check/IDE Run/Gradle窗口路线
- 用户实际独立编码、IDE三缺陷断点与24小时变式回测：NOT_RUN
- 非Linux脚本兼容、长期/多fork性能评测：NOT_RUN
- 没有Docker/前端/数据库依赖，不把“不需要”混写成“启动通过”

结果摘要：verification-report.json。完整日志：build/verification、build/final-gradle.log、build/learner-final-gradle.log、build/jmh-sanity.log。大型缓存与生成物不提交。本任务未推送GitHub，未修改已冻结JVM或其他课程源码。
