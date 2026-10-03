# C11 云原生：先让一笔订单穿过容器

> 这是Docker、Compose与容器网络前三课的源码草稿。已提供应用、调用方、可见测试和参考答案；当前Java运行、真实Docker/Redis与Academy原生Check均为NOT_RUN。统一环境命令尚待集成，文中的preflight/up/seed/verify/stop表示生命周期要求。

这是一门总课程中的 C11 共享项目，不是第二套课程或第二套基础设施。你不需要先会 Docker、Kubernetes、Istio，也不需要写前端。先用已提供的网页和命令行调用方，看到“库存从 10 变成 8”，再追踪这两份库存经过哪些进程、端口和数据卷。第一批覆盖 C11-01、C11-02、C11-03；后续 Kubernetes 和 Istio 尚未实现，不应把本项目当作整章完成。

## 学完第一段能做什么

1. 解释镜像和容器的区别，给一份可运行的 Java 应用制作不含编译器的运行镜像
2. 区分“进程存在”“端口可连”“依赖正常”“业务已初始化”；读懂一条 readiness 失败的原因
3. 用 Compose 创建有界、独立、保留数据的本机环境，不误停别的项目
4. 让容器通过 `redis:6379` 找到 Redis，并区分 DNS、连接、超时和认证问题
5. 用真实输入/输出说明：重复初始化不回填库存，同一订单重放不重复扣减，依赖故障不伪装成功，停止时排空已接受的请求

## 你拿到的完整项目

```
浏览器（已提供）或 bin/call.py（已提供）
   | HTTP，宿主 127.0.0.1:18085
   v
Docker 端口发布 -> cloudnative-api:8080
                    | CloudNativeApp：路由/响应/优雅退出
                    | CloudPolicy：业务就绪判断（C11-02练习）
                    | AddressPolicy：依赖地址（C11-03练习）
                    v
                 RedisClient：TCP + RESP2，超时600ms
                    | AUTH + PING / HGET / EVAL
                    v
                 redis:6379（不发布到宿主）
                    | 一次Lua中完成检查、扣库存、记幂等结果
                    v
                 <project>_cloudnative-redis-data（保留卷）
```

- `src/labs`：完整 Java 21 项目，只用 JDK 自带 HTTP 服务器，无 Maven 下载和业务框架先修
- `web/index.html`：可直接点按钮的前端；所有请求走同源地址，不需要 Node.js
- `bin/call.py`：和网页等价的可复制调用方；输出 HTTP 状态和 JSON
- `container/Dockerfile`：多阶段、非 root、exec 入口参考；镜像值只由总课程 `shared/versions.env` 提供
- `starter`：能编译或能构建的未完成版本；正确预期是可运行但契约测试失败
- `answers`：完整参考文件与不同实现思路；先解释行为再看答案
- `tests/contract.py`：真实 HTTP 业务断言；`native_verify.py` 验证真实 JVM/HTTP/信号但用 Redis 假服务；`docker_verify.py` 才检查真实 Redis/Lua/容器网络
- `wrong`：用于证明测试有效的错误解。它们不是生产配置，也不是建议你采用的“快捷方式”

## 先修小词典：每个词都对应一个观察

| 词 | 本课最小定义 | 你能看到的证据 |
|---|---|---|
| 进程 | 正在执行的一份程序，有自己的进程号 | 启动日志、停止退出码 |
| 端口 | 操作系统用来把网络连接交给某个进程的编号 | API监听8080，Redis监听6379 |
| localhost / 127.0.0.1 | “当前网络空间里的我自己” | API容器的localhost不是Redis容器 |
| DNS | 把名字解析为地址 | `redis`能解析；保留的`.invalid`域名解析失败 |
| 镜像 | 创建运行环境的只读文件层与默认配置 | Dockerfile、镜像ID、User与Entrypoint |
| 容器 | 根据镜像创建的隔离进程和可写层 | 一个镜像可创建多次，停止容器不等于删除镜像 |
| build context | 构建器允许读取的目录范围 | `.dockerignore`白名单排除秘密和测试文件 |
| tag / digest | 可读标签 / 内容寻址标识 | 完整版本加digest由唯一台账固定 |
| JDK / JRE | 编译和开发工具 / 运行Java所需环境 | 构建层有javac，运行层不应有javac |
| Compose service | 一类容器的声明，不等于某个固定IP | `cloudnative-api`、`redis` |
| project | Compose资源的命名和管理范围 | 统一入口生成`totalacademy-...`前缀 |
| volume | 独立于容器可写层的数据存储 | 重建应用或重启Redis后库存不回到10 |
| live / ready | 进程还能处理请求 / 现在能接业务流量 | Redis停了时/live=200，/ready=503 |
| 幂等 | 同一操作重复执行不会产生额外业务副作用 | 两次seed仍10；买2份后再seed仍8 |
| SIGTERM | 请求进程有序结束的信号 | drain_started → 请求完成 → shutdown_completed |
| SIGKILL | 立即强制结束，无法安排收尾 | 不应把退出137当作正常优雅停止 |

在纸上画出“谁在给谁发请求”。能说清当前命令在宿主还是在容器内执行，比背术语更重要。

## API契约（所有例子都只有合成数据）

| 请求 | 正常结果 | 重要失败 |
|---|---|---|
| `GET /live` | 200，`status=UP` | 不把Redis短暂故障等价为应用死亡 |
| `GET /startup` | 200，`status=UP` | 首批无慢启动流程，为后续探针课保留 |
| `GET /downstream-check` | 200，`status=PONG,layer=APPLICATION` | 503 + DNS/CONNECT/TIMEOUT/AUTH/PROTOCOL |
| `GET /ready` | 200，`status=READY,seeded=true` | 尚未seed、依赖失败或排空中则503 |
| `POST /seed` | 初次`created=true,stock=10` | 再次`created=false`，不得覆盖已扣库存 |
| `GET /stock` | 200，`stock`为整数 | 没有初始化时503、stock=-1 |
| `POST /orders?request_id=first&quantity=2` | 初次201、CREATED、remaining=8 | 同ID同数量200 REPLAY；同ID不同数量409 CONFLICT |
| `GET /slow?millis=1500` | 200，COMPLETED | 仅为停止排空测试提供，最大2000ms |

这里特意使用查询参数传合成订单，避免先学JSON解析器；真实交易系统应设计认证、请求体、幂等键存储寿命、审计和完整金额模型。接口没有登录保护，只能在教学回环环境使用。端口绑定回环不是完整访问控制。

## 运行顺序与验收边界

环境入口尚待总课程集成；此草稿不提供可直接启动C11的总课程命令。已提供脚本的执行方式和验证边界见 `docs/verification.md`。不要从本目录再复制一份版本台账，不要手工启动第二套MySQL/Redis。第一段仅需一个Redis，MySQL继续沿用总课程现有台账，未用到时不启动。

```text
preflight -> up（下游可连，但可能尚未seed）
              -> seed -> /ready=200 -> 业务验证
              -> collect -> stop（保留volume）
```

首次 `up` 不能先等待 API 的 `/ready`，又把 seed 放在“等待完成之后”，否则构成死锁。先有界等 `/downstream-check`，再执行显式 seed，最后以 `/ready` 开始业务验证。Compose的Redis健康依赖只能解决启动时的一部分先后关系；运行途中Redis仍可能失败，所以应用每次调用都要有超时和错误契约。

### 结果为什么分层记录

- 离线检查通过：说明文件规则、隔离边界、判题器和shell信号反例通过；不说明镜像可构建
- 原生进程通过：说明真实JVM/HTTP/TCP/信号成立；本地Redis假服务**不执行Lua**，不说明真实Redis原子性通过
- 真实Docker通过：必须在可用daemon上真的构建、启动、调用Redis/Lua、制造网络故障并恢复
- Academy原生交互：编辑区、占位符、Check按钮与Gradle/外部适配一致性另验；不能拿命令行日志替代

只有在你的实际环境重新执行后，才能记录运行结果。镜像版本清单只能说明选择了哪些依赖，不能证明镜像构建、运行或漏洞检查已经完成。

## 企业使用前仍要补的事

本机一份Redis并不是高可用数据库；AOF不是跨机备份；本课最小RESP客户端没有连接池、TLS、集群重定向等生产能力；订单幂等记录没有淘汰策略。JRE镜像减少编译工具，不等于“没有漏洞”；固定digest解决可重复性，不会自动更新安全补丁。生产系统还需身份认证、秘密管理、供应链扫描/签名、数据备份恢复、容量测试、SLO以及经过验证的升级流程。后续C11-04..10会逐步引入编排、发布、隔离和网格，绝不把本机Compose等同企业完整方案。
