# 分布式服务与一致性实验课

本课程实现完整目录C10的8个单元。学习路线从故障模型进入真实gRPC/Dubbo，再到容量治理、持久化幂等、XA/TCC/Saga和Outbox缓存读模型。课程内容和工程已制作；是否达到发布门禁必须看[中文阶段报告](中文阶段报告.md)，不能把单元绿色代替Docker联调或Academy界面验收。

## 开课前的固定版本

| 项目 | 本课基线与验证范围 |
|---|---|
| 课程 | 0.2.0，C10完整8单元，入门补课到进阶/高级故障恢复 |
| 先修 | Java并发C02、Spring服务C04、MySQL C06、Redis C07；事件链路选修Kafka C08 |
| JDK | Eclipse Temurin 21.0.12.1+1 LTS，编译目标/Gradle JVM/测试JVM均为21；准确云端输出见阶段报告 |
| 构建 | Gradle Wrapper 8.10.2，分发SHA-256固定；UTF-8；每个单元独立子项目 |
| 测试 | JUnit Jupiter 5.11.4；Testcontainers 1.20.6；H2 2.3.232仅作SQL分支合同快测 |
| RPC | gRPC Java 1.71.0；protobuf/protoc 4.29.0；grpc代码生成器1.71.0；Dubbo 3.3.6 |
| 服务发现 | Curator测试服务5.7.1，实际解析到的Curator/ZooKeeper版本由各模块gradle.lockfile固定；生产客户端Curator5.8.0，测试解析ZooKeeper3.9.2（编译配置仍含3.7.2，锁文件明确区分），真实本机ZooKeeper协议 |
| 治理库 | Resilience4j 2.3.0，真实breaker/bulkhead，令牌桶与滑动日志为明确标记的教学模型 |
| 数据客户端 | MySQL Connector/J 9.2.0；Kafka客户端3.9.1；Jedis5.2.0 |
| 其他直接依赖 | javax.annotation-api 1.3.2（仅编译生成stub）、SLF4J Simple2.0.16；全部传递依赖逐配置精确版本见各模块gradle.lockfile |
| 容器镜像 | 唯一来源仓库`infra/versions.env`：MYSQL_IMAGE、KAFKA_IMAGE、REDIS_IMAGE。当前台账MySQL8.4.7、Kafka3.9.1、Redis7.4.7；代码不复制镜像常量 |
| Docker | 单元/真实回环RPC不需要；MySQL/Kafka/Redis集成必须有Docker daemon。当前dot云端无daemon，动态集成待GitHub Ubuntu Docker CI |
| IDE与Academy | 目标IntelliJ IDEA 2026.1.5 / Academy 2026.9-2026.1-1070；本课GUI预览/Check/Reset/导出/干净导入均单独待验，不继承其他课程结果 |
| 前端 | 本课不需要图形前端；已提供两套真实RPC调用端及完整集成调用链，学习者无需制作前端 |
| 服务与资源 | 本机RPC随机回环端口；容器随机映射端口。最大并行集成为两个MySQL或MySQL+Kafka+Redis。建议至少4CPU/6GiB空闲内存，此建议不是已测最低配置 |
| 教学素材 | 全部src、Usage调用方、test、integration-test、proto、schema定义、solutions和源码固定提交公开 |

版本是可复现教学基线，不宣称当前最新安全组合。依赖升级须同时回归协议、API、镜像和课程元数据。数据库实验只使用Testcontainers隔离实例和生成的实验账号，不连接真实订单/支付/企业目录。

## 源码仓库：从第一条命令开始

```bash
cd courses/distributed-systems
./scripts/course.sh doctor
./gradlew :01-failure-model:test :01-failure-model:run
./gradlew :02-grpc:test :02-grpc:run
./gradlew :03-dubbo:test :03-dubbo:run
./gradlew test
# 以下需要真正可用的Docker；缺失时失败，不自动跳过
./gradlew integrationTest
```

Academy官方ZIP导入后使用题目Check/Run或IDE的Gradle工具窗口执行同名任务。当前官方导出会剔除gradlew、gradlew.bat与wrapper.jar；因此下文./gradlew命令仅适用于源码仓库/公开源码分发包，不能假设Academy导入目录自带Wrapper。不要要求学员靠猜测补文件。

独立包必须带`shared/versions.env`同源快照；作者的`authoring/build_distribution.py`从根台账复制并记录哈希，Academy正式导出前需在对应作者工程中登记该快照。缺少台账的ZIP不算完整可运行发行版。

`./gradlew test`包含真实回环TCP gRPC、Dubbo以及嵌入式真实ZooKeeper，另有H2 SQL合同快测；它不启动MySQL/Kafka/Redis容器。`integrationTest`是真实持久化与消息链路。第一次下载失败是环境/依赖错误，不能改测试来绕过。不要把作者本机Maven缓存作为发行依赖。

## 8个独立编码单元

| 单元 | 模块 | 核心产物 |
|---|---|---|
| C10-01 | `01-failure-model` | 调用知识状态与服务端提交分离、总预算切分、网络/CAP/PACELC边界 |
| C10-02 | `02-grpc` | proto、生成stub、Netty真实网络、两跳截止、取消/metadata/流控 |
| C10-03 | `03-dubbo` | 真实Dubbo远程接口、ZooKeeper注册发现、轮询、provider filter、读写重试差异 |
| C10-04 | `04-resilience` | 注入时钟令牌桶/滑动日志、真实熔断状态/半开探测、隔离上限 |
| C10-05 | `05-idempotency` | MySQL幂等键、持久状态、租约代次、未知结果恢复、指数抖动与总预算 |
| C10-06 | `06-transactions` | 两MySQL XA准备/落盘决策/恢复、TCC空回滚/悬挂、Saga重复/补偿恢复 |
| C10-07 | `07-outbox-cache` | 真实事务outbox、Kafka可重复发布、inbox投影、Redis版本floor和TTL |
| C10-08 | `08-capacity` | gRPC/Dubbo+MySQL库存闭环、无队列准入、容量估算、ID/分片/异地/故障预算答辩 |

模块之间仅复用明确已完成的fixture。C10-08引用C10-02/03的RPC与C10-05的存储；不要求复制前一课未完成代码。标准作者工程可直接运行，Academy占位是学习者起点。每节solutions提供完整标准实现，task.md提供编码步骤、所有练习区答案与中文解释。

## 如何学习而不只看答案

1. 读企业场景和ASCII图，先运行完整调用方
2. 从测试合同推导一个练习区，使用 `./gradlew :模块:test --tests '类名.方法名'` 逐步验证
3. 引入本节的重复/超时/并发/崩溃条件，记录持久状态和可观察结果
4. 跟踪固定源码入口，在标准答案之前写下机制推断
5. 核对solutions，解释替代实现与边界，再独立完成迁移题和口述答辩

## 完整性与故障保证

见[保证边界与故障矩阵](docs/保证边界与故障矩阵.md)、[源码路线](docs/源码路线.md)、[环境与发行](docs/环境与发行.md)。

本课不会把内存状态机称为真实分布式事务，把H2称为MySQL，或把单机测试称为异地高可用验证。XA日志、幂等记录、outbox/inbox及缓存floor都需要明确持久化/保留假设。生产安全、服务身份、TLS与证书生命周期在部署时必须完善，V2企业身份课程不改变这个责任。
