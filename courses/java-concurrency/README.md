# Java并发与JUC：独立课程

## 先选择运行路线

**Academy官方归档导入模式**：用本题Check检查作答，打开对应Usage.java的main运行按钮，或用IDE的Gradle工具窗口执行test/run。Academy2026.9官方导出实际会剔除gradlew、gradlew.bat与gradle-wrapper.jar，仅保留properties；不要在缺少Wrapper的导入目录照抄终端./gradlew命令。项目SDK与Gradle JVM均用完整JDK21。

**源码仓库或普通Gradle学员副本模式**：以下./gradlew命令针对含Wrapper的课程根，Windows用gradlew.bat。完整CLI与诊断教程保留；首次依赖解析失败应区分环境问题与作答失败。


完整JDK21、Gradle Wrapper8.10.2、JUnit5.11.4。默认语言级别和编译目标均21，不需前端、Docker、数据库或外部账号。建议先完成编码恢复与集合课程，但这里的项目不依赖其他课程未完成代码。

## 课程结构
1. JMM：不可变配置、安全发布、复合操作丢更新
2. 取消：启动、协作中断、预算、资源清理
3. 缓冲区：monitor与Condition、容量、排空关闭
4. AQS：一次性门、共享/独占源码、latch/semaphore
5. 原子类：CAS额度、ABA版本、CHM热点计数
6. 线程池：有界排队、扩线程、拒绝、异常、取消与关闭
7. 异步聚合：主/次依赖、deadline、隔离舱、ThreadLocal
8. 虚拟线程：资源约束、取消、线程转储和JFR证据

每节都有可见测试、真正main调用方、标准解逐步解析、正确替代实现、源码符号和独立迁移。8个单元对应完整C02，不以两周面试为理由压缩范围。

## 先运行

```sh
java -version
./gradlew --version
./gradlew test
./gradlew :juc-01-publication-lab:run
```

项目SDK与Gradle JVM都选21。首次构建需访问Gradle发行站和Maven Central。完整JDK应含javac、jcmd、jfr、lib/ct.sym；只有运行时不算可复现开发环境。源码基线OpenJDK21 GA与实际21u补丁运行时分别记录，不伪称二者相同。

作者工程包含答案；Academy生成学员视图时答案区变成可编译待实现桩。也可生成普通Gradle副本：

```sh
python authoring/materialize_learner.py /tmp/java-concurrency-learner
```

目的地必须不存在。普通副本不宣称是Academy归档；完整答案仍在每节task.md。正式归档须由Academy创建并在新目录导入验证，状态见[阶段报告](阶段报告.md)。

## 作者质量与证据

```sh
python authoring/build_course.py
python authoring/verify.py --java-home "$JAVA_HOME" --junit-console /path/to/junit-platform-console-standalone-1.11.4.jar
./gradlew clean test
python scripts/diagnose.py
```

Python只用于作者生成/验证和诊断收集，Java题目本身不依赖Python；作者YAML工具依赖PyYAML6.0.2。verify是真实JDK21编译/JUnit执行，参考解和替代解应通过、未填起点及错误变体应失败。报告位于build/verification/report.json。它不声称验证了IDE Check或源码断点。

[源码路线图](docs/源码路线图.md) · [诊断证据](docs/诊断证据.md) · [证据模板](docs/证据模板.md)

并发测试依赖latch/barrier/手动计时器；超时仅作挂起保护。所有故障工作量有界。JFR、线程转储等观察结果须人工解释，不以跑完命令代替理解，不以一次压力通过证明线程安全。

作者再生成需要官方Maven的google-java-format1.24.0 all-deps工具，SHA-256 812f805f58112460edf01bf202a8e61d0fd1f35c0d4fabd54220640776ec57a1。可用JAVA_FORMAT_JAR或authoring/build_course.py --formatter指定；工具不随课程分发，学员Gradle构建无需它。作者源、替代解、变异、调用端、测试一次统一格式化，再计算UTF-16占位偏移并生成可见答案。

## Academy界面抽检状态

本课程已在云端IDEA2026.1.5（261.27258.48）与Academy2026.9-2026.1-1070完成官方导出和干净导入，8单元识别正常。C02-01 JMM代表题真实Check：起点3失败/1通过，参考解4通过；Reset恢复0/8与两个TODO；PublicationLabUsage实际输出快照、受理序号1、受控错误计数1并以0退出。 中文正文、ASCII、展开提示、公开测试树、长标准答案及两种运行路线已实读。其余7题、Preview按钮流程、IDE动态断点和用户独立掌握未验收；详细范围见阶段报告。
