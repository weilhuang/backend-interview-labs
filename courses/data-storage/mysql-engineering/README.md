# C06 · MySQL 索引与事务工程（V1）

完整七单元，可作为独立 Academy 课程根导入，不是两周压缩目录。先修为 Java 方法、异常、集合和基础并发；SQL从第一题补齐。退出目标是独立写SQL、建立事务时序、解释真实计划/锁/日志证据，完成库存故障回归。

## 版本与前置条件

| 项目 | 固定值与状态 |
|---|---|
| 课程 | V1.0.0，入门到进阶/高级场景，七单元全部公开 |
| JDK | 编译/运行目标21；制作端Eclipse Temurin21.0.12.1+1，完整javac/java |
| Gradle | Wrapper8.10.2，发行包SHA256已固定 |
| 测试 | JUnit Jupiter5.11.4 / Platform1.11.4，Testcontainers1.20.6 |
| 驱动/连接池 | MySQL Connector/J9.2.0 / HikariCP6.2.1 |
| 数据库 | 从仓库infra/versions.env或其自动生成的shared快照读取MYSQL_IMAGE；精确tag/digest以台账为准 |
| Docker | 实验需要可用daemon与Compose v2；本制作云端没有daemon，课程真实集成验收等待CI |
| IDE / Academy | 项目语言级别JDK21；当前课程尚未完成实际插件预览、检查、导出和干净导入，不宣称IDE验收完成 |
| 前端 | 不需要；SQL/JDBC/CLI与可见JUnit是完整调用链，不要求学员制作界面 |
| 资源 | 每题一个隔离MySQL容器，建议至少2核/4GiB可用内存；建议值不是已测最低门槛 |
| 端口 | Testcontainers随机本地端口；共享Compose端口从infra/.env读取，默认13306，密码不写入源文件 |

## 从干净环境启动

完整仓库直接使用根镜像台账；独立导入时使用课程内自动生成、带SHA256的shared快照，不需要父仓库。也可用LAB_SHARED_VERSIONS或LAB_REPO_ROOT显式覆盖。详见[独立课程镜像台账](shared/README.md)。下面的命令适用于保留Wrapper的源码仓库；Academy官方ZIP使用Check/Run或Gradle工具窗口。

仓库根：

```sh
./scripts/lab.sh doctor
./scripts/lab.sh up mysql
./scripts/lab.sh check mysql
```

课程根：

```sh
java -version
javac -version
./gradlew --version
./gradlew unitTest
./gradlew test
```

test运行真正MySQL容器（不依赖已启动的Compose实例），没Docker会失败，不会默默跳过。unitTest只验证纯输入/策略契约，不能证明事务、锁、恢复。不要把两个命令的结果混淆。初次构建需访问Maven Central和Gradle发行包；下载失败不是学生代码错误。

## 使用预置调用端

共享Compose运行之后，设置对应实验库/用户/密码。以infra/.env实际值为准，连接仅限你拥有的本地教学环境。

```sh
export LAB_JDBC_URL='jdbc:mysql://127.0.0.1:13306/interview_lab?connectionTimeZone=UTC&forceConnectionTimeZoneToSession=true&connectTimeout=3000&socketTimeout=5000'
export LAB_DB_USER=lab
# LAB_DB_PASSWORD从本地实验配置设置，不要把真实密码提交Git
./gradlew :mysql-01-model-01-order-contract:reset
./gradlew :mysql-01-model-01-order-contract:run
```

reset入口明确只重建c06_*合成表数据：不DROP DATABASE，不清空其他课程表，不删除Docker卷。首次执行创建本课表；重复执行删除本课行后重新seed。索引DDL实验可能保留，C06-02的测试自建独占容器并独立处理索引。Usage不暗中reset，C06-04/05/06/07会改变实验数据，重跑前显式reset。不要把LAB_JDBC_URL指向生产或不属于你的数据库。

停止共享服务在仓库根运行 ./scripts/lab.sh down。无须docker system prune；不用全局清理。Testcontainers清理自身容器，不操作共享Compose实例。

## 七单元导览

| 单元 | 动手实现 | 自动证据 | 观察/深挖 |
|---|---|---|---|
| C06-01 | 参数化聚合、租户隔离、金额换算 | 3500分、错误JOIN5000、约束失败、回滚 | 主外键/范式/时区 |
| C06-02 | 联合索引与受控偏斜seed | 结果保持、索引列顺序 | JSON和ANALYZE计划、覆盖/回表 |
| C06-03 | 完整游标、UTC半开区间 | 同时间tie-break、不重复、limit边界 | 深OFFSET、函数/转换、N+1迁移 |
| C06-04 | 两真实连接可复现时序 | RC(10,11,11)、RR(10,10,11)、脏读防护 | Read View、undo、当前读 |
| C06-05 | 错误分类、整笔重试、排序加锁 | 1213死锁、1205范围锁、总量守恒 | data_locks、gap/next-key条件 |
| C06-06 | 真实配置与独占容器重启 | 已提交保留、未提交丢弃 | redo/undo/binlog/复制/备份边界 |
| C06-07 | 条件扣减、请求幂等、乐观版本、真实连接池与复制延迟 | 30抢10、不重复、资源释放、池耗尽复位、暂停副本陈旧读 | 连接池取舍、读副本陈旧度 |

每节task.md包含企业问题、原理、ASCII、步骤、全部测试入口、真实源码、递进面试问答和独立迁移；answer.md含完整标准实现与中文解析。每节 src/labs/Usage.java 是完整调用方，不是伪代码。

## Academy作者版与学员版

course-info.yaml是实际课程根；每节type: edu、可见文件清单和Unicode字符占位范围按官方Java样例结构建立。作者源码含标准解；Preview学员副本会把占位区变成待实现异常，真实题目测试初始失败是正常现象。公共support/src、support/test、sql和构建脚本通过additional_files导出。不要只压缩mysql目录。

```sh
python3 authoring/validate_course.py
python3 authoring/materialize_learner.py /tmp/c06-learner
```

Python检查依赖PyYAML6.0.2。离线纯Java检查见authoring/verify_unit.sh：需要指定JUNIT_CONSOLE_JAR，且build/deps包含HikariCP6.2.1编译依赖。不会把依赖缺失或跳过集成伪装通过。

## 证据和边界

看中文阶段报告.md区分已运行、未运行和观察项目。纯策略分类不是InnoDB模型。没有H2依赖，没有把模拟MVCC当真。C06-07同时提供真实HikariCP池压力测试、真实双MySQL GTID复制暂停/追平测试；Gate另行明确为T容量护栏，不冒充连接池。PITR提供演练清单，未把单容器重启说成完整灾备。真实集成是否执行成功以报告为准。

## 请求标识的排序规则

请求编号不是自然语言姓名。c06_orders/c06_reservation的request_id使用utf8mb4_0900_bin（NO PAD）：Case、case、case后跟空格是不同ID；同一ID不同参数仍拒绝。默认ai_ci排序规则可能把不相关请求当作重复。reset在本课旧表存在时按sql/migration-v2.sql定向迁移这两列，然后在单一事务中重建合成行；不触及其他表。生产变更应另做迁移计划和兼容评估。
