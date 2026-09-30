# Backend Interview Labs

面向 Java 后端面试的中文动手课程。以 JetBrains Academy 课程为学习入口，配合独立基础设施实验。

## 从这里开始

- [完整课程目录：16 门课程、113 个实验单元](docs/curriculum/01-full-curriculum.md)
- [独立的 14 天面试优先路线](docs/curriculum/02-fourteen-day-priority-route.md)
- [课程制作与验收标准](docs/curriculum/03-authoring-and-assessment.md)
- [完整试点规格与首包映射](docs/curriculum/04-pilot-detailed-design.md)
- [版本与官方来源](docs/curriculum/05-versioning-and-sources.md)
- [Java 编码恢复与集合：首批 12 道练习](courses/java-recovery-collections/README.md)

## 当前交付状态

完整课程目录已设计，但目录中的未来课程不等于已实现。当前实现是 Java 编码恢复与集合课程的 **author-mode pilot**，不是已验收的 Academy 学习者课程包。

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
- [V1 / V2 发布验收矩阵](docs/curriculum/08-release-plan.md)

报告中的完成范围与整个 V1 分开；每个较大模块会随代码提交独立报告，供逐步评审。
