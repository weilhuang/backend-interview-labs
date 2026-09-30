# V1 制作与验证进度

更新：2026-09-30。此表是阶段性工程证据，不是学习者已掌握或 V1 已发布的声明。完整范围仍以 [分版验收矩阵](08-release-plan.md) 为准，不因两周面试路线缩减。

## 如何评审

每门报告列出章节、讲解深度、完整调用方、测试、标准解、源码入口和已知边界。建议先看阶段报告，再抽读一节 task.md 和对应公开测试；对深度、节奏或案例提出调整。源码中的作者答案能通过测试，不代表学习者独立完成。

| 课程 | 内容实现 | 已取得真实验证 | 仍需完成 |
|---|---|---|---|
| C00/C01 Java 基础与集合 | 16 单元，52 公开测试，16 调用端，16 替代解，33 错误变体 | 云端真实 JDK21/Gradle；HashMap JDI 分支；JMH 短探索 | CI 已通过；官方导出与干净导入，三类题 Check/Reset 抽检通过；其余逐题界面与独立试学未验 |
| C02 JUC | 8 单元 | JDK21/Gradle 与 CI；38 测试、8 替代解、20 变体 | Academy 发行验收、独立试学 |
| C03 JVM/现代 Java | 7 单元 | JDK21/Gradle 与 CI；30 测试、7 替代解、19 变体 | Academy 发行验收、独立试学 |
| C04/C05 Spring/Boot | 14 阶段，预置中文页面 | 真实构建、MySQL 集成、14 调用端、32 负例 | 11 项真实浏览器断言与桌面/窄屏截图已通过；Academy 发行验收待做 |
| C06 MySQL | 7 单元 | 40 测试，其中 23 项真实服务测试，CI 通过 | 独立包台账与 Academy 发行验收 |
| C07 Redis | 7 单元 | 36 测试，其中 19 项真实服务测试，CI 通过 | 独立包台账与 Academy 发行验收 |
| C08 Kafka | 6 单元 | 6 套真实 Broker/数据库测试，包括三副本故障路径，已有 CI 通过记录 | 与 RocketMQ 修复后的整体回归；Academy 验收 |
| C09 RocketMQ | 6 单元 | 纯逻辑、编译、静态合同验证；实际启动及管理 RPC 已前进至成功 | 真实 QueryRoute 与双消费组收发已过；最新协议就绪门禁、回滚隔离及存储路径修复待完整CI回归 |
| C10 分布式 | 8 单元，真实 gRPC/Dubbo/注册发现 | 原工程及独立源码包各 38 测试；24 变体；8 CLI | 同键死锁、重启端口与XA恢复已在真实CI复验通过；Academy、macOS与独立试学待验 |
| C14 综合项目 | 5 阶段已制作，完整订单/库存/outbox/inbox/缓存/RPC 与中文前端 | 35 快测、5 调用端、5 组正反解、11 脚本边界；独立代码审查已补关键回归 | 首轮真实容器测试发现Kafka Admin超时配置冲突，已加回归并修正；容器/Compose/浏览器复验与Academy待验 |

内部 12 题试点不计入上述完整课程数量。试点官方导出和两次干净导入、第 1 题错误/正确/重置已实测；不能外推到其他题和其他课程，详见 [界面验收报告](../界面验收报告.md)。

## 当前可复核证据

- [MySQL/Redis 全部真实服务 CI](https://github.com/weilhuang/backend-interview-labs/actions/runs/36729402341)
- [Kafka 通过、RocketMQ 尚失败的历史运行](https://github.com/weilhuang/backend-interview-labs/actions/runs/36726367053)：需查看各套结果，不能把整个红色运行称为全绿
- [RocketMQ 消费者建立失败的最新证据](https://github.com/weilhuang/backend-interview-labs/actions/runs/36731386884)
- [框架后端、MySQL、调用端、负例与真实中文浏览器全部通过](https://github.com/weilhuang/backend-interview-labs/actions/runs/36735424856)
- [完整 Java 基础课程 CI 与 JDI 通过](https://github.com/weilhuang/backend-interview-labs/actions/runs/36733937766)
- [C10 全部真实服务与正反解通过](https://github.com/weilhuang/backend-interview-labs/actions/runs/36738093982)
- [共享环境全部真实读写、Rocket持久化与JDK21构建通过](https://github.com/weilhuang/backend-interview-labs/actions/runs/36738093788)

同一 PR 后续提交可能重跑所有课程，已有通过仅对应记录中的版本；修复后的最新版本仍需回归。运行中、取消、未执行与失败分别记录，不视为成功。

## 发布前重点

1. 完成 RocketMQ 最新协议门禁与完整套件回归，以及 C14 容器/进程恢复/前端联调
2. 各课程独立归档统一镜像台账和辅助镜像，提供可复建环境
3. 按课程结构逐项做 Academy 官方导出、干净导入、Check、Reset 与可见性检查
4. 交付源码、官方归档、版本/已知问题和中文操作文档，邀请实际试学反馈

开发未使用用户 Mac；Linux 云端与 CI 通过不代表 macOS/Apple Silicon 已实测。JDK 主线固定 21，容器按需启动，不要求同时运行所有依赖。
