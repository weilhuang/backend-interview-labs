# C06-06 · 日志职责与重启恢复

## 目标、先修与企业问题

数据库进程被终止后，一条已确认的订单日志必须恢复，一条未提交记录不能出现。本题只杀隔离Testcontainers容器内MySQL进程，再启动同一容器，不触碰宿主机数据库。

类型：A 自动正确性 + O 观察解释 + R 真实源码。本题不是 H2/内存 Map 的“数据库替代品”。纯 Java ContractTest 仅校验输入或策略分类，真实行为必须通过 DatabaseTest。

## 依赖和完整工程

本课 JDK21，制作机 Temurin21.0.12.1+1；Gradle8.10.2、JUnit5.11.4、Testcontainers1.20.6、Connector/J9.2.0。数据库镜像只从仓库 infra/versions.env 的 MYSQL_IMAGE 读取；课程不复制镜像常量。前端不需要，本课使用可见Java调用端和SQL。Docker/Academy界面验证状态见课程首页及中文阶段报告.md。

```text
06-durability/
+-- task.md                  本题步骤和机制
+-- src/labs/RecoveryLab.java      编码区，作者版含标准实现
+-- src/labs/Usage.java       可直接运行的完整调用方
+-- test/*ContractTest.java  纯逻辑测试，不代表MySQL验证
+-- test/*DatabaseTest.java  真实容器集成测试，全部可见
+-- answer.md                完整公开标准解与逐步说明
课程根 support/              JDBC包装和独占容器fixture
课程根 sql/                  schema/seed/reset/只读观测SQL
```

## 核心概念与图解

```text
事务修改 -> redo(崩溃重做) -> 提交确认
       \-> undo(回滚/旧版本)
服务层 -> binlog(复制/PITR输入)
SIGKILL -> 同一数据目录重启 -> committed在 / pending不在
```

redo用于崩溃后恢复已经写入日志的页修改，undo支持事务回滚与一致性读旧版本；binlog记录服务层数据变更，用于复制和时间点恢复链路。刷redo、刷binlog、副本确认和备份是不同边界。设置innodb_flush_log_at_trx_commit=1和sync_binlog=1强化本机提交持久化配置，但存储设备是否兑现fsync仍有假设。一次SIGKILL不等于宿主断电、磁盘损坏或完整灾备验证。

## 逐步编码、使用和验证

1. 填写inspect，查询本机三项配置，test fixture明确开启binlog并设两个同步值1
2. 先提交id1，再在另一连接写id2但不提交；测试只终止自身拥有的容器ID
3. 重启同一容器并轮询真实SELECT1，最多90秒；确认只存在id1
4. 阅读日志恢复流程，记录容器日志中的恢复事件与实验数据结果，不能只用端口通判定恢复
5. 将策略模型改成redo=2或sync_binlog=0，解释可能损失窗口；不要把未观测到丢失写成不会丢失

从课程根执行：

```sh
./gradlew :mysql-06-recovery-06-durability:unitTest
./gradlew :mysql-06-recovery-06-durability:test
./gradlew :mysql-06-recovery-06-durability:run
```

unitTest不是完整验收。test默认真正启动MySQL，不装Docker、没有daemon或镜像下载失败会报错，绝不自动skip并宣称通过。run使用已经启动的共享实验库，需要首页所列LAB_DB环境变量；没有隐式重置。首次或重复运行前显式执行首页reset命令，只删除c06_*实验表数据。

先独立修改RecoveryLab.java的占位区；正常测试后故意破坏一个条件，记录哪条可见测试抓到它，再恢复。IDE里可直接打开全部测试和Usage。引用资源/构建不能缺文件时从仓库根保留support与sql。

## 三阶提示

1. 从测试期望写出输入、输出和必须保留的不变量，区分A和O项目
2. 沿Usage到公开方法，再到Db.prepare/transaction检查参数、资源和事务边界
3. 阅读公开answer.md，对照每个SQL谓词/返回值；看答案后必须完成末尾陌生变式

## 固定版本真实源码伴读

[MySQL mysql-8.4.7：storage/innobase/log/log0write.cc](https://github.com/mysql/mysql-server/blob/mysql-8.4.7/storage/innobase/log/log0write.cc)

符号：log_write_up_to。辨认目标LSN、写入与flush等待参数；从存储引擎提交路径追到日志等待条件。结合 sql/handler.cc 的事务协调接口理解跨引擎/服务层边界，本题不声称实现了MySQL两阶段提交。

固定tag的路径与符号已通过官方mysql/mysql-server读取核验，文件SHA见SOURCES.md；行号仅用于导航，不当成永恒API。记录“入口 -> 状态字段 -> 关键条件 -> 分支 -> 本题证据”，不能只贴链接。运行的库与源代码是同系列固定版本，但未进行C++调试器单步验收。

## 标准答案与测试解释

完整实现与逐步解析就在本目录[answer.md](answer.md)，所有测试公开，允许先查阅再回测。标准解Policy保存实际配置，strictLocalCommit只是本机配置分类，scope显式限制保证。confirmed用事务插入后commit；pending开启事务但不commit。恢复测试通过Docker API对唯一容器ID发送KILL而非remove，避免丢失其数据目录，再显式等待JDBC可用。测试末尾关闭失效连接不覆盖主要断言。容器重启保留目录不等于具备外部备份。

## 面试题与参考回答

### 1. redo与binlog可以互相替代吗？

不能，层次、用途、记录格式和恢复路径不同；协调提交需要保证它们按设计一致。

### 2. undo是否只在ROLLBACK用？

不是，一致性读旧版本也依赖undo；长事务可延迟purge并增加空间压力。

### 3. 主库提交成功能保证读副本立即看到吗？

异步复制不能；要按业务选择主库读、等待GTID、会话一致性或可接受陈旧度。

### 4. 备份成功是否等于可恢复？

应验证备份完整性、binlog保留、目标时间、恢复步骤和业务对账；必须执行隔离恢复演练。

## 独立迁移与退出标准

写一份PITR演练清单：备份点、binlog范围、目标时刻、凭据权限、隔离恢复库、对账和RTO/RPO。实际复制延迟与PITR并未由单容器测试覆盖。

提交代码、完整测试输出、原始SQL/计划/时序及一页解释。每项0/1/2分：正确性、可复现故障、源码因果、边界/替代设计，共8分；至少6分且正确性与故障项非0。抄标准答案通过测试不能替代盲写变式，也不构成生产经历或面试保证。
