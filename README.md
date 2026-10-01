# Backend Interview Labs

面向 Java 后端面试的中文动手课程。以 JetBrains Academy 课程为学习入口，配合独立基础设施实验。

## 从这里开始

- [单一 V1 Academy 课程入口：11 章节、84 任务](docs/统一课程入口.md)
- [统一 V1 阶段报告与未完成门禁](docs/统一V1阶段报告.md)
- [Actions 官方课程产物与下载边界](docs/Actions下载官方Academy课程.md)

- [完整课程目录：16 门课程、113 个实验单元](docs/curriculum/01-full-curriculum.md)
- [独立的 14 天面试优先路线](docs/curriculum/02-fourteen-day-priority-route.md)
- [课程制作与验收标准](docs/curriculum/03-authoring-and-assessment.md)
- [完整试点规格与首包映射](docs/curriculum/04-pilot-detailed-design.md)
- [版本与官方来源](docs/curriculum/05-versioning-and-sources.md)
- [Java 编码恢复与集合：首批 12 道练习](courses/java-recovery-collections/README.md)

[查看各课程制作与验证进度](docs/curriculum/09-v1-progress.md)

## 当前交付状态

截至2026-10-01，九份分课官方评审归档已在本地准备并通过离线完整性检查9/9；此前已交付七份，修订后的C10分布式与C14综合项目两份仍待新提交CI。它们是已有分课证据，本次仅发布已审源码修复和验收报告，不发布归档下载目录。**V1仍未整体验收完成**：

- [日期化质量摘要与本地归档证据](docs/quality/release-readiness-20261001.json)
- [逐课制作/原生验证矩阵](docs/curriculum/09-v1-progress.md)

当前交付方向为 **单一 Academy 课程和统一环境**，通过 GitHub Actions 提供产物。统一生成器及官方导出基础流水线已实现并通过静态检查；统一课程包含 11 章节、84 任务、136 练习区，固定 JDK 21。官方原生与真实统一 Docker 验收仍为 NOT_RUN，最终 ZIP 发布门禁保持 BLOCKED。详见[本阶段报告](docs/统一V1阶段报告.md)；普通源码 ZIP 不能替代官方课程归档。

最近完整绿基线[f5b0d49的CI](https://github.com/weilhuang/backend-interview-labs/actions/runs/36780139579)包含12个实际测试job和10课三阶段。后续已修复C10“XA未实现却原生显示Correct”和C14“参考源码重复索引”的问题，新包原生证据已补齐到下列明确范围；新构建真实Docker CI仍未运行，不能继承旧绿。发布后以[PR #1](https://github.com/weilhuang/backend-interview-labs/pull/1)对应提交的实际结果为准。

原生验收仍是代表题抽检。MySQL/Redis只有导入、IDE纯合同与Reset，没有默认Check通过；新C10的06/07已发现真实集成类，但因缺Docker失败；C14只对01完成本轮Check/Reset，五阶段IDE模型/编辑器已逐一检查。不存在全题原生验收或学习者掌握度结论。

首包包含金额累计、ID 解析、泛型有界栈、稳定去重、不可变键、Top-K、快照、安全删除、动态数组、哈希索引与扩容、LRU、近期 ID 窗口。完整范围不会因为面试时间临近被删减；两周路线只调整练习顺序。

统一 **JDK 21**，目标 IDEA 版本为 **2026.1.5**。开发和验收在云端进行，不要求占用个人 Mac 的开发空间。实际学习可以使用自己的 IDEA；重型实验环境另行选择。

## 注意作者答案与学习者练习的区别

课程源码里的答案用于作者验证；直接运行作者工程通常应通过测试。先阅读首包 README，通过 Academy 预览或显式生成普通 Gradle 学习者副本再练习。教师解析在 `instructor/java-pilot/`，可以按需对照阅读；每题也提供标准答案、调用示例和全部测试。

普通源码ZIP不等于Academy官方归档；课程源码通常带作者参考实现。通过官方课程入口导入学习者包，按题面、TODO与公开完整答案区分练习和参考。完整发布仍需逐题Check/Reset、官方导出/导入及可见性验证。

## 验证

- [分层 CI：触发范围、完整验收与资源使用](docs/ci.md)
- [Academy 质量门禁：学习者副本、逐空位测试与归档边界](docs/quality/academy-quality-gates.md)
- [质量增强阶段报告：实际覆盖、问题修复与待验项](docs/quality/中文阶段报告.md)

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
- [综合项目：订单、库存、消息与恢复五阶段](courses/backend-capstone/中文阶段报告.md)
- [IDEA/Academy 实际界面验收及覆盖边界](docs/界面验收报告.md)
- [V1 / V2 发布验收矩阵](docs/curriculum/08-release-plan.md)

报告中的完成范围与整个 V1 分开；每个较大模块会随代码提交独立报告，供逐步评审。
