# Java编码恢复与集合源码 · C00/C01完整16单元

V1作者验收课程。它补齐C00/C01完整范围，不把先前12题内部试点当作全部基础课，也不按两周路线删减。每节都有完整工程、调用端、公开测试、答案和解释；课程状态以[中文阶段报告](中文阶段报告.md)的已测/未测清单为准，不将作者CLI通过当Academy归档验收完成。

## 固定版本与全部前置

| 项目 | 要求与边界 |
|---|---|
| JDK | 统一完整Eclipse Temurin21.0.12.1+1，--release21；不需要其他JDK，不自动下载/安装 |
| 源码阅读 | OpenJDK21 GA tag jdk-21+35，commit 890adb6410dab4606a4f26a942aed02fb2f55387；动态调试另记实际补丁与src.zip摘要 |
| Gradle/JUnit | 源码仓库含Wrapper8.10.2；Academy官方ZIP的Wrapper剔除行为见下方路线说明；Jupiter5.11.4、Platform1.11.4；普通测试依赖由Maven Central解析 |
| IDE/Academy | IDEA2026.1.5＋Academy2026.9-2026.1-1070：官方导出/干净导入与三类题Check/Reset已抽检；其余13题及Preview按钮流程未逐一验收，见阶段报告 |
| Python | 3.12执行脚本；作者工具需要PyYAML6.0.2 |
| 前端/Node | 不需要 |
| Docker/镜像/Testcontainers/外部服务 | 不需要；没有本课私建镜像清单 |
| 测试资源 | 单测试进程192MiB；固定种子小样本、latch/future有界等待；不运行无界压力或OOM |
| 源码调试 | JDK自带JDI，启动自己创建的64MiB子进程；Linux已验证情况见报告；本机临时调试通道，不附加真实业务进程 |
| JMH | 1.37，独立benchmark模块，仅-PwithJmh时启用；无额外应用或JDK，结果不足/未跑记NOT_RUN |
| 数据/文件 | 全部合成数据；文件测试只用@TempDir；默认调用端用内存Reader，不读取个人文件 |

## 两条运行路线：源码仓库与Academy官方归档

源码仓库路线：只打开本目录，不打开仓库根。下面所有./gradlew或gradlew.bat命令适用于包含Wrapper的源码课程目录和普通材料化目录。Project SDK、Gradle JVM、测试JVM分别设置JDK21；IDE自身启动JVM不是项目SDK。首次依赖下载失败是环境问题，不是作答错误。

```sh
./gradlew --version
./gradlew test
./gradlew :c00-01-workspace-lab:run
./gradlew :c00-08-capstone-lab:run
./gradlew :c00-08-capstone-lab:cli
./gradlew :c01-08-query-project-lab:run
python scripts/trace_hashmap.py
```

Academy官方归档路线：通过插件导入课程后，用本题Check检查答案；打开Usage的main运行按钮或IDE的Gradle工具窗口运行对应run任务。实际观察到Academy2026.9官方ZIP会剔除gradlew、gradlew.bat与gradle-wrapper.jar，仅保留wrapper.properties；因此不承诺导入目录能在终端执行./gradlew。缺少Wrapper不代表学生代码错；终端CLI练习请使用源码仓库路线，不把普通源码ZIP冒充官方归档。

源码仓库在Windows把./gradlew换gradlew.bat。JDI脚本的其他操作系统兼容性未实测。真实HashMap断点来自自建子进程，20秒内部预算、25秒进程组看门狗，不需要jcmd附加，不修改JDK开放模块/OS安全配置。

## 两条完整学习路线

C00：工作区 -> Money/OrderId -> 订单解析 -> 泛型仓库/Stream -> UTF-8与资源 -> 三缺陷调试 -> 七算法模式 -> 综合CLI。

C01：集合视图 -> 泛型动态数组 -> 双向链表/BFS/单调队列 -> 拉链Map -> 真实HashMap树化/查找/拆分 -> TreeMap/堆/LRU -> 迭代与并发边界 -> 索引查询与JMH。

common/中的Order、ParseFailure、OrderCodec是课程内公开完整checkpoint，使后续题不依赖前题尚未完成的答案。它不是外部仓库依赖，也不是隐藏评分代码。每题task.md下方直接有完整源码和中文解释，solutions/*.java.txt提供相同副本；全部test和Usage可见。

## 作者工程、学习者起点与发行状态

作者src含完整解；task-info.yaml的UTF-16占位生成学习者起点。不能把作者源码目录直接当作未作答学生包。普通目录材料化：

```sh
python authoring/materialize_learner.py build/learner-v1
python authoring/verify.py --junit-console /你已提供的路径/junit-platform-console-standalone-1.11.4.jar
```

脚本不下载JAR，只接受固定摘要。普通学习者目录不是插件导出的Academy ZIP；官方导出/干净导入与C00-01、C00-06、C00-08的Check/提示/重置已另行实测；其他题和Preview按钮流程仍需单独验收。Task面板建议拉宽至约600像素以上再阅读中文长文、代码与ASCII图。

## 源码仓库中的综合CLI与JMH

真实CLI入口labs.foundation.OrderAnalyzer接收“合成输入文件路径 PAID或PENDING”；调用端和端到端测试展示格式与错误码。不要拿个人真实文件验证错误路径。

```sh
./gradlew -PwithJmh :benchmark:jmh
```

JMH是观察实验，详见[实验设计](benchmark/实验设计.md)。默认./gradlew test不会运行基准、不产生性能保证。缺依赖时记录BLOCKED，未运行记NOT_RUN；不可用单次毫秒数证明复杂度或宣称普遍更快。

## 源码、评阅与许可

[固定源码及评阅](docs/源码与评阅.md)、[真实HashMap证据](docs/HashMap实际调试.md)、[全范围对照](docs/范围对照.md)、[第三方说明](THIRD_PARTY_NOTICES.md)。A自动正确性、O观察、R真实源码、T教学模型分开。读过答案后仍需独立变式与口述，不承诺面试结果。
