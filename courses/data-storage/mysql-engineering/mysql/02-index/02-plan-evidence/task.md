# C06-02 · 索引与执行计划

## 目标、先修与企业问题

订单列表查询持续变慢。先按固定分布生成2000条订单，99%属于租户7，付款状态有偏斜；再研究联合索引，保留相同查询结果。执行计划和耗时属于 O 观察，不靠一台机器上的毫秒阈值判分。

类型：A 自动正确性 + O 观察解释 + R 真实源码。本题不是 H2/内存 Map 的“数据库替代品”。纯 Java ContractTest 仅校验输入或策略分类，真实行为必须通过 DatabaseTest。

## 依赖和完整工程

本课 JDK21，制作机 Temurin21.0.12.1+1；Gradle8.10.2、JUnit5.11.4、Testcontainers1.20.6、Connector/J9.2.0。数据库镜像只从仓库 infra/versions.env 的 MYSQL_IMAGE 读取；课程不复制镜像常量。前端不需要，本课使用可见Java调用端和SQL。Docker/Academy界面验证状态见课程首页及中文阶段报告.md。

```text
02-plan-evidence/
+-- task.md                  本题步骤和机制
+-- src/labs/IndexLab.java      编码区，作者版含标准实现
+-- src/labs/Usage.java       可直接运行的完整调用方
+-- test/*ContractTest.java  纯逻辑测试，不代表MySQL验证
+-- test/*DatabaseTest.java  真实容器集成测试，全部可见
+-- answer.md                完整公开标准解与逐步说明
课程根 support/              JDBC包装和独占容器fixture
课程根 sql/                  schema/seed/reset/只读观测SQL
```

## 核心概念与图解

```text
二级索引 (tenant,status,time,id)
  等值前缀 -> 时间范围 -> 按(time,id)有序输出
  索引叶包含主键 -> 缺少列时再访问聚簇索引
  EXPLAIN估计 -> EXPLAIN ANALYZE真实执行/循环数
```

InnoDB 聚簇索引的叶子存储整行；二级索引叶包含主键值，取未覆盖列可能再按主键访问。联合索引遵循字典序，但不能把“最左前缀”简化成任何情况下缺首列必定全表扫；优化器可能选其他路径。筛选、排序、返回列共同决定索引。查询中 tenant/status 等值，created_at 范围，id 是稳定排序补充；索引通常可以承载需要的列，但实际路径由统计信息和代价决定。

## 逐步编码、使用和验证

1. 先执行 IndexDatabaseTest，查看索引前 JSON 计划，记录 possible_keys/key/rows/filtered 与排序证据
2. 补齐 addIndex 的 DDL，按 tenant_id,status,created_at,id 建索引；重复调用应安全
3. 保留结果 ID 列表，运行 ANALYZE TABLE 更新统计信息，再读取实际计划
4. 把投影改成总额与客户名，重新记录覆盖/回表变化；不要修改自动测试预期为固定 key
5. 把分布改成只有1%的租户8，比较估计与实际行数，至少提交两组原始计划

从课程根执行：

```sh
./gradlew :mysql-02-index-02-plan-evidence:unitTest
./gradlew :mysql-02-index-02-plan-evidence:test
./gradlew :mysql-02-index-02-plan-evidence:run
```

unitTest不是完整验收。test默认真正启动MySQL，不装Docker、没有daemon或镜像下载失败会报错，绝不自动skip并宣称通过。run使用已经启动的共享实验库，需要首页所列LAB_DB环境变量；没有隐式重置。首次或重复运行前显式执行首页reset命令，只删除c06_*实验表数据。

先独立修改IndexLab.java的占位区；正常测试后故意破坏一个条件，记录哪条可见测试抓到它，再恢复。IDE里可直接打开全部测试和Usage。引用资源/构建不能缺文件时从仓库根保留support与sql。

## 三阶提示

1. 从测试期望写出输入、输出和必须保留的不变量，区分A和O项目
2. 沿Usage到公开方法，再到Db.prepare/transaction检查参数、资源和事务边界
3. 阅读公开answer.md，对照每个SQL谓词/返回值；看答案后必须完成末尾陌生变式

## 固定版本真实源码伴读

[MySQL mysql-8.4.7：sql/sql_optimizer.cc](https://github.com/mysql/mysql-server/blob/mysql-8.4.7/sql/sql_optimizer.cc)

符号：JOIN::optimize / test_if_skip_sort_order。跟踪优化阶段如何组织访问路径和排序判断，区分可用索引集合与最终计划。源码不是“创建索引必定使用”的保证，必须把条件和统计信息同实验计划对应。

固定tag的路径与符号已通过官方mysql/mysql-server读取核验，文件SHA见SOURCES.md；行号仅用于导航，不当成永恒API。记录“入口 -> 状态字段 -> 关键条件 -> 分支 -> 本题证据”，不能只贴链接。运行的库与源代码是同系列固定版本，但未进行C++调试器单步验收。

## 标准答案与测试解释

完整实现与逐步解析就在本目录[answer.md](answer.md)，所有测试公开，允许先查阅再回测。标准解只在索引不存在时创建，information_schema.statistics 校验列顺序。测试断言索引定义和结果不变，实际计划只验证真实执行信息存在，并完整输出供评阅。受控分布 seedDistribution 使用批量 PreparedStatement 与事务；最多10万行，避免误生成无限数据。性能报告记录版本、分布、缓存冷热和计划，不能把日志当性能基准。

## 面试题与参考回答

### 1. 联合索引列顺序怎么决定？

从查询的等值前缀、范围、排序和投影推导，同时考虑写放大与复用；不能只按选择性大小机械排序。

### 2. 覆盖索引是否等于不读表？

需要的列可从该访问路径满足时可避免一般的回表读取，但 MVCC 等内部可见性处理另有条件，使用计划和源代码描述具体场景。

### 3. 为什么不能 assert key 等于某个名字？

小表、统计变化和优化器改进可能让别的访问路径更便宜；正确性与物理计划评阅应分开。

### 4. 索引越多越好吗？

每次写入维护额外树，增加日志、页分裂、缓存占用和磁盘；需要按真实查询组合评估。

## 独立迁移与退出标准

增加商家维度和最近7天待付款查询，给出两个索引候选，比较相同负载的读写成本与计划，不用强制索引掩盖错误设计。

提交代码、完整测试输出、原始SQL/计划/时序及一页解释。每项0/1/2分：正确性、可复现故障、源码因果、边界/替代设计，共8分；至少6分且正确性与故障项非0。抄标准答案通过测试不能替代盲写变式，也不构成生产经历或面试保证。
