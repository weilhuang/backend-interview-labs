# Kafka 与 RocketMQ 消息可靠性实验室

本目录提供 C08 与 C09 两门课程的完整作者工程。不是两周速成删减版，也不是完整 V1 发布结论。完整 V1 范围见仓库 docs/curriculum/08-release-plan.md；本包的 Docker/IDE 待验证状态见[验证报告](验证报告.md)。

## 版本、环境与开课自检

| 项目 | 固定基线与实际状态 |
|---|---|
| 课程 | 0.2.0，入门→进阶→高级，各六节，完整映射原目录 |
| JDK | Eclipse Temurin 21.0.12.1+1，目标与测试 JVM 为21；云端严格编译已执行 |
| 第三方服务内部JVM | 以官方镜像为准；RocketMQ5.3.2镜像发布元数据显示JDK8u442，不宣称内部JVM为21。课程业务源码、客户端和测试统一21 |
| Gradle / JUnit | Wrapper 8.10.2（SHA256已锁）；JUnit5.11.4 / Platform1.11.4 |
| Kafka | apache/kafka:3.9.1；Java客户端3.9.1；KRaft经典消费组协议 |
| RocketMQ | apache/rocketmq:5.3.2；Java gRPC SDK5.0.8；NameServer+Broker+Proxy，管理CLI内部仍使用官方Remoting工具，不与应用gRPC API混讲 |
| Testcontainers | 1.20.6；Kafka使用org.testcontainers.kafka.KafkaContainer；Ryuk/启动检查辅助镜像也必须经共享台账读取 |
| 嵌入式快速检查 | H2 2.3.232仅检查本地JDBC控制流；不替代MySQL真实语义 |
| MySQL / JDBC | 共享MYSQL_IMAGE；Connector/J9.2.0；inbox/outbox/本地事务状态真实SQL |
| Docker / Compose | 必须有本地Docker Engine；本云端没有daemon，因此未声称具体Engine/Compose组合通过 |
| 镜像来源 | 唯一真源../../infra/versions.env；不在Java写另一个tag，不宣称未核实digest或架构支持 |
| IDE / Academy | JDK_21与UTF-16占位元数据已提供；本包IDE预览/重置/导出/重新导入尚未验证 |
| 前端 | 不需要；本课以完整Java调用端、测试和CLI管理命令完成可观察闭环 |
| 资源 | 单broker每JVM堆256–512MiB；三Kafka副本实验额外需要资源，建议Docker至少4GiB，未实测容量 |
| 网络与安全 | 下载依赖需联网；课堂临时容器明文无认证，仅在本地隔离测试，禁止公网和真实账号数据 |

```bash
# 从仓库根检查共享环境（doctor命令实际由共享脚本提供）
./scripts/lab.sh doctor
cd courses/messaging
./gradlew test                         # 仅快速单元用例
./gradlew test -PwithDocker             # 完整真实broker与MySQL用例，一条命令自动启动/检查/关闭
./gradlew :kafka-01-contract:run        # 打印调用参数
```

不会因为没有 Docker 就自动跳过容器测试并报全绿。真实流程由Testcontainers创建随机资源、等待健康/协议响应、执行断言、关闭资源；失败要保留Gradle的报告和broker日志。不要使用docker system prune清理全机器。

## 教学顺序与原目录映射

| 原单元 | 本包目录 | 核心产物 |
|---|---|---|
| C08-01 | kafka/01-contract | 同key分区、真实单分区顺序、消费组位点契约 |
| C08-02 | kafka/02-producer | acks/幂等配置、业务重复send的反例 |
| C08-03 | kafka/03-inbox | MySQL inbox与业务同事务、提交窗口崩溃/重放 |
| C08-04 | kafka/04-rebalance | 真实扩容与分区移交、所有权、lag |
| C08-05 | kafka/05-transactions | Kafka内输出+位点事务、abort/read_committed边界 |
| C08-06 | kafka/06-recovery | 三副本leader停止、outbox重发、毒消息隔离、schema |
| C09-01 | rocketmq/01-routing | gRPC主线、tag/key/组、随机映射Proxy端点 |
| C09-02 | rocketmq/02-retry | 真实未确认重投、有界重试策略、应用隔离队列 |
| C09-03 | rocketmq/03-order-delay | FIFO消息组、DELAY真实投递、迟到取消状态机 |
| C09-04 | rocketmq/04-transactions | 本地MySQL事务、半消息、生产者重建后真实回查、消费幂等 |
| C09-05 | rocketmq/05-storage | CommitLog文件、SYNC_FLUSH、容器停止/恢复 |
| C09-06 | rocketmq/06-comparison | 两种真实broker的相同事件重复与业务不变量对照 |

每节 practice/task.md 含企业问题、概念图、操作步骤、源码固定tag/符号、完整源码与调用端、标准解、四道机制/场景问答、进一步追问及独立迁移。所有 src/ 与 test/ 对学习者可见；support公共代码也随课程可见。

## RocketMQ 5端点与配置特别说明

5.x gRPC客户端连接Proxy，不直接连接NameServer或Broker。RocketMQ5.3.2的LOCAL模式（mqbroker --enable-proxy）在LocalTopicRouteService中忽略请求端点，返回brokerIP1加固定gRPC端口；即使设置useEndpointPortFromRequest=true，也不能支持本实验的随机宿主端口映射。旧方案只检查RouteActivity而漏看LOCAL后续分支，真实CI已在客户端建立阶段失败。

本夹具改为同一临时容器内分别启动NameServer、Broker和CLUSTER Proxy，Proxy使用mqproxy -pm cluster，并配置namesrvAddr、proxyMode=CLUSTER、useEndpointPortFromRequest=true。ClusterTopicRouteService实际沿用请求地址；仍只暴露8081的随机宿主端口，NameServer和Broker管理调用在容器内执行。routing真实测试先断言QueryRoute返回地址等于随机宿主端点，再要求两个消费组成功收到同一条消息。源代码推导、严格编译和无容器单测已通过，此修正仍待新的真实CI及Mac/Linux动态验证，不能仅凭启动或管理命令成功验收。

容器总预算仍为1.5GiB/2CPU：NameServer堆64–128MiB、Broker堆256–512MiB、独立Proxy堆128–256MiB；各自直接内存上界为32/128/64MiB。监督脚本检查三个进程，清理前保留有界Proxy/Broker文件日志及容器状态，包括客户端失败但容器仍在运行的情况。

主题按NORMAL、FIFO、DELAY、TRANSACTION显式创建，避免用普通主题发送事务或顺序消息。各组独立随机命名；实验最后关闭容器，临时写层由Testcontainers清理。默认SYNC_FLUSH并不提供多副本容灾，不能从一次重启读到数据宣称任意故障零丢失。

## 使用与答案

作者工程中的Lab.java就是可执行标准解。Academy占位生成起点是throw UnsupportedOperationException("TODO…")；不是把未完成代码放在作者分支让正确测试失败。先用CLI确认依赖，再在IDE预览中编码、Check、Reset。必须另外验证导出及干净导入，普通源码ZIP不能冒充Academy发行归档。

Kafka事务只覆盖Kafka内的输出与消费位点。RocketMQ事务消息协调本地事务事实与消息投递，不能原子完成下游数据库/HTTP副作用。持久幂等、保留策略和恢复操作始终是业务系统责任。

## 独立课程与学生起点

```bash
python -m pip install -r authoring/requirements.txt
python authoring/validate_course.py
python authoring/materialize_course.py --course kafka --output build/独立Kafka作者项目
python authoring/materialize_course.py --course rocketmq --output build/独立RocketMQ学生项目 --learner
```

两门课程可分别生成独立项目目录，只保留对应六节。共享镜像从原仓库唯一台账生成只读发布快照，附SHA256来源记录；它不是第二份手工维护的版本表。项目与普通源码ZIP不冒充官方Academy发行归档，IDE预览/导出/干净导入仍需分别验证。

## 作者侧严格检查

```bash
python authoring/download_compile_dependencies.py
python authoring/verify.py --jdk "$JAVA_HOME"
python authoring/check_sources.py
```

verify.py实际编译全部Java与真实服务测试代码，运行无Docker单测，再逐节编译学生空实现和固定错误变体，要求被同一公开测试拒绝，并恢复作者解重新回归。它没有启动Docker。源码证据固定到官方提交，不是只给易漂移的分支链接。

若Docker Engine的新版本拒绝旧客户端API，可在实际核对docker version的Server API范围后加入-PdockerApiVersion=1.44（课程CI使用这个显式设置）。它只设置测试JVM的docker-java客户端请求版本，不改宿主机安全或网络配置；仍须运行真实容器才能确认当前组合。

共享台账必须包含TESTCONTAINERS_RYUK_IMAGE与TESTCONTAINERS_TINY_IMAGE。若报缺键，先由共享环境维护者登记Testcontainers1.20.6对应的固定辅助镜像，再重新生成独立课程快照；课程不会偷偷使用另一套默认镜像或关闭Ryuk。
