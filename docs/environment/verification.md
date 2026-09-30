# 共享环境验证记录与版本来源

记录日期：2026-09-30。只列已经发生的检查，准备好的命令不是运行证据。

## 已实际执行

环境：云端 Linux x86_64，Python 3.12.14，Bash 5.2.37；随后使用已准备好的完整 Temurin JDK 21.0.12.1+1 做读取器验证。

| 检查 | 命令 | 结果 |
| --- | --- | --- |
| 脚本与安全边界回归 | `JAVA_HOME=/path/to/jdk-21 python3 -m unittest discover -s scripts/tests -v` | **本轮 84/84 通过**（含版本快照回归）；Docker 调用使用模拟对象，管理/监督脚本使用本机假进程 |
| 镜像/端口/健康/资源等静态约束 | `./scripts/lab.sh verify` | 通过，不访问 Docker |
| Bash 入口语法 | `bash -n scripts/lab.sh` | 通过 |
| Python 编译 | `python3 -m py_compile scripts/lab.py scripts/ci_smoke.py scripts/tests/*.py` | 通过 |
| 新增 RocketMQ 宿主 SDK5 探针 | 使用完整 JDK21 和已缓存官方 SDK5.0.8 执行 `javac --release 21` | 编译通过；没有 Docker，未执行真实端点连接 |
| Java 共享版本读取器 | `javac --release 21` 编译 `LabImages.java` 与 `LabImagesProbe.java`，再运行 probe | **通过**：仓库根与课程子目录均读取成功，未知键与缺失台账均按预期失败；云宿主完整 JDK21，不是构建容器 |
| 实际环境诊断 | `./scripts/lab.sh doctor` | **未通过**：缺 Docker CLI，退出码 2；未安装/启动 daemon |

回归覆盖：不执行 shell 配置、非法/重复配置拒绝、固定镜像与宿主覆盖防护、core/Kafka/RocketMQ 按需选择、目录/符号链接越界拒绝、数据默认保留、精确 reset 确认、失败不删数据、构建 Wrapper/缓存参数、就绪失败、停止容器与缺失容器、缺 Docker/daemon、旧 Compose、旧 Engine 回环暴露风险，以及 CI 专用项目限制、真实读写命令参数、收发值匹配和日志脱敏。新增 RocketMQ 回归还覆盖 HTTP/2 部分帧读取、匹配 PING ACK、TCP/错误帧拒绝、实时端口绑定与检查中进程退出、mqadmin 零退出异常拒绝、三进程 TERM 传播/异常监督、持久化读取步骤不得重新发送。

`infra/compose.yaml` 使用 JSON 语法（JSON 是 YAML 的子集），因此离线标准库可完整读取对象并检查上述约束。这不替代 Docker Compose 自己的 schema 解析。

## 已完成的真实云端 CI

- 提交：`a57a95b67a0d29cd280a54d3f761c340b9cad0d4`（PR 合并预览提交 `e0ff210f4977ef93aaadef74dccd59172368bc2c`，并未实际合并 main）
- [实际运行记录](https://github.com/weilhuang/backend-interview-labs/actions/runs/36708893556)，job `109865674586`，全部步骤成功，父任务已读取日志核对
- 实测平台：Ubuntu 24.04.5 / Linux x86_64；Docker Engine 28.0.4、Compose 2.38.2；2 CPU / 7.8 GiB
- 2026-09-30 UTC：11:30:41 MySQL/Redis 真实读写通过；11:30:49 停止/重启后持久化通过；11:31:18 Kafka 建主题、发送、消费内容比对通过；11:32:03 完整 JDK21 镜像内 Gradle `BUILD SUCCESSFUL`
- Compose 解析、镜像拉取、健康检查、独立 CI 项目清理、脱敏日志上传均已执行成功

云端制作容器本身仍无 Docker CLI；上面的结果来自独立 GitHub Actions runner，不能把两者混同。`scripts/ci_smoke.py` 只接受 `CI=true` 且精确格式的临时项目，避免误写学习者数据库。

## 未执行或未充分覆盖，不能标为通过

- 全部镜像的多架构 registry index digest 锁定：本轮有实际 amd64 拉取和运行，但未独立完成每个 arm64 manifest 审核
- 新增 RocketMQ 共享 Compose、宿主 SDK5 真实连接及重启持久化待本次 CI；既有 MySQL/Redis/Kafka smoke 使用容器内客户端，不代表所有课程 Testcontainers 集成
- 故障注入、异常终止后的数据恢复和更完整的卷权限/输出所有权矩阵
- Mac Intel/Apple Silicon Docker Desktop、Bash3.2 实测和实际资源峰值
- 前端/业务项目课 UI 验收；当前 Java 基础课无 Web 前端

按[运行契约](runtime-contract.md#4-发布前必须完成的实机验收)继续补齐，不把当前基础 smoke 视为所有课程集成成功。

## 镜像固定基线与官方证据

唯一可执行版本在 [`infra/versions.env`](../../infra/versions.env)。此处是来源说明，不是第二份机器可读版本台账。

| 键 | 已核对的官方发布内容 | 架构证据与限制 |
| --- | --- | --- |
| `MYSQL_IMAGE` | [Docker Official MySQL 8.4 标签列表](https://hub.docker.com/_/mysql/tags?name=8.4) 中存在选定完整补丁标签 | 上游标签页列出 amd64、arm64/v8；已在 CI 实际 amd64 拉取运行；arm64 与完整 registry index 审核待验收 |
| `REDIS_IMAGE` | [Docker Official Redis 镜像层页面](https://hub.docker.com/layers/library/redis/7.4.7-alpine3.21/) 显示选定完整补丁与 Alpine 标签 | 官方页面标为 multi-platform；已在 CI 验证 amd64 拉取运行；arm64 实测仍待验收 |
| `KAFKA_IMAGE` | [Apache Kafka 3.9 Docker 指南](https://kafka.apache.org/39/getting-started/docker/) 明确给出选定官方 JVM 镜像 | [该标签 arm64 镜像页面](https://hub.docker.com/layers/apache/kafka/3.9.1/images/sha256-39bc3b30084ad6ab33ad2c9a525f15c942bf097b18cb2a1825afa6df3411f8b5) 有 ARM 证据；双架构实际运行待验证 |
| `JAVA_BUILD_IMAGE` | [官方 Maven amd64 页面](https://hub.docker.com/layers/library/maven/3.9.11-eclipse-temurin-21/images/sha256-463a1849665463254b2dd56e3a5b316f1596bc93d0571065c06ea05bb48ab8f4) 与 [arm64 页面](https://hub.docker.com/layers/library/maven/3.9.11-eclipse-temurin-21/images/sha256-d1d89ba5f782ba5dd52272e7da5aed592abb192dff6435523b852ffab3ee8484) | 两页显示同一多架构 index digest，已写入台账；不是把某一个 CPU 的单架构 manifest 当作共用摘要。已在 CI 实际 amd64 拉取并完成 JDK21/Gradle 构建 |

这是官方已发布的**教学复现基线**，不是“当前最新”“无漏洞”或“所有补丁仍在维护”的保证。Kafka 3.9 文档本身标为旧版。镜像里基础 OS/JDK 的安全更新与业务主版本支持期必须分别核查；不得拿教学环境直接部署生产。没有使用 `latest`、`8.4`、`7-alpine` 等浮动标签。

除 Maven 的已核对多架构摘要外，当前其余镜像锁完整标签，标签仍可能被上游重建。同一 daemon 默认 `--pull missing` 会保留已有版本；不同时间/机器可能得到同标签的新层。正式发布前应在可用云端核验各架构与多架构 index digest，并把通过验收的摘要追加到同一个台账，不从搜索摘要臆造 digest。

## RocketMQ 共享 profile 本轮增量

`ROCKETMQ_IMAGE` 继续引用唯一台账中的现有官方镜像，来源为[Apache RocketMQ 官方 Docker 快速开始](https://rocketmq.apache.org/docs/quickStart/02quickstartWithDocker/)。本轮加入独立 `rocketmq` profile，不新增镜像、不默认启用重组件。

- NameServer、Broker 与独立 CLUSTER Proxy 同容器；Proxy 同时明确 `namesrvAddr`、`proxyMode=CLUSTER`、`useEndpointPortFromRequest=true`。固定版本 LOCAL Proxy 不保留请求映射端口，不能用于宿主 18081 的本布局
- 健康定义要求真实 NameServer/Broker 管理 RPC；统一入口进一步核对宿主当前发布绑定、HTTP/2 SETTINGS/PING 往返以及探测后的容器状态
- 1536 MiB/2CPU 总限制，三进程各自 JVM 预算、64 MiB commitlog 段、项目命名卷与 UID/可写诊断见 [详细说明](rocketmq.md)
- 已准备 CI：共享固定 JDK21 镜像编译探针；宿主 JDK21 + SDK5 从发布端口发送/消费/ACK；留存消息后 down/up，再只读原消息并 ACK；独立一次性项目与脱敏日志沿用原有边界

**尚未执行本轮共享 RocketMQ Compose 的真实 config/up、卷权限、HTTP/2/gRPC、down/up 持久化及实际资源峰值验收。** 制作云容器仍无 Docker CLI；上面“已完成的真实云端 CI”仅对应原 MySQL/Redis/Kafka/JDK 基线。消息队列课程的独立 Testcontainers CI 应由该模块报告记录，不能替代共享 Compose 结果。精确提交的 CI 完成后再补充运行链接、提交、平台和时间。

## 版本升级流程

1. 查看上游官方发布说明、支持范围与安全公告，选择具体版本
2. 在已授权云端检查多架构 manifest，保留平台与 digest 证据
3. 只改 `infra/versions.env`，确认 Compose 与 Testcontainers 读取同源
4. 跑无 Docker 回归、真实 Compose 解析，再跑各依赖课程集成测试与必要 UI 验收
5. 记录新旧镜像、数据兼容性、迁移/回退限制和实测资源后再更新发布包
6. 升级不会自动删除旧镜像/旧卷；数据文件可能不能被旧服务器版本重新打开，先备份，不用 reset 充当迁移

## 官方行为参考

- [Compose profiles](https://docs.docker.com/compose/how-tos/profiles/)：按需服务与显式指定服务的行为
- [Compose up](https://docs.docker.com/reference/cli/docker/compose/up/)：`--wait`、`--wait-timeout`、`--pull missing`
- [Docker 端口发布](https://docs.docker.com/engine/network/port-publishing/)：回环绑定及旧于 Engine 28.0 的同网段访问风险
- [Docker Desktop Mac 安装要求](https://docs.docker.com/desktop/setup/install/mac-install/)：芯片选项、受支持系统、许可与最低主机内存
- [Docker Desktop 资源设置](https://docs.docker.com/desktop/settings-and-maintenance/settings/)：VM 内存与磁盘独立于应用预算
- [Testcontainers 配置](https://java.testcontainers.org/features/configuration/)：辅助镜像与资源清理器不等于业务镜像
- [Testcontainers 网络](https://java.testcontainers.org/features/networking/)：随机端口与运行时主机地址
- [Testcontainers Kafka 模块](https://java.testcontainers.org/modules/kafka/)：按官方镜像选择兼容模块

## Testcontainers 辅助镜像

统一登记 Ryuk 0.11.0 与 Alpine 3.17.10，分别用于清理器和短暂的检测辅助容器。Testcontainers1.20.6默认tiny标签为3.17，本仓库按[官方镜像已发布补丁](https://hub.docker.com/layers/library/alpine/3.17.10/images/sha256%3A2cb00e789e7be763614c2ec63140b0ad899a29205e331eabcff9d61b04f1e0c4)固定为3.17.10，避免浮动。此旧版仅用于隔离的临时教学测试，不代表受支持或无漏洞的生产基础镜像；未来安全升级必须重跑集成。Ryuk保持启用。
