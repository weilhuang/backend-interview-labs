# 版本冻结 兼容验证与官方来源

## 已知事实与建议分开

本方案编写于 2026-09-30。用户指定 IDEA 2026.1.5，课程开发、测试与验证按云端方向进行，学习端是否使用远程 IDE 尚未确定。已有首包源码的版本配置可只读核对；完整课程的大多数依赖尚未冻结。本文件不会把滚动文档里的“最新版本”复制成已经通过测试的课程环境。

| 项目 | 本次可核对的值或设计决定 | 状态与限制 |
|---|---|---|
| 首包目录 | `courses/java-recovery-collections`，12 个编程任务 | 已看到源码、task.md 与 YAML；不等于 IDE 已验收 |
| 首包课程版本 | 0.1.0 | 来自 gradle.properties，尚需与归档/发布记录绑定 |
| Java 目标 | release 17，Academy JDK_17 | 目标语法/字节码，不等于实际运行 JDK |
| Gradle Wrapper | 8.10.2 | 已在 wrapper 文件固定版本与 SHA-256 |
| JUnit | BOM 5.11.4 | 已在 build.gradle 声明；依赖解析/测试需实测 |
| 首轮执行环境 | 裁剪的 Java 21 环境，已用 javac 21 组件按 -source 17/-target 17 执行 JUnit | 缺少完整 --release 17 API 检查所需内容；不能等同完整 JDK17 或 Gradle 验证 |
| 首轮测试证据 | 制作方报告 65/65 checks 通过；12 空实现与12 错误变体被拒绝；12 任务/20 占位静态有效 | 不是 Gradle/IDE Check/学生归档导入验收，最终结果以首包验证报告为准 |
| IDEA | 目标 2026.1.5 | actual build number 与云端是否已部署仍须验证 |
| Academy 插件 | 待核对与上述 IDE build 的兼容版本 | 不根据模板存在推断插件能加载 |
| 后续 Java 教学线 | 基础首包 17；21 的稳定能力与25 的版本对照独立安排 | 不是把全部课强制升级为 25 |

首包实际 build 使用 Groovy DSL，这是课程配置选择；官方模板使用 Kotlin DSL，不意味着必须逐字沿用模板。改写后仍须保留与插件相容的 source/test 布局、JUnit 平台和失败报告机制，并通过 IDE Check 验证。[官方模板](https://github.com/jetbrains-academy/java-course-template)

## 为什么不能只写一个 JDK 版本

需要分别记录 IDE 的启动运行时、Project SDK、Gradle daemon JVM、javac 工具链、test JVM 与 release 目标。它们可以不同，但必须是明确支持并经过实际测试的组合。仅设置 release=17 不提供完整 JDK，也不自动附加 OpenJDK 17 源码。

Gradle 的运行 JVM 与编译/测试工具链是不同兼容项。JDK 21 运行 Gradle 的支持起点与 JDK 25 不同，因此 JDK 25 专题不能默认沿用首包 Gradle 8.10.2；应在独立课程冻结相容 wrapper 或使用经验证的外部编译流程。[Gradle 兼容矩阵](https://docs.gradle.org/current/userguide/compatibility.html)

## 完整课程的版本线

下面的 family 是选型边界，不是可直接执行的精确依赖锁。正式制作每门课时必须落到版本号/commit/digest，并先验证再发布。

| 课程范围 | 建议隔离的版本线 | 必须成组冻结 |
|---|---|---|
| C00/C01 首包 | Java 17 教学目标；可另测完整 JDK 17/21 运行 | JDK 发行商/build/架构、Gradle、JUnit、Academy、IDE |
| C02/C03 现代 Java | 21 稳定特性；25 独立对照；8/17 以差异题保留 | 编译与运行 JDK、preview flags、源码 tag、分析工具 |
| C04/C05 | Boot 3.5/Framework 6.2 为一条，Boot 4.x/Framework 7.x 为另一条 | Boot BOM、Framework、servlet 容器、Spring Security、测试依赖、Gradle |
| C06 | MySQL 8.4 系列候选，另给与目标岗位旧版本差异 | server patch/image digest、JDBC driver、sql_mode、字符集、隔离级别、持久化设置 |
| C07 | 制作时选择官方可获取且授权可接受的 Redis 稳定线 | server/client、镜像/license、持久化、复制/集群拓扑、Lua/API |
| C08 | Kafka 4.x KRaft 实验线；历史 ZooKeeper 行为独立说明 | broker/client、协议/组协议、镜像、副本与事务配置 |
| C09 | RocketMQ 5.x 实验线，4.x 客户端作为显式对照 | broker/NameServer/Proxy/client、部署模式、镜像与参数 |
| C10 | gRPC/protobuf、Dubbo、resilience 库各自固定 | protoc/runtime/plugin、协议、注册中心、客户端/服务端依赖 |
| C11 | Docker/Compose 与所选本地型隔离 K8s 发行方式；Istio 固定模式 | 引擎/Compose、kind或等价工具、node image、kubectl、Istio、CNI |
| C12 | ELK 三组件兼容线，SkyWalking 独立兼容线 | ES/Logstash/Kibana、agent/OAP/UI/storage 与插件支持矩阵 |
| C13 | 正式发布的 Go 稳定补丁版本，具体版本待制作冻结 | Go toolchain、go.mod/go.sum、grpc/protobuf generator、race 支持平台 |

Spring 官方分别提供 Boot 3.5 与当前版本的系统要求。前者明确其 Framework 和构建工具范围，因此不能把新版 Gradle 或 Framework 随意塞进旧课程依赖；课程制作应引用对应版本页面并保留当时的验证记录。[Boot 3.5 系统要求](https://docs.spring.io/spring-boot/3.5/system-requirements.html)、[Boot 当前系统要求](https://docs.spring.io/spring-boot/system-requirements.html)

JDK 25 文档明确区分已正式特性与预览特性；每道新特性题必须标注所选版本状态和编译/运行开关。不要把“新 JDK”写成永远正确的最新特性清单。[Java 25 语言变化](https://docs.oracle.com/en/java/javase/25/language/java-language-changes-summary.html)

## 可复制的版本台账字段

下列只是待填写的数据结构，不是当前已具备的版本锁：

```yaml
course_id: C01
course_release: pending
status: authored_or_planned_not_import_verified
template:
  repository: https://github.com/jetbrains-academy/java-course-template
  commit: pending_exact_sha
ide:
  product: IntelliJ IDEA
  target_version: 2026.1.5
  actual_build: pending
  academy_plugin_version: pending
jdk:
  vendor: pending
  full_build: pending
  platform: pending
  release_target: 17
  gradle_runtime: pending
  test_runtime: pending
  source_tag: pending
  source_commit: pending
build:
  gradle_version: 8.10.2
  distribution_sha256: copy_from_verified_wrapper
  junit_bom: 5.11.4
  dependency_lock_status: pending
services: []
verification:
  cli_reference_solution: not_recorded_here
  cli_student_expected_failure: not_recorded_here
  ide_check: pending
  student_archive_import: pending
  os_architecture: pending
```

上面字段属于仓库自己的版本台账，不是 Academy course-info.yaml 的扩展。发布前所有必需 pending 值必须变成具体值或明确的“不适用”；不能把 pending 留在实际可运行配置里。

依赖不使用 `latest`、`+` 或无上限区间；Gradle wrapper 留校验和，依赖锁/校验元数据按课维护。容器同时记录人可读 tag 和不可变 digest，镜像架构不同须分别验证。外部实验启动前对照台账检查实际版本，而不是只相信配置文件。[Gradle 依赖锁定](https://docs.gradle.org/current/userguide/dependency_locking.html)

## 源码锚点模板

每个源码题制作时记录如下内容：

- 项目与官方仓库 URL
- release tag、完整 commit SHA、源码文件路径、类与方法符号
- 使用的运行二进制是否与源码同版本，以及 sources jar/src.zip 的来源
- 输入、初始状态、断点、命中的分支和观察到的状态变化
- 从证据可以推出的结论、不能推出的结论、一个反例或版本差异

首包源码阅读已核对标签 `jdk-17+35`，指向 commit `dfacda488bfbe2e11e8d607a6d08527710286982`（制作方报告的官方 tag 核验）；公式题以 OpenJDK 17 为教学线，真实链路也应先使用相同版本。后续 JDK 21 对照单独标注，不能把 JDK 21 源码截图贴成 JDK 17 运行结果。源码链接的版本已固定，但本轮 javac21 编译运行不等于 OpenJDK17 运行期调试。精确版本与验证方式以首包实际记录为准。

## 官方来源与适用范围

这些来源用于核对平台能力和关键机制，不代表相关课程已经实现或每个链接的滚动版本已经适配到课程。源码任务正式制作还需补 tag/commit 精确锚点。

### Academy 与构建

- [JetBrains Academy Java Course Template](https://github.com/jetbrains-academy/java-course-template)：课程根、YAML、Gradle/JUnit 5 示例以及预览/归档文档入口
- [模板构建文件](https://raw.githubusercontent.com/jetbrains-academy/java-course-template/main/build.gradle.kts)：source/test 布局、JUnit platform 和失败输出；main 是阅读入口，发布必须固定 commit
- [JetBrains Academy 插件与作者指南入口](https://plugins.jetbrains.com/plugin/10081-jetbrains-academy/docs/educator-start-guide.html)：插件页面；本次网页抓取无法完整取得交互式指南正文，因此菜单名称、IDE 兼容范围与导入细节仍需插件内实测
- [Gradle 兼容矩阵](https://docs.gradle.org/current/userguide/compatibility.html)、[依赖锁定](https://docs.gradle.org/current/userguide/dependency_locking.html)：构建/JVM 兼容与可重复依赖

### Java 与 Spring

- [Java 21 HashMap API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/HashMap.html)：公共合同、迭代顺序与 fail-fast 边界；首包 Java 17 仍需对应版本文档/源码
- [Java 21 并发包](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/package-summary.html)：并发工具和 memory consistency 说明
- [OpenJDK 21 Updates 源码库](https://github.com/openjdk/jdk21u)：后续对照课的官方源码入口，不用默认分支作为发布锚点
- [JDK 25 文档](https://docs.oracle.com/en/java/javase/25/)、[语言变化表](https://docs.oracle.com/en/java/javase/25/language/java-language-changes-summary.html)：版本化语言/工具/VM 说明
- [Spring Framework 参考文档](https://docs.spring.io/spring-framework/reference/)、[声明式事务注解](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/annotations.html)：IoC、AOP、MVC、事务与代理边界；正式任务切到对应 Framework 版本
- [Boot 3.5 要求](https://docs.spring.io/spring-boot/3.5/system-requirements.html)、[Boot 当前要求](https://docs.spring.io/spring-boot/system-requirements.html)：各线对应的 Java、Framework、Gradle/容器范围

### 数据 消息与 RPC

- [MySQL 8.4 InnoDB 多版本机制](https://dev.mysql.com/doc/refman/8.4/en/innodb-multi-versioning.html)：MVCC/undo 入口；实际隔离现象需配真实 SQL 时序
- [Redis 分布式锁](https://redis.io/docs/latest/develop/use/patterns/distributed-locks/)：锁安全、租约与故障假设；不据此宣称某方案无条件强一致
- [Kafka 4.1 设计文档](https://kafka.apache.org/41/design/design/)：分区、日志、消费与交付语义；课程所选其他版本需对照对应文档
- [RocketMQ 事务消息](https://rocketmq.apache.org/docs/featureBehavior/04transactionmessage/)：半消息、事务状态与回查边界
- [gRPC deadline](https://grpc.io/docs/guides/deadlines/)：预算传播与超时/取消设计
- [Dubbo 官方文档](https://dubbo.apache.org/en/overview/)：版本化架构、协议与服务治理

### 基础设施 观测与 Go

- [Docker Compose 文档](https://docs.docker.com/compose/)：多容器实验生命周期
- [Kubernetes 概念](https://kubernetes.io/docs/concepts/)：工作负载、网络、存储、安全与资源；发布选择与实际集群一致的版本文档
- [Istio 文档](https://istio.io/latest/docs/)：流量、安全与不同数据平面模式；latest 仅阅读入口
- [Elastic Stack 设置](https://www.elastic.co/docs/deploy-manage/stack-settings)：ELK 组件配置与部署文档入口
- [SkyWalking 文档](https://skywalking.apache.org/docs/)：Java agent、OAP、UI 与存储组件分开查版本
- [Go 官方文档](https://go.dev/doc/)、[Go 发布记录](https://go.dev/doc/devel/release)：语言、工具链、并发、数据库、诊断与版本历史

## 仍待验证的事项与停止条件

1. 云端完整 JDK 是否已安装、编译器与 source archive 是否可用；未经许可不绕过安装限制
2. IDEA 2026.1.5 actual build 与 Academy 插件匹配；能加载插件不是全部课程特性已验证
3. 12-task 首包的作者解、学生起点、负例、CLI 与 IDE 各自的结果；测试集是否存在漏检
4. 官方插件预览/归档/重新导入；普通 ZIP 打包不能自动称为 Academy 可导入课程
5. 真实源码版本与二进制对应；首包当前注释/链接不等于调试证据齐备
6. 各基础设施组合的云端资源预算、镜像架构、可重建/清理与故障安全
7. Go 在目标 Academy 插件的作者/检查支持；未证实前保留原生 Go 工程路线

无法验证时保留明确状态并继续不依赖它的教案/测试设计，不把云端制作任务擅自转移到用户 Mac、不降低完整课程范围，也不用估计值冒充实验结果。
