# C06-03 · 慢查询与稳定游标分页

## 目标、先修与企业问题

运营翻到十万页时接口很慢，订单在同一毫秒创建还会重复或遗漏。要在稳定数据集上实现完整排序键的游标分页，并把 DATE(created_at) 改为半开区间。

类型：A 自动正确性 + O 观察解释 + R 真实源码。本题不是 H2/内存 Map 的“数据库替代品”。纯 Java ContractTest 仅校验输入或策略分类，真实行为必须通过 DatabaseTest。

## 依赖和完整工程

本课 JDK21，制作机 Temurin21.0.12.1+1；Gradle8.10.2、JUnit5.11.4、Testcontainers1.20.6、Connector/J9.2.0。数据库镜像只从仓库 infra/versions.env 的 MYSQL_IMAGE 读取；课程不复制镜像常量。前端不需要，本课使用可见Java调用端和SQL。Docker/Academy界面验证状态见课程首页及中文阶段报告.md。

```text
03-pagination/
+-- task.md                  本题步骤和机制
+-- src/labs/QueryLab.java      编码区，作者版含标准实现
+-- src/labs/Usage.java       可直接运行的完整调用方
+-- test/*ContractTest.java  纯逻辑测试，不代表MySQL验证
+-- test/*DatabaseTest.java  真实容器集成测试，全部可见
+-- answer.md                完整公开标准解与逐步说明
课程根 support/              JDBC包装和独占容器fixture
课程根 sql/                  schema/seed/reset/只读观测SQL
```

## 核心概念与图解

```text
OFFSET N: 读取并丢弃N行 -> 返回M行
游标(time,id): 定位边界 -> 返回M行
同一时间: id1 -> id2 -> id3；只传time会漏掉id2
```

深 OFFSET 通常仍需要访问并丢弃前面的匹配行，游标能用排序键界定下一页。created_at 不唯一时，游标必须包含 id，条件为 time>t OR (time=t AND id>id0)。半开时间区间避免结束点重复，允许使用普通时间列索引；函数索引是另一种明确设计，不应断言任何函数必定不能用索引。跨页期间有插入、删除、修改时，不承诺全局一致快照，应定义业务语义。

## 逐步编码、使用和验证

1. 读取 QueryDatabaseTest：种子订单1、2时间相同，从(time,1)后翻页必须拿到2
2. 填写 after 的谓词、租户和稳定排序，拒绝0或超过100的page size
3. 对比 slowDay 与 onUtcDay，2025-01-01 UTC下结果均为[1,2]
4. 用 IndexLab分布数据扩到10万，记录OFFSET与游标实际扫描行数；只在受控实验库运行 EXPLAIN ANALYZE
5. 增加翻页间插入/删除的用例并陈述你选择的接口契约；不要把新记录变化误判成MySQL错误

从课程根执行：

```sh
./gradlew :mysql-03-query-03-pagination:unitTest
./gradlew :mysql-03-query-03-pagination:test
./gradlew :mysql-03-query-03-pagination:run
```

unitTest不是完整验收。test默认真正启动MySQL，不装Docker、没有daemon或镜像下载失败会报错，绝不自动skip并宣称通过。run使用已经启动的共享实验库，需要首页所列LAB_DB环境变量；没有隐式重置。首次或重复运行前显式执行首页reset命令，只删除c06_*实验表数据。

先独立修改QueryLab.java的占位区；正常测试后故意破坏一个条件，记录哪条可见测试抓到它，再恢复。IDE里可直接打开全部测试和Usage。引用资源/构建不能缺文件时从仓库根保留support与sql。

## 三阶提示

1. 从测试期望写出输入、输出和必须保留的不变量，区分A和O项目
2. 沿Usage到公开方法，再到Db.prepare/transaction检查参数、资源和事务边界
3. 阅读公开answer.md，对照每个SQL谓词/返回值；看答案后必须完成末尾陌生变式

## 固定版本真实源码伴读

[MySQL mysql-8.4.7：sql/iterators/composite_iterators.cc](https://github.com/mysql/mysql-server/blob/mysql-8.4.7/sql/iterators/composite_iterators.cc)

符号：LimitOffsetIterator::Read。查找 offset 阶段读取并丢弃输入行的循环，再看 limit 停止条件。说明少返回数据不代表上游少做了工作，并通过实际计划的行数/loops验证。

固定tag的路径与符号已通过官方mysql/mysql-server读取核验，文件SHA见SOURCES.md；行号仅用于导航，不当成永恒API。记录“入口 -> 状态字段 -> 关键条件 -> 分支 -> 本题证据”，不能只贴链接。运行的库与源代码是同系列固定版本，但未进行C++调试器单步验收。

## 标准答案与测试解释

完整实现与逐步解析就在本目录[answer.md](answer.md)，所有测试公开，允许先查阅再回测。标准解用两项比较展开完整排序，不使用只比较时间的简化。limit仍参数绑定并限制在1..100。日期优化只接受已经定义好的UTC日；86400秒不适用于直接表示任意时区的夏令时自然日。QueryLab.plan 只供受控 SELECT 实验，调用者不得把不可恢复的写语句放进去。复杂度需按索引访问与返回行数描述，不能说所有游标分页都是常数时间。

## 面试题与参考回答

### 1. LIMIT为什么不能自动修复慢查询？

LIMIT限制输出，排序、连接和前置过滤可能仍处理大量行；看执行树实际行数和循环数。

### 2. 游标API能直接跳第10000页吗？

通常不能随机跳任意页，需书签或改变产品交互；这是效率与功能的取舍。

### 3. 类型转换会导致索引失效吗？

取决于转换方向、类型、排序规则和优化器；保留参数与列类型一致，并提供具体SQL与计划。

### 4. N+1如何识别？

一次父查询后每条记录再查子项，请求次数随行数线性增长；可用批量IN/分组查询或合适JOIN，注意JOIN放大。

## 独立迁移与退出标准

新增批量加载订单明细接口，保证最多两次查询且保留空明细订单；给出统计查询次数的测试和重复行处理。

提交代码、完整测试输出、原始SQL/计划/时序及一页解释。每项0/1/2分：正确性、可复现故障、源码因果、边界/替代设计，共8分；至少6分且正确性与故障项非0。抄标准答案通过测试不能替代盲写变式，也不构成生产经历或面试保证。
