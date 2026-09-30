# RocketMQ 共享开发环境

本次交付状态：首次共享云端 CI 已通过拉取、UID3000 命名卷写入、HTTP/2 检查和宿主 gRPC 收发；重启验收收到已 ACK 的收发消息而失败。启动屏障、优雅停止及独立持久化主题修复已完成离线回归，完整真实验收待新提交重跑；资源峰值仍未测定。消息队列课程自己的 Testcontainers 结果与这里的共享 Compose 是两套隔离验收，不能互相代替。

## 启动、检查、停止

```bash
./scripts/lab.sh down          # 换章节前停掉其他重组件；保留所有数据
./scripts/lab.sh up rocketmq   # 只启动同一官方镜像中的三个进程
./scripts/lab.sh check rocketmq
./scripts/lab.sh logs rocketmq
./scripts/lab.sh down          # 保留 rocketmq-data、其他数据卷和构建缓存
```

`infra/versions.env` 的 `ROCKETMQ_IMAGE` 是唯一镜像引用来源，与消息队列课程 Testcontainers 同源。不会另外拉 NameServer、Broker、Proxy 或控制台镜像。默认 `up` 仍只开 MySQL/Redis；显式 `up rocketmq` 不会停掉此前服务，故切换章节先 `down`。

- 宿主 SDK5 端点：`127.0.0.1:18081`，端口由 `.env` 的 `ROCKETMQ_PORT` 控制
- 同一 Compose 网络：`rocketmq:8081`
- 只发布回环地址 gRPC 端口；9876、10911、8080 均不发布
- SDK 使用 `enableSsl(false)`，无公网、鉴权、主从或容错保证；仅供隔离开发
- 本文不改变 JDK21 课程标准：源码/探针使用完整 JDK21，官方 RocketMQ 发行镜像自带的服务端 JVM 是上游运行时，不重打镜像或替换它

## 为什么是三进程 CLUSTER Proxy

NameServer、单个 Broker、独立 CLUSTER Proxy 同容器，共享容器网络。因此 Broker 与 Proxy 的 `namesrvAddr` 均为 `127.0.0.1:9876`，Broker 注册地址为 `127.0.0.1:10911`。Proxy 显式指定 `proxyMode=CLUSTER` 和 `useEndpointPortFromRequest=true`，向 SDK 保留其请求端点。

选定服务端版本的 LOCAL Proxy（`mqbroker --enable-proxy`）路由实现不使用请求中的映射端口，可能把宿主 SDK 重定向到未发布的 8081。因此不能把 CLUSTER 三进程简化回 LOCAL。若以后拆成三个容器，需要重新设计容器 DNS/注册地址，不能照抄同容器的回环地址。

启动顺序有明确屏障：先启动 NameServer/Broker；最多等待 120 秒，重复小内存实际 `clusterList`，单次 RPC 取剩余预算与 15 秒较小值；要求精确 Broker 路由、版本和 active。RPC 失败/空表头不算成功；任一服务提前退出则停止，不启动 Proxy。随后显式创建允许广播的系统消费组 `CID_DefaultHeartBeatSyncerTopic`（`updateSubGroup -d true`），确认成功才启动 Proxy，避免禁用自动创建后出现内部 CODE26。失败保留最近 RPC 输出，不用固定 sleep 或盲重启代替条件。

监督脚本为各进程建立独立进程组；收到 TERM 时停止官方 shell 包装及 Java 子进程，并最多等待整个进程组 25 秒退出，不能只等先退出的 shell 包装、提前结束尚在刷盘的 Java。超时会明确记录强制终止，不能标作优雅关闭。任一关键进程意外退出，即使退出码为 0，也使容器返回失败，避免只剩一个 Java 进程却显示“可用”。`down` 的 30 秒等待上限之后 Docker 可能强制停止，因此异常终止恢复仍须另验。

## 就绪证据分层

1. Compose 健康检查：Proxy 监听存在；实际运行小内存 `clusterList`，要求 NameServer 返回指定 Broker，Broker 运行统计包含版本且处于 active；异常文本或空表头均失败，不能只看 mqadmin 退出码
2. `up/check`：重新跑管理 RPC、核对实际 Docker 回环发布绑定、从当前宿主完成 HTTP/2 SETTINGS 和匹配 PING ACK，再读取容器实时状态；TCP connect 或历史 healthy 状态都不够
3. CI 业务验收：JDK21 + RocketMQ SDK5 从 `.env` 宿主端点建客户端，在 roundtrip 主题/组发送、比对、ACK；在另一个 durable 主题/组预建消费位置并留存一条未消费消息。`down/up` 后只打开原 durable 主题/组，必须读到重启前的精确内容并 ACK，不创建 Producer、不补发；空消息超时或任何未知内容都失败

RocketMQ 至少一次投递允许重复；一次 ACK 的 RPC 成功不能被解释成跨重启精确一次消费保证。独立主题避免把已 ACK roundtrip 的重投误判为持久化内容错误，同时不降低“必须读回重启前 durable 原消息”的要求。ACK 状态强持久化、异常断电恢复及业务幂等属于另外的课程验收。

前两层通过不代表第三层通过。HTTP/2 往返也不是一次 gRPC 业务 RPC。远程 Docker context 的回环端点不在脚本主机，不能自动回退成容器内检测后声称宿主通过；在 daemon 所在的授权云端主机运行本入口。

## 资源与磁盘边界

容器限制 1536 MiB、2 CPU。Java 堆与直接内存设置：

| 进程 | 初始/最大堆 | 直接内存上限 |
| --- | --- | --- |
| NameServer | 64/128 MiB | 32 MiB |
| Broker | 256/512 MiB | 128 MiB |
| Proxy | 128/256 MiB | 64 MiB |
| 短时 mqadmin | 32/128 MiB | 32 MiB |

堆上限不等于 RSS，仍有 metaspace、线程栈、映射文件和文件缓存。预算在实际 CI 的 OOM/资源结果出来前不能宣称“峰值已验证”；建议 Docker 3–4 GiB 内存、3–5 GiB 初始磁盘余量，避免同时开 Kafka/core/构建容器。镜像中的 mqadmin 默认工具脚本会创建约 1 GiB JVM，所以管理脚本直接调用同发行包工具主类，限制内存并在 15 秒超时后终止工具进程。

数据卷采用本项目 `rocketmq-data:/tmp`，数据明确位于 `/tmp/lab-rocketmq/store`。这里的 `/tmp` 被命名卷持久化，不是关机即丢弃的临时数据；`down` 保留，只有精确确认当前项目的 `reset` 才删除。选择镜像已有的可写目录，是为了保留 UID3000 且不新增 root/chown 初始化服务，不把整个发行目录复制进卷。新卷实际可写性已由首次 Linux amd64 CI 验证：`/tmp` 为 root 的 1777 目录，`lab-rocketmq/store` 由 UID3000 创建。其他架构/环境仍待实测；启动会记录 UID/GID 并检查 store 可写，不会自行改权限或删卷。

commitlog 段设置为 64 MiB，过期保留时间为 24 小时。它们不是磁盘硬配额，多主题/队列或持续发送仍会增长。Docker stdout 日志为 3×10 MiB；官方文件日志按类别缩至 1 MiB 文件与一个归档，JVM GC 日志仍另占空间。用 `doctor` 看占用，不运行任何全局 prune。

## 管理与 CI

自动建主题/消费组关闭。课程初始化代码需要显式管理操作；同容器管理入口是 `bash /opt/lab-rocketmq/admin.sh`，仅登记 `clusterList`、`updateTopic`、`updateSubGroup`、`topicStatus`。它使用内部 NameServer/Broker 地址，参数与官方 mqadmin 相同，不接受未登记的删除命令。由课程管理器或本项目 Compose exec 调用，不对公网开放管理端口。

CI 在精确格式 `backend-interview-labs-ci-运行号-重试号` 下创建一次性主题/消费组，普通学习项目调用 `scripts/ci_smoke.py` 会被拒绝。流程依次运行 core、Kafka、RocketMQ，再单独构建，避免默认同时启动重组件。故障保留脱敏 Docker 日志、UID/目录信息及官方有限尾部日志；不自动 reset 掩盖错误。

官方依据：[Docker 快速开始](https://rocketmq.apache.org/docs/quickStart/02quickstartWithDocker/)、[固定版本 Proxy 配置](https://github.com/apache/rocketmq/blob/rocketmq-all-5.3.2/proxy/src/main/java/org/apache/rocketmq/proxy/config/ProxyConfig.java)、[LOCAL 路由实现](https://github.com/apache/rocketmq/blob/rocketmq-all-5.3.2/proxy/src/main/java/org/apache/rocketmq/proxy/service/route/LocalTopicRouteService.java)、[CLUSTER 路由实现](https://github.com/apache/rocketmq/blob/rocketmq-all-5.3.2/proxy/src/main/java/org/apache/rocketmq/proxy/service/route/ClusterTopicRouteService.java)、[官方容器构建及非 root 用户](https://github.com/apache/rocketmq-docker/blob/master/image-build/Dockerfile-ubuntu)。
