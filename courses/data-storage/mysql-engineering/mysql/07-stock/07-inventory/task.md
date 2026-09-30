# C06-07 · 库存并发与资源边界

## 目标、先修与企业问题

30个并发请求争抢10件库存，且同一请求被客户端重发8次。数据库必须不超卖、不重复扣减，售罄后不能遗留幂等占位；连接创建或业务异常必须归还并发预算和连接资源。

类型：A 自动正确性 + O 观察解释 + R 真实源码。本题不是 H2/内存 Map 的“数据库替代品”。纯 Java ContractTest 仅校验输入或策略分类，真实行为必须通过 DatabaseTest。

## 依赖和完整工程

本课 JDK21，制作机 Temurin21.0.12.1+1；Gradle8.10.2、JUnit5.11.4、Testcontainers1.20.6、Connector/J9.2.0。数据库镜像只从仓库 infra/versions.env 的 MYSQL_IMAGE 读取；课程不复制镜像常量。前端不需要，本课使用可见Java调用端和SQL。Docker/Academy界面验证状态见课程首页及中文阶段报告.md。

```text
07-inventory/
+-- task.md                  本题步骤和机制
+-- src/labs/StockLab.java      编码区，作者版含标准实现
+-- src/labs/Usage.java       可直接运行的完整调用方
+-- test/*ContractTest.java  纯逻辑测试，不代表MySQL验证
+-- test/*DatabaseTest.java  真实容器集成测试，全部可见
+-- answer.md                完整公开标准解与逐步说明
课程根 support/              JDBC包装和独占容器fixture
课程根 sql/                  schema/seed/reset/只读观测SQL
```

## 核心概念与图解

```text
requestId -> INSERT去重(同事务)
                  |
                  v
UPDATE stock SET qty=qty-n WHERE qty>=n
   1行 -> COMMIT     0行 -> ROLLBACK(含去重记录)
重复键 -> 核对sku/n -> 返回REPLAY；参数不同 -> 拒绝
```

先读库存再无条件写会产生竞态。单条条件UPDATE把“检查和扣减”置于同一行更新协议，受影响行数决定结果。幂等记录与扣减必须同一事务提交，否则会出现去重成功但没扣减或扣减成功但没去重。乐观版本UPDATE进一步约束观察版本，失败需要重新读取和重新判断业务，而不是无脑重试旧版本。信号量Gate只是并发容量护栏，并非实现了生产连接池。

## 逐步编码、使用和验证

1. 填写reserve的条件更新，必须同时检验sku、剩余数量并增加version；失败用异常触发整笔rollback
2. 执行30请求库存测试：APPLIED恰为10，最终库存0，reservation行数10
3. 先用一个数量为2的请求验证APPLIED、库存8、version1和参数绑定的去重行；完整reset后，再用4个线程并发发8次相同requestId：只1次APPLIED，其余7次REPLAY；用相同id不同sku/数量必须拒绝，最终库存9、version1且仅1条去重记录
4. 运行乐观锁旧版本、售罄无占位、连接创建失败和业务异常释放测试
5. 观测线程数、并发预算、查询超时与服务器max_connections；补充真实连接池集成可作为迁移，不把Gate叫池化

从课程根执行：

```sh
./gradlew :mysql-07-stock-07-inventory:unitTest
./gradlew :mysql-07-stock-07-inventory:test
./gradlew :mysql-07-stock-07-inventory:run
```

unitTest不是完整验收。test默认真正启动MySQL，不装Docker、没有daemon或镜像下载失败会报错，绝不自动skip并宣称通过。run使用已经启动的共享实验库，需要首页所列LAB_DB环境变量；没有隐式重置。首次或重复运行前显式执行首页reset命令，只删除c06_*实验表数据。

同请求并发用例先验证单请求基础能力，再测试竞争。未实现的扣减会在INSERT后回滚；多个相同键的等待者可能因此出现真正的InnoDB死锁，掩盖本应直接看到的TODO。前置断言在创建线程池前执行，且成功后重置全部合成数据，不预种并发请求的去重行、不减少8个请求或4个线程，也不捕获/放宽1213错误。它仍检验从空去重表开始的并发扣减，而非只检验已完成请求的重放。

先独立修改StockLab.java的占位区；正常测试后故意破坏一个条件，记录哪条可见测试抓到它，再恢复。IDE里可直接打开全部测试和Usage。引用资源/构建不能缺文件时从仓库根保留support与sql。

## 三阶提示

1. 从测试期望写出输入、输出和必须保留的不变量，区分A和O项目
2. 沿Usage到公开方法，再到Db.prepare/transaction检查参数、资源和事务边界
3. 阅读公开answer.md，对照每个SQL谓词/返回值；看答案后必须完成末尾陌生变式

## 固定版本真实源码伴读

[MySQL mysql-8.4.7：storage/innobase/row/row0sel.cc](https://github.com/mysql/mysql-server/blob/mysql-8.4.7/storage/innobase/row/row0sel.cc)

符号：row_search_mvcc。从锁定访问分支观察条件更新所依赖的当前行访问；结合官方UPDATE及事务手册解释受影响行数。Java包装不重新实现InnoDB行锁，真正的原子性来自服务器。

固定tag的路径与符号已通过官方mysql/mysql-server读取核验，文件SHA见SOURCES.md；行号仅用于导航，不当成永恒API。记录“入口 -> 状态字段 -> 关键条件 -> 分支 -> 本题证据”，不能只贴链接。运行的库与源代码是同系列固定版本，但未进行C++调试器单步验收。

## 标准答案与测试解释

完整实现与逐步解析就在本目录[answer.md](answer.md)，所有测试公开，允许先查阅再回测。业务先校验request和amount再连接；INSERT请求去重行后做条件UPDATE。SoldOut携带控制结果但作为SQLException触发rollback，随后返回SOLD_OUT。只有1062进入重放检查，必须比对sku和quantity，不能把任何完整性异常都称为重复请求。乐观锁比较version，成功递增。Gate用try/finally归还许可，try-with-resources关闭连接；它不缓存连接、不验证存活、不做会话复位。

## 面试题与参考回答

### 1. 为什么不先SELECT再UPDATE？

两条语句之间其他事务可能改变库存；要条件UPDATE或显式锁定并在同一事务使用。

### 2. 唯一请求ID就能保证exactly-once吗？

需要限定幂等记录与业务写处于同一事务、ID作用域与保留期、参数一致和外部副作用边界；本题只保证该数据库扣减。

### 3. 连接池越大吞吐越高吗？

过多并发会增加数据库争用和排队；容量应由服务时间、数据库预算和峰值测量确定，不能仅按应用线程数。

### 4. 乐观锁与悲观锁怎么选？

按冲突概率、重试成本、事务时长和一致性需求，观察业务不变量与尾延迟；不是乐观必然快。

## 独立迁移与退出标准

把Gate换成固定版本HikariCP，测试借用超时、故障连接、事务状态复位与泄漏；再设计读副本陈旧库存的反例和主库裁决方案。

提交代码、完整测试输出、原始SQL/计划/时序及一页解释。每项0/1/2分：正确性、可复现故障、源码因果、边界/替代设计，共8分；至少6分且正确性与故障项非0。抄标准答案通过测试不能替代盲写变式，也不构成生产经历或面试保证。

## 已提供的真实连接池与复制实验

PoolLab.java使用HikariCP6.2.1，maximumPoolSize上限8，借用超时300ms，验证超时250ms。PoolDatabaseTest先持有唯一连接，第二次借用必须以SQLTransientConnectionException在库预算内失败；归还后再次借用成功。另一用例在未提交事务中修改库存并close代理连接，下一次借用检查autoCommit已复位且库存仍10。测试不把实测耗时精确断言为300ms，避免调度噪声；全题Gradle超时仍有上限。

ReplicaDatabaseTest独享两台MySQL和专用Docker网络，镜像都读取同一MYSQL_IMAGE。使用GTID自动定位启动异步复制，先等待已知位置应用。STOP REPLICA SQL_THREAD明确暂停应用，主库从10更新到8后副本仍10；重新启动SQL线程并等待指定GTID，副本变8。它证明“主库成功不代表副本立即可见”，不声称自动故障转移或跨地域容灾。测试中root只管理自建隔离拓扑和合成复制账号，不连接共享Compose或用户服务。

```sh
./gradlew :mysql-07-stock-07-inventory:test --tests PoolDatabaseTest
./gradlew :mysql-07-stock-07-inventory:test --tests ReplicaDatabaseTest
```

```text
主库提交 quantity=8 -> binlog/GTID -> 副本IO接收 -> [SQL应用暂停]
主库读=8                                  副本读=10
START SQL_THREAD -> WAIT指定GTID -> 副本读=8
```

进一步读HikariCP固定版本ProxyConnection.close：dirty且非autoCommit时rollback，复位dirtyBits对应状态，finally recycle。连接池不是简单复用裸Connection；会话状态泄漏会影响下一位借用者。

## 请求标识的排序规则

请求编号不是自然语言姓名。c06_orders/c06_reservation的request_id使用utf8mb4_0900_bin（NO PAD）：Case、case、case后跟空格是不同ID；同一ID不同参数仍拒绝。默认ai_ci排序规则可能把不相关请求当作重复。reset在本课旧表存在时按sql/migration-v2.sql定向迁移这两列，然后在单一事务中重建合成行；不触及其他表。生产变更应另做迁移计划和兼容评估。
