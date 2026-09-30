# 共享实验环境：按需启动，不重复下载整套中间件

> 状态：[完整共享环境 CI 36738093788](https://github.com/weilhuang/backend-interview-labs/actions/runs/36738093788) 已在 Linux amd64 实际通过 MySQL/Redis 读写与重启持久化、Kafka 收发、RocketMQ 宿主 gRPC 收发与 down/up 原消息读取，以及共享 JDK21 构建。制作容器本身没有 Docker，不使用个人 Mac；Mac/arm64 与资源峰值仍未实测。详细时间、提交及历史失败见 [验证记录](verification.md)。

课程制作、构建和验收在云端进行，不使用个人 Mac 的磁盘与计算资源。将来在 Mac 学习时可用同一入口，只开当前章节需要的服务。如果磁盘紧张，Java 基础题可以只用 IDEA + JDK 21，不必启动中间件。

## 1. 最低依赖与实测版本分开看

| 项目 | 本仓库最低/固定基线 | 本次实际验证 |
| --- | --- | --- |
| Python | 3.9+，仅标准库 | 3.12.14，脚本与测试通过 |
| Bash | 3.2+，只作入口 | 5.2.37，语法检查通过；Mac 自带 3.2 待验证 |
| Docker | Linux 容器，Engine 28.0+ | 制作容器未安装；基础 CI 实测 Engine 28.0.4 |
| Compose | 插件 v2.20.0+，不支持 v1 | 完整共享 CI 实测 2.38.2，含 RocketMQ |
| macOS/Docker Desktop | 使用 [Docker 官方当前支持的 macOS 与芯片版本](https://docs.docker.com/desktop/setup/install/mac-install/) | 未占用个人 Mac；Intel/Apple Silicon 均待实测 |
| Java | 完整 JDK **21**，构建镜像由台账锁定 | 云宿主完整 JDK21 验证读取器/新探针编译；基础 CI 已验证共享构建容器 |
| Gradle/Maven | Gradle 用各课已锁定 Wrapper；Maven 用共享镜像 | 首包使用 Gradle Wrapper；此环境入口未代替课程测试 |

最低 Engine 版本设为 28.0 是安全边界：[Docker 官方说明旧于 28.0 的版本可能允许同二层网段访问发布到 localhost 的端口](https://docs.docker.com/engine/network/port-publishing/)。仍需使用默认隔离网络，不能另开公网转发或直接路由。

Docker Desktop 是 Mac 的可选学习环境，不是课程制作前提。安装/登录/许可由使用者按官方流程确认，脚本不会安装软件、申请特权、改系统设置、开放防火墙或启动 daemon。官方的最低 4 GB 主机内存并不等于“所有实验可同时运行”。

镜像唯一来源是 [`infra/versions.env`](../../infra/versions.env)，登记 MySQL、Redis、Kafka、RocketMQ、完整 JDK 构建及 Testcontainers 辅助镜像。RocketMQ Compose 与课程 Testcontainers 读取同一 `ROCKETMQ_IMAGE`，没有增加另一种业务镜像；K8s、Istio、ELK、SkyWalking 属于后续范围。

## 2. 一条命令启动并等待健康

在仓库根目录运行；首次成功连接 Docker 后会创建 `infra/.env`，内容来自实验样例，权限为仅当前用户读写。镜像只在缺失时拉取。

```bash
# 只检查配置，不要求安装 Docker
./scripts/lab.sh verify

# 检查版本、daemon、Compose 解析、资源与占用；不会清理
./scripts/lab.sh doctor

# 默认：MySQL + Redis，等待协议级健康检查通过
./scripts/lab.sh up

# 当前章节只用一个组件时，更省资源
./scripts/lab.sh up mysql
./scripts/lab.sh up redis
./scripts/lab.sh up kafka
./scripts/lab.sh up rocketmq

# 确实需要组合时才启动；不会自动启动其他组件
./scripts/lab.sh up core kafka

# 使用相同的组件选择检查、看最近日志
./scripts/lab.sh check core
./scripts/lab.sh check kafka
./scripts/lab.sh logs kafka
./scripts/lab.sh check rocketmq
./scripts/lab.sh logs rocketmq

# 停止此项目的所有组件；保留数据、镜像和构建缓存
./scripts/lab.sh down
```

`up` 不是后台“发起即成功”：它使用 Compose `--wait`，再检查选中容器是否运行且 `healthy`；健康失败返回非零。MySQL 执行普通实验用户的 `SELECT 1`，Redis 通过密码执行 `PING`，Kafka 查询 broker 协议 API。RocketMQ 要求 NameServer 返回当前 Broker、Broker 运行统计显示活跃，并检查宿主发布端口的 HTTP/2 SETTINGS/PING 往返；这仍不等于 gRPC 业务收发，必须另跑 SDK 集成验收。其他组件检查仅证明内部就绪。

命令中的 `core` 表示 MySQL + Redis；`kafka` 只开 Kafka，`rocketmq` 只开 RocketMQ。先启动的组件不会因下一次 `up` 自动停止，切换重型章节前先 `down`。命令不受宿主 `COMPOSE_PROFILES=*` 或镜像同名环境变量覆盖，避免误开全套或重复拉取另一个标签。

## 3. 完整 JDK 21 构建容器

```bash
# 首包：仍使用仓库的 Gradle Wrapper，首次会下载对应 Gradle 和依赖
./scripts/lab.sh build courses/java-recovery-collections bash ./gradlew --no-daemon test

# 单独核实完整 JDK 与 Maven；不启动 MySQL/Redis/Kafka/RocketMQ
./scripts/lab.sh build . javac -version
./scripts/lab.sh build . mvn -version
```

`build` 是一次性容器，执行后自动移除该容器；整个仓库映射为 `/workspace`，Gradle/Maven 使用项目命名的持久化缓存卷。Gradle 版本继续由课程 Wrapper 控制，不使用宿主 Gradle，也不把首包改成 Maven。构建命令必须在仓库内的真实目录执行，路径中的空格可正常处理，不能以 `../` 或符号链接逃逸。

这里不挂载 Docker socket，不使用特权容器，因此这个构建入口适合编译与普通单元测试，**不承诺在容器内部直接运行 Testcontainers**。未来集成测试优先在已批准的云端 JDK 21 + 可用 Docker daemon 环境中执行；若需要嵌套容器测试，先单独评估权限与网络，不自动扩大宿主访问。

Linux 上构建容器的默认用户可能让输出归 root 所有；这尚未做真实验证。不要用全仓库 `chmod/chown` 掩盖问题。云端集成时先验证目录所有权并选择受控用户方案；Mac Docker Desktop 的绑定挂载行为也必须实际检查。

## 4. 连接地址与拓扑

```text
宿主 IDEA / 预置课程后端 / 浏览器
           |
           | 只发布到 127.0.0.1
           +--> 13306 --> MySQL:3306 --> mysql-data
           +--> 16379 --> Redis:6379 --> redis-data
           +--> 19092 --> Kafka:19092 --> kafka-data（仅按需）
           +--> 18081 --> RocketMQ Proxy:8081 --> Broker --> rocketmq-data（仅按需）

同一 Compose lab 网络中的课程容器
           +--> mysql:3306
           +--> redis:6379
           +--> kafka:9092（内部 advertised listener）
           +--> rocketmq:8081（gRPC，独立 CLUSTER Proxy）

一次性 java-build
           +--> /workspace（当前仓库）
           +--> gradle-cache / maven-cache（跨课程复用）
```

| 用途 | 宿主端点 | 同网络容器端点 | 健康定义 |
| --- | --- | --- | --- |
| MySQL | `127.0.0.1:13306` | `mysql:3306` | 实验账户连接目标库，查询 `SELECT 1` |
| Redis | `127.0.0.1:16379` | `redis:6379` | 认证后的 `PING` |
| Kafka | `127.0.0.1:19092` | `kafka:9092` | broker API 版本查询成功 |
| RocketMQ | `127.0.0.1:18081` | `rocketmq:8081` | NameServer/Broker 真实管理 RPC + 宿主 Proxy HTTP/2 往返；业务收发另验 |

`.env` 可调整宿主端口，容器端口不变。Kafka 同时配置内部和宿主 advertised listener，不能把宿主的 `localhost` 直接填进其他容器。Kafka 为单节点 KRaft、明文协议，只有教学用途；无 ZooKeeper，无额外控制台，无集群容错保证。

RocketMQ 把 NameServer、Broker、独立 CLUSTER Proxy 放在同一容器，只发布 gRPC 8081，不发布 9876、10911 或控制台；无鉴权/高可用，仅限隔离开发。不能改回 `--enable-proxy` 的 LOCAL 模式：选定版本会把路由端口固定为 8081，破坏宿主映射端口。详细配置、健康边界、管理命令与卷布局见 [RocketMQ 开发环境](rocketmq.md)。

旧 `infra/.env` 需要自行增加 `ROCKETMQ_PORT=18081`，保留原项目名、密码和所有其他配置。脚本不会覆盖已有 `.env`，缺键时会拒绝并给出提示。

远程 Docker context 的 `127.0.0.1` 指向远程宿主，不能当成本机地址。RocketMQ 的宿主端点检查要求入口在 daemon 所在主机运行；只允许有明确安全接入方案后扩展远程学习。脚本不会打开公网端口或创建隧道；需要远程学习时先准备明确授权的安全接入方案。

## 5. 内存、磁盘与节省方法

下列是配置上限/规划预算，不是实测峰值或下载承诺；Docker 虚拟机、文件缓存、JVM/数据库初始化还会有额外开销。

| 组合 | 容器内存上限合计 | 建议给 Docker 的内存 | 初始磁盘规划余量 |
| --- | --- | --- | --- |
| Redis 单独 | 192 MiB | 约 2 GiB | 1 GiB |
| core | 960 MiB | 约 3–4 GiB | 3–5 GiB |
| Kafka 单独 | 1024 MiB | 约 3–4 GiB | 3–5 GiB |
| RocketMQ 单独 | 1536 MiB | 约 3–4 GiB | 3–5 GiB；多进程与消息文件，非峰值实测 |
| Java 构建单独 | 1536 MiB | 约 3–4 GiB | 3–6 GiB（含依赖/Gradle缓存） |
| core + Kafka + Java 构建 | 3520 MiB | 约 6 GiB 起 | 8–12 GiB 起；低配置 Mac 不建议并发 |

- Docker 同一 daemon 下相同镜像引用会复用已有镜像层；不同 daemon/不同机器之间不共享缓存
- 各课程必须读取同一个台账，不能一课用 `redis:7`、另一课用 `redis:alpine`，也不强制 `linux/amd64` 在 Apple Silicon 仿真
- 镜像与依赖缓存、数据卷、构建输出是不同的占用，镜像共享不代表所有磁盘占用都消失
- Docker stdout 日志每容器配置 3 × 10 MiB；RocketMQ 官方各类别文件日志缩为每文件 1 MiB + 1 个归档，仍有多个类别及 JVM GC 日志，不能把 stdout 上限当成总磁盘上限
- Kafka 有日志保留时间/段大小约束；RocketMQ commitlog 段为 64 MiB、保留 24 小时。两者都不是总磁盘硬配额，更多主题/队列/持续写入仍会增长
- `doctor` 展示 Docker 占用；主机剩余空间与 Docker VM 磁盘上限不是同一概念
- 不执行 `docker system prune`、`docker volume prune`、全局镜像删除或自动删除卷；需要清理时先确认对象与备份

## 6. 安全停止、重置和密码

`down` 默认保留所有数据。如果只是暂时换章节，用 `down`。

只有主动决定丢弃此项目所有教学数据和构建缓存后，才执行下面的**破坏性**命令；使用自定义项目后缀时须替换成 `.env` 里的精确项目名。没有精确参数会在访问 Docker 前拒绝。

```bash
# 永久删除此项目 MySQL/Redis/Kafka/RocketMQ 数据以及 Gradle/Maven 缓存；不删除镜像
./scripts/lab.sh reset --confirm-reset backend-interview-labs
```

样例密码只用于隔离实验，禁止保存真实用户、订单、工作数据库或生产密码。`infra/.env` 已由根 `.gitignore` 的 `.env` 模式排除；脚本不会在 `config` 或 `doctor` 打印展开后的密码。环境变量及容器元数据仍可被有 Docker 权限的本机用户查看，这不是生产 secrets 管理。

更改 `.env` 的 MySQL 密码不会更改已存在数据卷中的账户；遇到认证失败先核对原配置或通过数据库正式改密。不要默认 reset。Redis 的密码随容器配置改变，应用也须同步更新。日志可能含实验数据，分享前需脱敏。

## 7. 常见故障，先查原因再行动

| 现象 | 下一步 |
| --- | --- |
| 未找到 Docker CLI | 在授权的云端准备 Docker；个人 Mac 制作环境不启用；无需 Docker 的 `verify` 仍可运行 |
| daemon 不可访问 | 启动已安装的 Desktop 或检查云 daemon/context；不要给 socket 加全局写权限 |
| Compose 过旧 | 核对官方受支持版本并升级；不要改用已停用的 v1 |
| 端口占用 | 查看本机监听进程，或改 `.env` 里对应高位端口；不杀未知进程 |
| MySQL 长时间不健康 | 看 `logs mysql`；首次初始化可稍等；核对磁盘、旧卷密码、版本迁移 |
| Redis OOM/noeviction | 实验上限是 96 MiB 数据内存；减少样本或为该课明确调整预算，禁止误当生产配置 |
| Kafka 进程退出 | 看 `logs kafka`、检查 Docker 内存和数据卷权限；不要任意改成 root/privileged |
| RocketMQ 未就绪 / 退出 137 | 看 `logs rocketmq` 的 uid、目录权限和官方日志；核对 Docker 内存、Proxy CLUSTER 路由；不改 root/privileged、不 reset 掩盖问题 |
| RocketMQ 健康但 SDK 连接失败 | 看真实宿主 gRPC smoke；配置同时保留 `namesrvAddr`、`proxyMode=CLUSTER`、`useEndpointPortFromRequest=true`，宿主端口取 `.env` |
| 拉取被拒绝/无网络 | 核对正式镜像源、网络政策及速率限制；不替换成未知第三方镜像 |
| `no matching manifest` | 核对选定标签/摘要架构与实际 daemon 架构；不要静默开启跨架构仿真 |
| Docker 中健康但应用连不上 | 分清宿主地址与容器 DNS；Kafka 检查 advertised listener；再查应用凭据与依赖版本 |

更多：[预置前端与课程接入契约](runtime-contract.md) · [真实验收与官方来源](verification.md)。
