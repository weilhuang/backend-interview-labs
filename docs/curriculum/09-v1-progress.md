# V1 制作与验证进度

更新：2026-09-30。此表是阶段性工程证据，不是学习者已掌握或 V1 已发布的声明。完整范围仍以 [分版验收矩阵](08-release-plan.md) 为准，不因两周面试路线缩减。

## 如何评审

每门报告列出章节、讲解深度、完整调用方、测试、标准解、源码入口和已知边界。建议先看阶段报告，再抽读一节 task.md 和对应公开测试；对深度、节奏或案例提出调整。源码中的作者答案能通过测试，不代表学习者独立完成。

| 课程 | 内容实现 | 已取得真实验证 | 仍需完成 |
|---|---|---|---|
| C00/C01 Java 基础与集合 | 16 单元，52 公开测试，16 调用端，16 替代解，33 错误变体 | 云端真实 JDK21/Gradle；HashMap JDI 分支；JMH 短探索 | CI 已通过；官方导出与干净导入，三类题 Check/Reset 抽检通过；其余逐题界面与独立试学未验 |
| C02 JUC | 8 单元 | JDK21/Gradle 与 CI；38 测试、8 替代解、20 变体；官方导出、两次干净导入与首题 Check/Reset 抽检通过 | 其余逐题 GUI 与独立试学 |
| C03 JVM/现代 Java | 7 单元 | JDK21/Gradle 与 CI；30 测试、7 替代解、19 变体；官方导出、两次干净导入与首题 Check/Reset 抽检通过 | 其余逐题 GUI 与独立试学 |
| C04/C05 Spring/Boot | 14 阶段，预置中文页面 | 真实构建、MySQL 集成、14 调用端、32 负例 | 11 项真实浏览器断言与桌面/窄屏截图已通过；Academy 发行验收待做 |
| C06 MySQL | 7 单元 | 40 测试，其中 23 项真实服务测试，CI 通过 | 独立包同源台账已验证；Academy 发行验收待做 |
| C07 Redis | 7 单元 | 36 测试，其中 19 项真实服务测试，CI 通过 | 独立包同源台账已验证；Academy 发行验收待做 |
| C08 Kafka | 6 单元 | 真实 Broker/数据库、三副本故障路径；与 RocketMQ 合计 44 项测试全过，其中 17 项真实服务测试 | Academy 发行验收与独立试学 |
| C09 RocketMQ | 6 单元 | QueryRoute、双组收发、重试/顺序/事务与已写段恢复全部通过；MQ 合计 44 项，零失败/错误/跳过 | Academy 发行验收与独立试学 |
| C10 分布式 | 8 单元，真实 gRPC/Dubbo/注册发现 | 44 项本机/RPC、9 项真实服务测试全过；25 变体；8 CLI | 同键死锁、重启端口与XA恢复已在真实CI复验通过；Academy、macOS与独立试学待验 |
| C14 综合项目 | 5 阶段已制作，完整订单/库存/outbox/inbox/缓存/RPC 与中文前端 | 35 快测＋5 真实服务测试；5 调用端、5 组正反解、11 脚本边界；Compose 独立进程恢复与 320/390/800/801/1440px 浏览器检查全过 | Academy 发行验收、macOS 与独立试学 |

内部 12 题试点不计入上述完整课程数量。试点官方导出和两次干净导入、第 1 题错误/正确/重置已实测；不能外推到其他题和其他课程，详见 [界面验收报告](../界面验收报告.md)。

C02 本轮改进了公开并发测试的异常传播，使学习者 TODO 失败能直接暴露而非被次生超时掩盖。已交付的官方 ZIP 保持原样；其 GUI 抽检记录仍只代表原包，新源码发行包需另行导出和比对，详见 [质量增强阶段报告](../quality/中文阶段报告.md)。

## 当前可复核证据

下面九条运行均对应提交 `1fb27d8885bf1eb62b112d2e15f5478becf697fa`，结论为成功。历史失败保留为排错记录，不表示修复后的版本仍失败。

- [MySQL/Redis 全部真实服务 CI](https://github.com/weilhuang/backend-interview-labs/actions/runs/36746760864)
- [Kafka/RocketMQ 完整 44 项与课程正反解通过](https://github.com/weilhuang/backend-interview-labs/actions/runs/36746760650)
- [框架后端、MySQL、调用端、负例与真实中文浏览器通过](https://github.com/weilhuang/backend-interview-labs/actions/runs/36746760801)
- [完整 Java 基础课程与 JDI 通过](https://github.com/weilhuang/backend-interview-labs/actions/runs/36746760767)
- [JUC/JVM 构建、正反解及诊断通过](https://github.com/weilhuang/backend-interview-labs/actions/runs/36746760776)
- [内部试点通过](https://github.com/weilhuang/backend-interview-labs/actions/runs/36746760613)
- [C10 全部真实服务与正反解通过](https://github.com/weilhuang/backend-interview-labs/actions/runs/36746760872)
- [C14 全部测试、独立进程恢复及五种视口通过](https://github.com/weilhuang/backend-interview-labs/actions/runs/36746760606)
- [共享环境真实读写、Rocket 持久化与 JDK21 构建通过](https://github.com/weilhuang/backend-interview-labs/actions/runs/36746760630)

已有通过仅对应记录中的版本。新质量门禁和 CI 调度改动必须在新提交上验证，不能沿用旧提交的全绿结论；运行中、取消、未执行与失败分别记录，不视为成功。私人仓库的 Actions 计费与 ChatGPT 套餐不同，当前没有读取账户剩余额度；上述运行确实执行并通过，不能将先前测试失败归因于额度不足。

## 发布前重点

测试层次见 [Academy 质量门禁说明](../quality/academy-quality-gates.md)，本轮实测与缺口见 [中文阶段报告](../quality/中文阶段报告.md)，执行策略见 [CI 使用指南](../ci.md)。新门禁的本地验证与 GitHub 运行结果分别记录，不互相代替。

1. 补齐跨课程学习者生命周期、归档完整性与独立占位区测试，并验证新的 CI 调度不会漏验或产生假绿
2. 各课程独立归档统一镜像台账和辅助镜像，提供可复建环境
3. 按课程结构逐项做 Academy 官方导出、干净导入、Check、Reset 与可见性检查
4. 交付源码、官方归档、版本/已知问题和中文操作文档，邀请实际试学反馈

开发未使用用户 Mac；Linux 云端与 CI 通过不代表 macOS/Apple Silicon 已实测。JDK 主线固定 21，容器按需启动，不要求同时运行所有依赖。
