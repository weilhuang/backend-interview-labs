# C06-01 · 数据模型与 SQL 契约

## 目标、先修与企业问题

电商报表按租户统计已付款金额与 SKU 数量。金额 15.00 元存成 1500 分，UTC 时间存入 DATETIME(6)。NEW 订单不能计入收入，同一订单的两条明细不能让订单总额被加两遍。先修是 Java 异常、集合和 try-with-resources；SQL 从本题建立。

类型：A 自动正确性 + O 观察解释 + R 真实源码。本题不是 H2/内存 Map 的“数据库替代品”。纯 Java ContractTest 仅校验输入或策略分类，真实行为必须通过 DatabaseTest。

## 依赖和完整工程

本课 JDK21，制作机 Temurin21.0.12.1+1；Gradle8.10.2、JUnit5.11.4、Testcontainers1.20.6、Connector/J9.2.0。数据库镜像只从仓库 infra/versions.env 的 MYSQL_IMAGE 读取；课程不复制镜像常量。前端不需要，本课使用可见Java调用端和SQL。Docker/Academy界面验证状态见课程首页及中文阶段报告.md。

```text
01-order-contract/
+-- task.md                  本题步骤和机制
+-- src/labs/OrderQueries.java      编码区，作者版含标准实现
+-- src/labs/Usage.java       可直接运行的完整调用方
+-- test/*ContractTest.java  纯逻辑测试，不代表MySQL验证
+-- test/*DatabaseTest.java  真实容器集成测试，全部可见
+-- answer.md                完整公开标准解与逐步说明
课程根 support/              JDBC包装和独占容器fixture
课程根 sql/                  schema/seed/reset/只读观测SQL
```

## 核心概念与图解

```text
客户1 --< 订单1(1500分) --< 明细101(2件)
                        --< 明细102(1件)
租户7 -> WHERE过滤 -> GROUP BY/SUM -> 只返回本租户汇总
```

关系模型通过主键标识行，外键约束引用存在，唯一键约束同租户请求号不重复。主外键不能自动防止跨租户关联：本例写入 fixture 固定正确，生产创建接口还须校验客户租户或使用复合外键。JOIN 会扩展行数，因此对订单金额求和要在订单粒度进行，不能在明细 JOIN 后直接 SUM(o.total_cents)。整数分防止二进制浮点误差；cents 用 longValueExact 拒绝小数分和溢出，而不是悄悄四舍五入。

## 逐步编码、使用和验证

1. 打开 sql/schema.sql，解释三类约束；通过 reset 重建4张业务表与2张后续实验表的合成数据
2. 运行 Usage，应看到租户7总分3500，SKU101数量2、SKU102数量3；租户8的500分不应混入
3. 填写 paidTotal 的参数化聚合语句；运行 OrderDatabaseTest，观察故意错误 JOIN 的结果5000
4. 尝试重复请求号、缺失订单外键、负库存，记录 SQL 异常及未损坏行数
5. 自己增加零订单租户与金额0.001输入测试；不能只通过一个正常样例

从课程根执行：

```sh
./gradlew :mysql-01-model-01-order-contract:unitTest
./gradlew :mysql-01-model-01-order-contract:test
./gradlew :mysql-01-model-01-order-contract:run
```

unitTest不是完整验收。test默认真正启动MySQL，不装Docker、没有daemon或镜像下载失败会报错，绝不自动skip并宣称通过。run使用已经启动的共享实验库，需要首页所列LAB_DB环境变量；没有隐式重置。首次或重复运行前显式执行首页reset命令，只删除c06_*实验表数据。

先独立修改OrderQueries.java的占位区；正常测试后故意破坏一个条件，记录哪条可见测试抓到它，再恢复。IDE里可直接打开全部测试和Usage。引用资源/构建不能缺文件时从仓库根保留support与sql。

## 三阶提示

1. 从测试期望写出输入、输出和必须保留的不变量，区分A和O项目
2. 沿Usage到公开方法，再到Db.prepare/transaction检查参数、资源和事务边界
3. 阅读公开answer.md，对照每个SQL谓词/返回值；看答案后必须完成末尾陌生变式

## 固定版本真实源码伴读

[MySQL mysql-8.4.7：storage/innobase/row/row0ins.cc](https://github.com/mysql/mysql-server/blob/mysql-8.4.7/storage/innobase/row/row0ins.cc)

符号：row_ins_check_foreign_constraint。先定位外键索引查询和错误返回分支，解释为什么有外键不等于有跨租户授权。约束错误导致语句失败；本课 Db.transaction 负责整个业务事务回滚。

固定tag的路径与符号已通过官方mysql/mysql-server读取核验，文件SHA见SOURCES.md；行号仅用于导航，不当成永恒API。记录“入口 -> 状态字段 -> 关键条件 -> 分支 -> 本题证据”，不能只贴链接。运行的库与源代码是同系列固定版本，但未进行C++调试器单步验收。

## 标准答案与测试解释

完整实现与逐步解析就在本目录[answer.md](answer.md)，所有测试公开，允许先查阅再回测。paidTotal 的 tenant 参数通过 PreparedStatement 绑定，字符串拼接不会出现在查询条件中。COALESCE 把空集合 SUM 的 NULL 转为0。quantities 从支付订单 JOIN 明细，在 SKU 粒度聚合，返回只读 Map。对连接不擅自 close，因为连接属于调用者；PreparedStatement/ResultSet 归方法所有并自动关闭。查询成本取决于行数与索引，不宣称固定 O(1)。

## 面试题与参考回答

### 1. 唯一约束能否代替业务幂等？

不能。它只能判断键重复；还要验证请求参数一致、恢复先前结果并定义保留时间。C06-07会实现。

### 2. 为什么错误 JOIN 汇总是5000？

订单1有两条明细，1500被计两次，再加订单3的2000。正确汇总要选择正确粒度。

### 3. DATETIME 是否自动携带时区？

不携带。课程约定 UTC，驱动会话也设置 UTC；展示层转换，跨夏令时的本地日范围应先计算 UTC 边界。

### 4. 为什么不用 double 表示金额？

二进制浮点不能精确表示很多十进制金额；用整数最小单位或明确精度与舍入规则的 DECIMAL/BigDecimal。

## 独立迁移与退出标准

新增退款状态与部分退款明细，定义净收入粒度，写出防重复退款约束和异常回滚测试，不得简单把 PAID 改成 NOT NEW。

提交代码、完整测试输出、原始SQL/计划/时序及一页解释。每项0/1/2分：正确性、可复现故障、源码因果、边界/替代设计，共8分；至少6分且正确性与故障项非0。抄标准答案通过测试不能替代盲写变式，也不构成生产经历或面试保证。

## 请求标识的排序规则

请求编号不是自然语言姓名。c06_orders/c06_reservation的request_id使用utf8mb4_0900_bin（NO PAD）：Case、case、case后跟空格是不同ID；同一ID不同参数仍拒绝。默认ai_ci排序规则可能把不相关请求当作重复。reset在本课旧表存在时按sql/migration-v2.sql定向迁移这两列，然后在单一事务中重建合成行；不触及其他表。生产变更应另做迁移计划和兼容评估。
