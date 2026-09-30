# Backend Interview Labs

面向 Java 后端面试的中文动手课程。以 JetBrains Academy 课程为学习入口，配合独立基础设施实验。

## 从这里开始

- [完整课程目录：16 门课程、113 个实验单元](docs/curriculum/01-full-curriculum.md)
- [独立的 14 天面试优先路线](docs/curriculum/02-fourteen-day-priority-route.md)
- [课程制作与验收标准](docs/curriculum/03-authoring-and-assessment.md)
- [完整试点规格与首包映射](docs/curriculum/04-pilot-detailed-design.md)
- [版本与官方来源](docs/curriculum/05-versioning-and-sources.md)
- [Java 编码恢复与集合：首批 12 道练习](courses/java-recovery-collections/README.md)

[查看各课程制作与验证进度](docs/curriculum/09-v1-progress.md)

## 当前交付状态

当前已有 Java 基础与集合、JUC、JVM、Spring/Boot、MySQL、Redis、Kafka/RocketMQ 的作者课程实现，分布式与综合项目正在完善。**V1 仍未整体验收完成**，各模块真实测试与界面验证范围见下方报告。

内部试点已完成官方导出和干净导入，并对第 1 题实测错误答案、正确答案及重置；该结果不能外推为全部课程、全部题目已完成 Academy 验收。

首包包含金额累计、ID 解析、泛型有界栈、稳定去重、不可变键、Top-K、快照、安全删除、动态数组、哈希索引与扩容、LRU、近期 ID 窗口。完整范围不会因为面试时间临近被删减；两周路线只调整练习顺序。

统一 **JDK 21**，目标 IDEA 版本为 **2026.1.5**。开发和验收在云端进行，不要求占用个人 Mac 的开发空间。实际学习可以使用自己的 IDEA；重型实验环境另行选择。

## 注意作者答案与学习者练习的区别

课程源码里的答案用于作者验证；直接运行作者工程通常应通过测试。先阅读首包 README，通过 Academy 预览或显式生成普通 Gradle 学习者副本再练习。教师解析在 `instructor/java-pilot/`，可以按需对照阅读；每题也提供标准答案、调用示例和全部测试。

普通源码 ZIP 不等于 Academy 导出的课程归档。发布学习者包前需实际验证：预览、错误和正确答案检查、提示、重置、导出、干净导入及答案泄漏检查。

## 验证

- [当前验证记录](courses/java-recovery-collections/authoring/VERIFICATION.md)
- [CI 配置](.github/workflows/java-pilot.yml)：完整 JDK 21、Gradle、元数据及有限错误变体验证

只把实际执行通过的检查标记为通过。命令行编译或测试成功不等于 IDEA UI 验收成功；观察与源码理解题还需要证据与口述复盘。

## 分版范围

V1 必须完成 Java、Java 框架、分布式、数据库与缓存、消息队列，包含必要前端及 Docker 支撑环境。当前 12 题只是内部试点，不代表 V1 完成。V2 为云原生、可观测和 IAM/LDAP/Keycloak 等企业身份工程；Go 单列待排期。

## 阶段报告

- [Java 编码恢复与集合：结构、逐题内容和验证证据](courses/java-recovery-collections/阶段报告.md)
- [共享 Docker 环境：设计、使用示例与实际 CI 结果](docs/environment/phase-report.md)
- [Java 基础与集合：完整 C00/C01 16 单元](courses/java-foundations/中文阶段报告.md)
- [JUC 并发：8 单元与正确性验证](courses/java-concurrency/阶段报告.md)
- [JVM 与现代 Java：7 单元](courses/java-jvm/阶段报告.md)
- [Spring/Boot 应用与源码：14 阶段](courses/java-frameworks/中文阶段报告.md)
- [MySQL 与 Redis：真实数据库验收](courses/data-storage/中文阶段报告.md)
- [消息队列验证与已知问题](courses/messaging/验证报告.md)
- [分布式服务与一致性：8 单元](courses/distributed-systems/中文阶段报告.md)
- [IDEA/Academy 实际界面验收及覆盖边界](docs/界面验收报告.md)
- [V1 / V2 发布验收矩阵](docs/curriculum/08-release-plan.md)

报告中的完成范围与整个 V1 分开；每个较大模块会随代码提交独立报告，供逐步评审。
