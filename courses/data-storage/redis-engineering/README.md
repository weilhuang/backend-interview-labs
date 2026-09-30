# C07 Redis与缓存一致性 · 完整七单元

这是可独立打开的JetBrains Academy课程根，保持长期完整内容，不是两周删减版。课程自带全部Java源码、调用端、测试、故障编排、公开标准解与中文机制解释。Redis/MySQL实验使用真实客户端和隔离容器；纯Java通过不代表服务端实验通过。

## 开课版本、依赖与验收状态

| 项目 | 本课固定值/选择 | 当前验证边界 |
|---|---|---|
| 课程 | 1.0.0；基础到进阶故障工程；先修C00、C02基础、C06事务 | 7单元实现和讲义已交付；完整发布仍有动态门禁 |
| JDK | Eclipse Temurin21.0.12.1+1；Java目标21，不启用预览特性 | 完整JDK21严格编译全部源码/测试 |
| 构建 | Gradle Wrapper8.10.2，SHA-256写入wrapper配置；Gradle JVM与测试JVM为21 | CLI配置解析和官方本地JAR离线unitTest通过；标准Maven在线解析未完成 |
| 测试 | JUnit Jupiter5.11.4 / Platform1.11.4；Testcontainers1.20.6 | 17个纯Java测试通过；18个真实集成测试编译，未动态执行 |
| 客户端 | Jedis5.2.0、Commons Pool2由其依赖锁定2.12.0、MySQL Connector/J9.2.0 | 实际Maven Central JAR编译，无假接口stub |
| IDE/Academy | 目标IntelliJ IDEA2026.1.5 build261.27258.48；Academy2026.9-2026.1-1070 | 工具可用版本；本课程预览/检查/重置/导出/干净导入尚未实测 |
| 前端 | 不需要；使用Java Usage与JUnit作为完整调用端 | 不要求学习者搭建或修改网页 |
| Docker | Linux Engine28.0+、Compose2.20.0+是共享环境最低线 | 本云端无Docker CLI/daemon，Engine/Compose实际版本待动态环境记录 |
| 共享环境 | 仓库infra/versions.env为唯一镜像台账；REDIS_IMAGE、MYSQL_IMAGE | 当前台账Redis7.4.7-alpine3.21、MySQL8.4.7；tag不是不可变digest，摘要/架构待拉取记录 |
| 镜像读取 | support的Images向上查台账；独立导出用LAB_VERSIONS指定同一原始文件 | 测试和Usage无镜像tag常量，无另一份版本表 |
| 资源 | 01–03仅Redis；04/06/07为Redis+MySQL；05最多两Redis节点 | 建议至少2核/4GiB可用供单课试验，是预算建议而非实测最低；测试串行 |
| 端口/数据 | Testcontainers分配临时端口、网络和容器内数据目录；c07随机键前缀 | 不连接真实服务、不执行全库清空、不重置现有卷 |

精确测试状态见[阶段报告](中文阶段报告.md)，源码入口见[SOURCES](SOURCES.md)，第三方出处见[声明](THIRD_PARTY_NOTICES.md)。不要把尚未完成的Docker或IDE检查记为通过。

## 一条自检与三类执行

在本课程根使用完整JDK21：

```bash
java -version
./gradlew --version
./gradlew unitTest             # 只验证17项纯Java契约；不需要Docker
./gradlew test                 # 完整35项：17纯Java + 18真实集成；Docker缺失明确失败
./gradlew integrationTest      # 只跑真实集成，便于单独留档
./gradlew :redis:01-structures:run
```

先核实IDE Project SDK、Gradle JVM、测试JVM都是21。首次下载Gradle或依赖失败属于环境错误，不是答案错误；按正常代理/证书配置修复，不禁用TLS校验。无Docker时可读、编译和做纯Java题，不能把跳过集成当课程完成。默认test包含集成，不使用disabledWithoutDocker悄悄变绿。

Testcontainers直接创建并关闭自己的容器，无需先启动Compose。若要观察共享服务，在仓库根使用已实现的入口：

```bash
./scripts/lab.sh doctor
./scripts/lab.sh up redis
./scripts/lab.sh check redis
./scripts/lab.sh up core        # 需要MySQL+Redis时
./scripts/lab.sh check core
./scripts/lab.sh down           # 不接受组件参数；停止本项目而保留数据
```

共享实例宿主端口为Redis16379、MySQL13306，库interview_lab；它们与本课临时c07_lab容器不是同一套数据。课程的崩溃/提升测试只能运行在它自行创建的容器上。不要复制实验脚本改成公司的Redis地址。详细启动/健康/停止和重置范围见仓库docs/environment/README.md。`lab.sh build`不挂Docker socket，不能默认用它承载嵌套Testcontainers。

## 七单元导航与完成产物

| 单元 | 任务/调用端 | 核心可检验证据 |
|---|---|---|
| C07-01 | [结构与原子命令](redis/01-structures/task.md)，StructuresUsage | Hash/Set/ZSet/Stream、固定窗口Lua、pipeline与脚本错误不回滚 |
| C07-02 | [过期淘汰](redis/02-expiry/task.md)，ExpiryUsage | UTF-8限额、PTTL、真实4MB noeviction/allkeys-lru |
| C07-03 | [穿透击穿雪崩](redis/03-stampede/task.md)，StampedeUsage | 负缓存TTL、四线程单飞一次回源、失败释放、抖动与容量 |
| C07-04 | [数据库缓存竞态](redis/04-consistency/task.md)，ConsistencyUsage | MySQL事务outbox、旧回填反例、幂等重投、水位丢失重建 |
| C07-05 | [持久化复制](redis/05-replication/task.md)，ReplicationUsage | RDB/AOF进程崩溃边界、双节点WAIT、手工隔离提升 |
| C07-06 | [租约与fencing](redis/06-leases/task.md)，LeasesUsage | token安全续租/释放、错误授予顺序反例、MySQL拒绝旧fence |
| C07-07 | [服务故障演练](redis/07-resilience/task.md)，ResilienceUsage | 有界池/超时/背压、真实Redis慢/停/恢复、实际MySQL回源 |

每节有独立task.md、src/labs、test/labs、solution.md。所有测试在IDE和导出包中可见。标准解完整公开，随时可查；看答案后建议换输入/时序独立重写，并口述保证成立的前提。

## Academy与普通Gradle两种工作方式

- 这是作者模式课程：源码为参考答案，task-info.yaml中的真实placeholder提供学员起点；不是以注释TODO伪装空白练习
- 使用Academy的课程创建/打开本地作者课程入口，选择当前含course-info.yaml的目录。按插件当前UI实际操作；预览、Check、Reset、Export、干净导入均需记录，当前未把静态YAML检查当IDE实测
- 普通IDE方式直接打开当前Gradle根即可阅读/运行标准解。需要空实现练习副本时运行`python3 authoring/materialize_learner.py build/learner`；该副本是普通Gradle工程，不声称是官方可导入归档
- 独立导出保留自动生成的shared镜像快照与SHA256，无需父仓库；LAB_SHARED_VERSIONS或LAB_REPO_ROOT可显式覆盖，旧LAB_VERSIONS仍兼容。详见[独立课程镜像台账](shared/README.md)。源码仓库可用Wrapper；Academy官方ZIP若移除Wrapper，请用Check/Run或Gradle工具窗口。真实Redis集成仍需要Docker
- 运行`python3 authoring/validate_course.py`检查7题元数据、可见文件、实现区和教案；修改Java后用`python3 authoring/sync_metadata.py`同步公开标准解及占位符offset

## 统一完成标准

A：完整真实测试和纯契约通过，失败场景能复现且资源关闭；O：记录版本、配置、数据量、时序、指标与不能推出的结论；R：固定源码文件/符号/状态/分支/反例；T：明确模型省略范围。压测没遇到问题不是证明，脚本原子执行不是出错回滚，WAIT不是无限故障下零丢失，租约不是永久所有权，Future超时不是底层工作已结束。

每节独立迁移至少做一次，不追求背答案数量，不承诺学习后必过面试。本课程不要求前端、不缩减两周之外的内容，不接触学习者个人电脑或生产系统。
