# C14 后端综合项目：订单、库存与可恢复消息

这是完整 V1 中的五阶段综合项目课程，不代表整套 V1 已验收。前置知识对应 C00–C10；每节自带完整依赖和标准答案，不要求复制前一节尚未完成的代码。学员编写后端，中文前端已预置。

## 先确认依赖

- 完整 **JDK 21**，编译器严格 `--release 21`。本地云端实测版本记录见中文阶段报告；CI用Temurin21并打印具体补丁
- Gradle Wrapper **8.10.2**，官方发行包SHA-256已在wrapper.properties固定
- Spring Boot **3.5.16** / Spring Framework **6.2.19**；Kafka client **3.9.1**、Jedis **5.2.0**、gRPC **1.71.0**、protobuf/protoc **4.29.0**、MySQL Connector/J **9.2.0**、Testcontainers **1.20.6**
- 真实集成需要Docker Engine或Docker Desktop与Compose V2；Python3用于校验和脚本。普通学习不需要Node
- 镜像只读仓库 `infra/versions.env`；独立作者工程的 `shared/versions.env` 由 `authoring/prepare_export.py` 生成，SHA在旁边，不能手改第二份版本

课程使用一个MySQL实例的不同表和独立事务、单Kafka broker及一个Redis，减轻课堂资源负担。项目提供跨进程RPC部署与重复/未知窗口验证，不证明跨可用区容灾。请为Java与中间件预留约3–5GB可用内存及镜像/持久卷磁盘空间，实际消耗以Docker测量为准。

## 最短启动路径

在完整源码仓库的本课程根执行：

```bash
java -version
bash ./gradlew --version
bash ./gradlew test
bash scripts/course.sh doctor
bash scripts/course.sh start
python3 scripts/check.py
bash scripts/course.sh stop
```

打开 `http://127.0.0.1:8088`。默认使用05-defense完整作者检查点；练第二节时设置 `CAPSTONE_STAGE=02-reliability` 再start。为避免对已有数据混用不同学习实现，切换检查点前stop；不提供删除数据的“快速重置”。可通过 `CAPSTONE_HTTP_PORT` 换本机端口。

start会编译应用分发目录，并启动独占Compose项目。stop只停止这个项目，MySQL/Redis/Kafka卷均保留。脚本没有广泛pkill、没有删除卷、没有自动执行schema迁移。第一次运行需要下载固定依赖与镜像。数据库凭据只用于隔离课堂容器，HTTP仅绑定本机回环，不承诺生产认证。

## 五个独立检查点

| 阶段 | 学员实现 | 完整产物与失败证据 |
|---|---|---|
| C14-01 | OrderRules验证、重复意图和取消状态 | 数量/身份边界、状态机、容量与故障模型 |
| C14-02 | OrderService下单与取消事务 | 唯一身份、条件扣减、同事务outbox、缓存回源和并发不超卖 |
| C14-03 | DeliveryFlow的发布/消费确认顺序 | Kafka→gRPC→inbox/投影，四个未知窗口与重放 |
| C14-04 | RecoveryPolicy的就绪和降级决策 | Compose、健康、数据重启保留、限流与完整事故记录 |
| C14-05 | Audit库存守恒和投影一致性 | 随机新变体、盲测题库、2/5/15分钟答辩 |

每节task.md含企业用途、ASCII图、完整操作顺序、三层提示、源码符号/断点、四层面试问题以及完整公开标准解。全部调用方和测试可见。`reference/`为其他阶段已完成依赖；Gradle明确排除本节目标类的参考版本，只编译你的版本。

## 完整项目结构

```text
backend-capstone/
  app/src/main/java/labs/capstone/
    BootApp.java                  HTTP、错误合同与业务就绪
    Runtime.java                  页面/重放完整调用方
    Database.java                 Hikari池、DDL与一致性审计快照
    DeliveryStore.java            接收端inbox与投影原子提交
    DeliveryRpc.java / DeliveryMain.java   真正独立gRPC进程
    Broker.java / OrderCache.java  真Kafka客户端与Redis缓存
    Model.java / Config.java / Json.java / Exercise.java
    Usage.java / HealthMain.java   可见CLI与容器探针
    protocol/                     由公开proto固定工具生成
  app/src/main/resources/static/index.html  完整中文前端
  reference/src/labs/capstone/     五个公开标准实现
  capstone/stages/
    01-contract/ ... 05-defense/   每节src、test、integration-test、题面、YAML
  shared/test/                    H2控制流测试支撑，不能替代MySQL
  shared/integration-test/         真实容器与恢复夹具
  shared/versions.env + versions.sha256   自动生成的镜像快照
  protocol/delivery.proto         可版本化gRPC合同
  scripts/                        启停、真实HTTP、浏览器、抽题
  docs/                           源码、故障、盲测与前端说明
  authoring/                      元数据和正反解验证
  compose.yaml                    只引用唯一镜像台账
  build.gradle / settings.gradle / gradle/ / gradlew
  中文阶段报告.md
```

订单HTTP与配送RPC为两个Java进程。教学部署共享MySQL实例，但一次订单事务不跨RPC；每个服务的持久化确认均可能与网络应答分离。Redis是5秒TTL的最终一致查询缓存。`fresh=true`、库存更新和审计均读MySQL。投影只是可取消的配送计划，未接真实支付或实物发货。

```text
中文页面 -> Spring Boot -> [订单 + 库存 + outbox] MySQL事务
                              |
                      Kafka确认后标记发布
                              |
                  Kafka消费 -> gRPC独立进程
                              |
                     [inbox + 配送读模型]事务
                              |
                         提交下一条位点
```

## 可见接口与验证命令

- GET `/api/dashboard`：同一MySQL快照中的订单、库存、投影及审计；附各依赖健康、待发事件和投影落后数
- POST `/api/orders`：`{"requestId":"demo-1","sku":"book","quantity":2}`，同号同参数返回原状态，同号改参数409
- POST `/api/orders/demo-1/cancel`：释放一次库存并写v2事件；重复取消不重复释放
- GET `/api/orders/demo-1?fresh=true`：直接读MySQL；不带fresh使用TTL五秒的缓存；晚回填可延长相对提交的陈旧窗口
- POST `/api/replay`：一个有界批次发布与消费；页面不并发触发，失败后保留记录重试
- GET `/api/health` 与 `/api/ready`：分别观察四项依赖以及数据库/积压就绪；不是跨服务一致快照

```bash
bash ./gradlew :02-reliability:test :02-reliability:usage
bash ./gradlew integrationTest
python3 authoring/validate_course.py
python3 scripts/draw-defense.py
```

快测与H2只验证纯业务和控制流。真实MySQL锁、排序规则、Kafka日志、RPC和恢复必须看integrationTest；真实浏览器另有CI步骤。任何尚未运行的层级都不能由其他绿色结果推断。容器集成中的RPC客户端与服务端在同一测试JVM，以真实HTTP/2通信；Compose才运行两个独立Java进程，scripts/recovery-check.py用本项目应用进程SIGKILL与重建验证跨进程恢复。

## Academy与源码CLI是两个入口

本目录是Academy作者工程；标准答案和测试不会被人为隐藏。官方Academy导出器会剔除Wrapper脚本/JAR等构建文件，普通源码ZIP也不是官方学习归档。源码CLI使用本目录Wrapper；官方归档导入后的Check/Run由插件提供Gradle上下文。

Check执行当前模块公开快测；Run执行Usage的无容器领域调用。完整网页与外部服务使用源码CLI的Compose入口，不能把无容器Run当作真实中间件验收。正式官方ZIP必须在对应IDEA/Academy中导出、重新导入、Check/Run/重置后验证，再单独发布；本课程报告会明确这一步的状态。

本课程仅做C14 V1：不含Kubernetes、Istio、ELK、SkyWalking或企业IAM课程，相关扩展仍属V2。
