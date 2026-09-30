# 共享环境验证记录与版本来源

记录日期：2026-09-30。只列已经发生的检查，准备好的命令不是运行证据。

## 已实际执行

环境：云端 Linux x86_64，Python 3.12.14，Bash 5.2.37；随后使用已准备好的完整 Temurin JDK 21.0.12.1+1 做读取器验证。

| 检查 | 命令 | 结果 |
| --- | --- | --- |
| 脚本与安全边界回归 | `python3 -m unittest discover -s scripts/tests -v` | **42/42 通过**；Docker 调用使用模拟对象 |
| 镜像/端口/健康/资源等静态约束 | `./scripts/lab.sh verify` | 通过，不访问 Docker |
| Bash 入口语法 | `bash -n scripts/lab.sh` | 通过 |
| Python 编译 | `python3 -m py_compile scripts/lab.py scripts/ci_smoke.py scripts/tests/*.py` | 通过 |
| Java 共享版本读取器 | `javac --release 21` 编译 `LabImages.java` 与 `LabImagesProbe.java`，再运行 probe | **通过**：仓库根与课程子目录均读取成功，未知键与缺失台账均按预期失败；云宿主完整 JDK21，不是构建容器 |
| 实际环境诊断 | `./scripts/lab.sh doctor` | **未通过**：缺 Docker CLI，退出码 2；未安装/启动 daemon |

回归覆盖：不执行 shell 配置、非法/重复配置拒绝、固定镜像与宿主覆盖防护、core/Kafka 按需选择、目录/符号链接越界拒绝、数据默认保留、精确 reset 确认、失败不删数据、构建 Wrapper/缓存参数、就绪失败、停止容器与缺失容器、缺 Docker/daemon、旧 Compose、旧 Engine 回环暴露风险，以及 CI 专用项目限制、真实读写命令参数、收发值匹配和日志脱敏。

`infra/compose.yaml` 使用 JSON 语法（JSON 是 YAML 的子集），因此离线标准库可完整读取对象并检查上述约束。这不替代 Docker Compose 自己的 schema 解析。

## 已准备但尚未运行的云端 CI

[共享环境 workflow](../../.github/workflows/lab-environment.yml) 在独立 Ubuntu 24.04 GitHub runner 上依次执行 core 读写、停止/重启持久化、Kafka 收发、完整 JDK21/首包 Gradle 构建；最后仅清理 `backend-interview-labs-ci-运行号-重试号` 的临时卷，并上传脱敏日志。

`scripts/ci_smoke.py` 只接受 `CI=true` 且精确格式的独立项目，防止误写学习者已有数据库。这个 workflow 已做 YAML 解析检查，**还没有实际 GitHub run / job URL，不能宣称 CI 已通过**。部署授权与推送由仓库主任务统一处理；一旦真实运行，需在此补充提交 SHA、run URL、各阶段结果和平台。

## 未执行，不能标为通过

- Docker Compose 真实 `config`、镜像拉取和 registry manifest digest 校验
- MySQL/Redis/Kafka 的真实启动、卷权限、健康检查、宿主连接、持久化读写和消息收发
- `up/down/up` 数据保留，异常退出后的恢复，临时项目 reset 范围的真实验收
- JDK21 构建镜像中的首包 Gradle 任务与输出文件所有权
- Testcontainers 运行；`LabImages.java` 已用云宿主 JDK21 编译并验证读取，但尚未接入真实容器项目课
- Mac Intel/Apple Silicon 的 Docker Desktop 与 Bash3.2 实测，实际内存/磁盘峰值
- 前端/业务项目课 UI 验收；当前 Java 基础课无 Web 前端

待获准可用 Docker 环境后，按 [运行契约的验收清单](runtime-contract.md#4-发布前必须完成的实机验收) 逐项补证据，不为通过测试静默安装 daemon、挂 socket、改权限或清理卷。

## 镜像固定基线与官方证据

唯一可执行版本在 [`infra/versions.env`](../../infra/versions.env)。此处是来源说明，不是第二份机器可读版本台账。

| 键 | 已核对的官方发布内容 | 架构证据与限制 |
| --- | --- | --- |
| `MYSQL_IMAGE` | [Docker Official MySQL 8.4 标签列表](https://hub.docker.com/_/mysql/tags?name=8.4) 中存在选定完整补丁标签 | 上游标签页列出 amd64、arm64/v8；本次未执行 registry manifest/pull |
| `REDIS_IMAGE` | [Docker Official Redis 镜像层页面](https://hub.docker.com/layers/library/redis/7.4.7-alpine3.21/) 显示选定完整补丁与 Alpine 标签 | 官方页面标为 multi-platform；本次没有验证该具体标签在本机的 amd64/arm64 拉取，按待验收处理 |
| `KAFKA_IMAGE` | [Apache Kafka 3.9 Docker 指南](https://kafka.apache.org/39/getting-started/docker/) 明确给出选定官方 JVM 镜像 | [该标签 arm64 镜像页面](https://hub.docker.com/layers/apache/kafka/3.9.1/images/sha256-39bc3b30084ad6ab33ad2c9a525f15c942bf097b18cb2a1825afa6df3411f8b5) 有 ARM 证据；双架构实际运行待验证 |
| `JAVA_BUILD_IMAGE` | [官方 Maven amd64 页面](https://hub.docker.com/layers/library/maven/3.9.11-eclipse-temurin-21/images/sha256-463a1849665463254b2dd56e3a5b316f1596bc93d0571065c06ea05bb48ab8f4) 与 [arm64 页面](https://hub.docker.com/layers/library/maven/3.9.11-eclipse-temurin-21/images/sha256-d1d89ba5f782ba5dd52272e7da5aed592abb192dff6435523b852ffab3ee8484) | 两页显示同一多架构 index digest，已写入台账；不是把某一个 CPU 的单架构 manifest 当作共用摘要。尚未实际拉取 |

这是官方已发布的**教学复现基线**，不是“当前最新”“无漏洞”或“所有补丁仍在维护”的保证。Kafka 3.9 文档本身标为旧版。镜像里基础 OS/JDK 的安全更新与业务主版本支持期必须分别核查；不得拿教学环境直接部署生产。没有使用 `latest`、`8.4`、`7-alpine` 等浮动标签。

除 Maven 的已核对多架构摘要外，当前其余镜像锁完整标签，标签仍可能被上游重建。同一 daemon 默认 `--pull missing` 会保留已有版本；不同时间/机器可能得到同标签的新层。正式发布前应在可用云端核验各架构与多架构 index digest，并把通过验收的摘要追加到同一个台账，不从搜索摘要臆造 digest。

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
