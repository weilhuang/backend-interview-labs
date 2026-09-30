# C06-05 · 锁等待与死锁重试

## 目标、先修与企业问题

两个仓库同时把一个库存单位互相转移，按相反顺序锁行出现死锁。目标是稳定复现等待环、限制重试并证明最终守恒，同时观察RR范围锁与RC差异。

类型：A 自动正确性 + O 观察解释 + R 真实源码。本题不是 H2/内存 Map 的“数据库替代品”。纯 Java ContractTest 仅校验输入或策略分类，真实行为必须通过 DatabaseTest。

## 依赖和完整工程

本课 JDK21，制作机 Temurin21.0.12.1+1；Gradle8.10.2、JUnit5.11.4、Testcontainers1.20.6、Connector/J9.2.0。数据库镜像只从仓库 infra/versions.env 的 MYSQL_IMAGE 读取；课程不复制镜像常量。前端不需要，本课使用可见Java调用端和SQL。Docker/Academy界面验证状态见课程首页及中文阶段报告.md。

```text
05-deadlock/
+-- task.md                  本题步骤和机制
+-- src/labs/LockLab.java      编码区，作者版含标准实现
+-- src/labs/Usage.java       可直接运行的完整调用方
+-- test/*ContractTest.java  纯逻辑测试，不代表MySQL验证
+-- test/*DatabaseTest.java  真实容器集成测试，全部可见
+-- answer.md                完整公开标准解与逐步说明
课程根 support/              JDBC包装和独占容器fixture
课程根 sql/                  schema/seed/reset/只读观测SQL
```

## 核心概念与图解

```text
T1持有sku101 -> 等待sku102
T2持有sku102 -> 等待sku101
     等待环 -> InnoDB选择受害事务(1213)
改进：两事务都按101->102加锁 + 整个事务有界重试
```

记录锁、间隙锁、next-key锁的实际范围取决于索引、隔离级别和扫描条件。当前实验对主键范围[101,200)做FOR UPDATE，RR会阻止在覆盖间隙中插入150；RC对该场景一般不锁间隙，但外键检查和重复键等仍有例外。死锁并不自动说明数据库故障，是并发访问的一种可恢复结果；业务必须理解哪一整个事务被回滚。

## 逐步编码、使用和验证

1. 运行 opposingOrderCreatesRealDeadlock：两连接先各持一把锁，CyclicBarrier同时发起第二次请求；必须至少一个1213，另一个成功
2. 填写 retryable，只允许1213或1205进入本题重试；连接断开08006不能盲重试提交
3. 用 sql/observations.sql 读取data_lock_waits和锁模式，必要时记录只读诊断权限阻塞
4. 运行RR/RC范围插入对照，RR期望1205，RC插入1行；测试不以固定毫秒数断言
5. 改用swapOne升序加锁，验证库存和20；注入永久错误确认最多3次且资源关闭

从课程根执行：

```sh
./gradlew :mysql-05-locks-05-deadlock:unitTest
./gradlew :mysql-05-locks-05-deadlock:test
./gradlew :mysql-05-locks-05-deadlock:run
```

unitTest不是完整验收。test默认真正启动MySQL，不装Docker、没有daemon或镜像下载失败会报错，绝不自动skip并宣称通过。run使用已经启动的共享实验库，需要首页所列LAB_DB环境变量；没有隐式重置。首次或重复运行前显式执行首页reset命令，只删除c06_*实验表数据。

先独立修改LockLab.java的占位区；正常测试后故意破坏一个条件，记录哪条可见测试抓到它，再恢复。IDE里可直接打开全部测试和Usage。引用资源/构建不能缺文件时从仓库根保留support与sql。

## 三阶提示

1. 从测试期望写出输入、输出和必须保留的不变量，区分A和O项目
2. 沿Usage到公开方法，再到Db.prepare/transaction检查参数、资源和事务边界
3. 阅读公开answer.md，对照每个SQL谓词/返回值；看答案后必须完成末尾陌生变式

## 固定版本真实源码伴读

[MySQL mysql-8.4.7：storage/innobase/lock/lock0lock.cc](https://github.com/mysql/mysql-server/blob/mysql-8.4.7/storage/innobase/lock/lock0lock.cc)

符号：lock_rec_lock / lock_rec_insert_check_and_lock。观察锁模式、间隙插入冲突与等待状态分支；死锁检测相关路径还可进入 lock0wait.cc。请报告表名、索引名、LOCK_MODE、事务ID与阻塞关系，源码符号不能代替现场证据。

固定tag的路径与符号已通过官方mysql/mysql-server读取核验，文件SHA见SOURCES.md；行号仅用于导航，不当成永恒API。记录“入口 -> 状态字段 -> 关键条件 -> 分支 -> 本题证据”，不能只贴链接。运行的库与源代码是同系列固定版本，但未进行C++调试器单步验收。

## 标准答案与测试解释

完整实现与逐步解析就在本目录[answer.md](answer.md)，所有测试公开，允许先查阅再回测。retry每次获取新连接并从头执行事务，不是只重复失败的UPDATE。Db.transaction在1205情况下显式rollback，避免误以为锁等待超时总能自动回滚整笔事务。当前重试上限1..5，演示快速重试；生产需在同一总deadline中加入退避与抖动，不能无限叠加网络重试。转移先验证两个SKU不同，再全局升序加锁，修改总量守恒。

## 面试题与参考回答

### 1. 1205与1213区别？

前者为锁等待超时，后者为检测出的死锁受害事务；是否整笔事务自动回滚不同，应用统一显式rollback再重试。

### 2. 只有UPDATE才会死锁吗？

否，锁定读、唯一键/外键检查和多资源访问也会形成等待环，必须查看具体锁依赖。

### 3. 索引会减少锁吗？

合适的访问路径常能减少扫描与锁定范围，但具体锁依隔离级别和条件，不能简单说有索引就是行锁。

### 4. 断网后能直接重试事务吗？

提交响应丢失时结果可能未知；先靠业务幂等键/查询恢复结果，再决定重试，不把所有SQLException一视同仁。

## 独立迁移与退出标准

把两个库存扩成三个SKU转移，建立全局锁顺序；用受控连接故障验证未把结果未知当成未提交。

提交代码、完整测试输出、原始SQL/计划/时序及一页解释。每项0/1/2分：正确性、可复现故障、源码因果、边界/替代设计，共8分；至少6分且正确性与故障项非0。抄标准答案通过测试不能替代盲写变式，也不构成生产经历或面试保证。
