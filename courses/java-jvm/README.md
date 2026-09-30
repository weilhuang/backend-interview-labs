# JVM与现代Java实验课程 · V1作者验收版

状态：作者CLI与真实Gradle验收已完成（30测试、7替代解、19错误变异），详见[阶段报告](阶段报告.md)。尚未通过本课程专属Academy预览、Check、重置、插件导出与干净导入，不称为可用发行归档。不是JetBrains官方课程。七个C03单元完整覆盖，不用两周路线删减内容。

## 版本、依赖与边界

| 项目 | 本课要求/验证边界 |
|---|---|
| 主线JDK | 完整Eclipse Temurin21.0.12.1+1；统一JDK21、--release21，无预览开关 |
| 源码阅读 | OpenJDK21 GA jdk-21+35 / 890adb6410dab4606a4f26a942aed02fb2f55387；GA阅读与供应商补丁调试分开 |
| 显式旧版对照 | 同一JDK21以--release8、--release17编译；不代表在实际8/17 VM运行 |
| 新版资料附录 | 25示例仅作显式版本对照；已有完整JDK25时自选运行，无环境就NOT_RUN；V1学习与毕业只要求JDK21，不要求另装或下载JDK |
| Gradle/JUnit | Wrapper8.10.2；Jupiter5.11.4，Platform1.11.4；依赖来自Maven Central |
| IDE/Academy | 目标IntelliJ IDEA2026.1.5；实际build与插件组合、导入/Check/提示/重置/导出未在本课验收 |
| Python | Python3.12执行轻量CLI；作者验证另需PyYAML6.0.2与指定JUnit独立JAR |
| 前端/Node | 不需要 |
| Docker/Compose/镜像/Testcontainers | 不需要；本课没有外部服务或重复镜像台账 |
| 资源/端口 | 不开放网络端口；测试堆192MiB；诊断堆96MiB、JFR16MiB、空闲磁盘至少256MiB；单模式12秒 |
| 素材 | jvm/七课全部src、调用端、test、task.md与solutions；scripts/、experiments/独立包含 |

先修：C00基本编译、异常、集合；事故诊断另需C02锁与线程池。完成标准：能按症状选择工具、提交因果证据、修复并补回归；不能用“调大堆”代替分析。

## 打开与自检

在IDEA中打开本目录而非仓库根，Project SDK、Gradle JVM、测试JVM均设完整JDK21。IDE启动运行时不是项目SDK。首次依赖解析需要联网；不自动安装JDK或修改全局设置。

```sh
python scripts/lab.py doctor
./gradlew test
./gradlew :jvm-01-loading-lab:run
python scripts/lab.py bytecode
python scripts/lab.py layout
python scripts/lab.py migration
python scripts/lab.py modules
python scripts/lab.py gc
python scripts/lab.py diagnose --mode lock
```

C03-07的官方资料阅读和JDK21规则模型属于主线；五个25源码示例是可选资料附录。只有已经拥有JDK25且自愿验证时，才指定JAVA25_HOME并运行python scripts/version25.py。没有25环境可直接跳过运行，NOT_RUN不影响V1毕业；课程不会自动下载或安装任何JDK。

Windows的Gradle命令换gradlew.bat。诊断脚本使用JDK工具与Python；作者云端Linux证据不能冒充Windows/macOS实测。每次只运行一个诊断模式；不接受外部PID、不连接真实业务系统。build/evidence内只包含合成数据，自行保留后可删除对应单次目录。普通test不会运行诊断、生成heap dump或打开端口。

## 学习路线

1. [字节码、加载与初始化](jvm/01-loading/lab/task.md)：运行时类型身份、单目标隔离加载器、javap
2. [内存与生命周期](jvm/02-lifecycle/lab/task.md)：有界保留、引用类型、关闭与suppressed
3. [GC受控实验](jvm/03-gc/lab/task.md)：同负载G1/Serial、分配与停顿证据
4. [JVM事故工具链](jvm/04-diagnostics/lab/task.md)：CPU/锁/保留/池四类故障、jcmd/JFR、资源修复
5. [8到17的迁移](jvm/05-migration/lab/task.md)：Stream/time/Optional/var/switch/record/sealed/modules
6. [21稳定能力](jvm/06-java21/lab/task.md)：record patterns、pattern switch、SequencedCollection、虚拟线程
7. [25与后续版本](jvm/07-java25/lab/task.md)：成熟状态矩阵、官方来源；25隔离编译/缺开关反例仅为可选资料附录

## 答案与起点角色

作者src含完整解；task-info.yaml占位区用于Academy生成起点。每题task.md直接展示同一完整解和中文解释，solutions/*.java.txt是方便单独查看的相同副本。所有测试与调用端可见，没有隐藏评分代码。不能只复制作者工程就称学习者起点。

```sh
python authoring/materialize_learner.py build/learner-preview
python authoring/verify.py --junit-console /你提供的路径/junit-platform-console-standalone-1.11.4.jar
```

作者验证只读取明确提供且SHA固定的JAR，不依赖作者目录缓存，不自动下载。材料化生成普通目录用于完整性验收，不冒充插件课程ZIP。实际Academy归档必须由插件单独创建/检查/导入。

## 证据而非伪通过

- A：契约、可控并发、异常释放、输入边界，用公开JUnit验证
- O：性能、JFR、GC、保留路径，根据[评阅标准](docs/评阅标准.md)判断，不能关键词打分
- R：[源码阅读清单](docs/源码阅读清单.md)，固定tag/SHA、符号、输入、分支、状态及反例
- T：单目标加载器、有界保留、版本开关模型均有意缩小，不能称生产框架

环境不足写INVALID_ENV/BLOCKED；没运行写NOT_RUN。标准解通过、错误解失败、替代解通过与IDE验收是四件不同的事。
