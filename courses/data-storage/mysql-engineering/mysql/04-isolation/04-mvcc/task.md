# C06-04 · 隔离级别与 MVCC

## 目标、先修与企业问题

客服打开订单后，库存被另一事务更新。产品希望知道读取的是首次看到的版本还是最新提交版本。用两个真实连接按确定顺序执行，不用Java Map模拟InnoDB。

类型：A 自动正确性 + O 观察解释 + R 真实源码。本题不是 H2/内存 Map 的“数据库替代品”。纯 Java ContractTest 仅校验输入或策略分类，真实行为必须通过 DatabaseTest。

## 依赖和完整工程

本课 JDK21，制作机 Temurin21.0.12.1+1；Gradle8.10.2、JUnit5.11.4、Testcontainers1.20.6、Connector/J9.2.0。数据库镜像只从仓库 infra/versions.env 的 MYSQL_IMAGE 读取；课程不复制镜像常量。前端不需要，本课使用可见Java调用端和SQL。Docker/Academy界面验证状态见课程首页及中文阶段报告.md。

```text
04-mvcc/
+-- task.md                  本题步骤和机制
+-- src/labs/IsolationLab.java      编码区，作者版含标准实现
+-- src/labs/Usage.java       可直接运行的完整调用方
+-- test/*ContractTest.java  纯逻辑测试，不代表MySQL验证
+-- test/*DatabaseTest.java  真实容器集成测试，全部可见
+-- answer.md                完整公开标准解与逐步说明
课程根 support/              JDBC包装和独占容器fixture
课程根 sql/                  schema/seed/reset/只读观测SQL
```

## 核心概念与图解

```text
会话A(RR/RC)                 会话B
BEGIN
普通读quantity=10 -> 建立视图
                            UPDATE=11; COMMIT
普通读 RR=10 / RC=11
FOR UPDATE=11 -> 当前锁定读
ROLLBACK
```

一致性非锁定读通过Read View选择可见的记录版本，必要时沿undo版本链回溯。RR通常在第一次一致性读建立视图并复用；RC每条一致性读使用新的快照。事务自己的写入可见，因此不能把事务内所有结果描述成简单的历史数据库快照。锁定读、UPDATE使用当前版本和锁语义，不能从RR快照读的观察推导所有操作都不出现新行。

## 逐步编码、使用和验证

1. 先预测 Trace 三项，分别运行 RC/RR真实集成用例，RR为(10,10,11)，RC为(10,11,11)
2. 填写 observe 中第二次普通读取和锁定读取，保留事务/隔离级别复位
3. 运行 first-read 时机测试：只BEGIN但未读，另一连接提交12后，首次普通读可见12
4. 运行自己的未提交写与其他连接读测试，验证读己之写与不脏读
5. 画出Read View、事务ID、旧版本链；加入范围内新行比较快照读与锁定读，不宣称所有幻读都消失

从课程根执行：

```sh
./gradlew :mysql-04-isolation-04-mvcc:unitTest
./gradlew :mysql-04-isolation-04-mvcc:test
./gradlew :mysql-04-isolation-04-mvcc:run
```

unitTest不是完整验收。test默认真正启动MySQL，不装Docker、没有daemon或镜像下载失败会报错，绝不自动skip并宣称通过。run使用已经启动的共享实验库，需要首页所列LAB_DB环境变量；没有隐式重置。首次或重复运行前显式执行首页reset命令，只删除c06_*实验表数据。

先独立修改IsolationLab.java的占位区；正常测试后故意破坏一个条件，记录哪条可见测试抓到它，再恢复。IDE里可直接打开全部测试和Usage。引用资源/构建不能缺文件时从仓库根保留support与sql。

## 三阶提示

1. 从测试期望写出输入、输出和必须保留的不变量，区分A和O项目
2. 沿Usage到公开方法，再到Db.prepare/transaction检查参数、资源和事务边界
3. 阅读公开answer.md，对照每个SQL谓词/返回值；看答案后必须完成末尾陌生变式

## 固定版本真实源码伴读

[MySQL mysql-8.4.7：storage/innobase/read/read0read.cc](https://github.com/mysql/mysql-server/blob/mysql-8.4.7/storage/innobase/read/read0read.cc)

符号：ReadView::prepare / MVCC::view_open。定位 m_creator_trx_id、活跃事务集合以及视图上下界；再读 row/row0sel.cc 的 row_search_mvcc 和 row_sel_build_prev_vers_for_mysql。把“可见性判断失败 -> 构造旧版本”的路径与两连接实验关联，不要复制一个Java列表叫作MVCC。

固定tag的路径与符号已通过官方mysql/mysql-server读取核验，文件SHA见SOURCES.md；行号仅用于导航，不当成永恒API。记录“入口 -> 状态字段 -> 关键条件 -> 分支 -> 本题证据”，不能只贴链接。运行的库与源代码是同系列固定版本，但未进行C++调试器单步验收。

## 标准答案与测试解释

完整实现与逐步解析就在本目录[answer.md](answer.md)，所有测试公开，允许先查阅再回测。代码顺序本身是屏障：第一次读取完成之后才允许writer执行自动提交UPDATE，再执行第二次读取。没有依赖线程恰好调度。reader关闭自动提交前检查两连接空闲；finally rollback并恢复自动提交和原隔离级别。第二次锁定读会读取11，即便之前RR普通读是10。测试只验证列出的场景；purge、长事务undo增长和崩溃恢复是额外观察。

## 面试题与参考回答

### 1. RR快照何时建立？

本课普通BEGIN后的首次一致性读建立，不是构造Connection时；WITH CONSISTENT SNAPSHOT等显式路径要单独讨论。

### 2. Read View是不是复制所有数据？

不是，保存可见性相关事务信息，行旧版本由undo提供；因此长事务会影响旧版本回收。

### 3. RC一定比RR好吗？

RC快照更新更及时且锁行为不同，但重复读语义改变；要按业务一致性与竞争需求选择。

### 4. 如何解释快照读10而FOR UPDATE读11？

前者按Read View找可见版本，后者按当前锁定读语义访问；混用时需要理解观察的并非同一时间面。

## 独立迁移与退出标准

设计“检查余额后扣款”的反例，再改成条件UPDATE，解释隔离级别不能替代业务原子条件。

提交代码、完整测试输出、原始SQL/计划/时序及一页解释。每项0/1/2分：正确性、可复现故障、源码因果、边界/替代设计，共8分；至少6分且正确性与故障项非0。抄标准答案通过测试不能替代盲写变式，也不构成生产经历或面试保证。
