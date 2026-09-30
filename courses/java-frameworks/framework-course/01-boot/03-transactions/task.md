# 03 JDBC事务与失败原子性

对应完整课程：C04-03。JDK 21，Spring Boot 3.5.16 / Framework 6.2.19。先修和运行方法见课程首页；本节全部源码、调用方、测试和标准解公开。

## 企业场景

创建订单同时扣库存。写入订单失败时必须恢复库存；不能把方法返回失败却已扣库存的状态留给用户。

## 实际操作与逐步编码

1. Usage通过真实H2数据库执行一笔订单
2. 实现Service.place中的TransactionTemplate边界
3. 在扣库存后注入异常，验证库存与订单同时回滚
4. 观察相同请求重试与库存不足
5. 可选MySQL真实集成由共享镜像驱动，Docker未启动不能记录通过

运行本节检查：`./gradlew :03-transactions:test`。运行完整调用方：`./gradlew :03-transactions:usage`。服务型示例另可执行 `./gradlew :03-transactions:run`，停止使用 Ctrl+C。

## 正确性合同

数量必须正数；库存初始10。成功创建同时扣减；任何异常全部回滚。相同requestId/quantity重试不重复扣减；同键不同数量冲突失败。H2仅证明本节Spring/JDBC事务，不替代MySQL的MVCC/锁语义。

## 核心机制与图解

```text
[事务开始] -> [查重] -> [条件扣库存] -> [插入订单] -> [提交]
                             |              |
                             +-- 任一步失败 -+
                                      |
                                      v
                              [库存与订单同时回滚]
```

事务必须包含读取请求状态、条件扣减和插入订单。数据库连接由Spring绑定到当前事务，JdbcTemplate复用该连接；不是分别new连接。异常必须穿过事务边界才能按规则回滚。重复键竞态的生产处理还需数据库唯一约束和重试设计。

## 固定版本源码阅读

[TransactionTemplate.execute](https://github.com/spring-projects/spring-framework/blob/6214eae8bd02c2ed7ab382bb8d16a9cc6de49522/spring-tx/src/main/java/org/springframework/transaction/support/TransactionTemplate.java) → PlatformTransactionManager；[DataSourceTransactionManager](https://github.com/spring-projects/spring-framework/blob/6214eae8bd02c2ed7ab382bb8d16a9cc6de49522/spring-jdbc/src/main/java/org/springframework/jdbc/datasource/DataSourceTransactionManager.java)跟踪连接绑定、提交与回滚。

记录入口、关键分支、输入、状态与版本。不要求背整段源码；必须说明哪条观察支持你的结论。自动测试通过不等于源码讲解已通过人工评阅。

## 渐进提示

1. 先读完整调用方与测试，写出正常、边界和失败的差别
2. 只修改标出的练习区，把合同转化为分支或框架API调用
3. 对照本节真实源码入口，解释是哪一层执行校验或事务/代理行为

## 公开标准解

下面是所有练习区的完整实现；完整文件也在项目中公开。学生起点和标准解分开，不需要解锁。

```java
      if (requestId == null || requestId.isBlank() || quantity < 1)
        throw new IllegalArgumentException("请求编号与数量不合法");
      tx.executeWithoutResult(
          status -> {
            var previous =
                jdbc.queryForList(
                    "select quantity from orders where request_id=?", Integer.class, requestId);
            if (!previous.isEmpty()) {
              if (previous.get(0) != quantity) throw new IllegalArgumentException("同一编号内容冲突");
              return;
            }
            int updated =
                jdbc.update(
                    "update stock set remaining=remaining-? where sku='BOOK' and remaining>=?",
                    quantity,
                    quantity);
            if (updated != 1) throw new IllegalStateException("库存不足");
            if (failAfterDebit) throw new IllegalStateException("模拟扣库存后写入失败");
            jdbc.update("insert into orders(request_id,quantity) values(?,?)", requestId, quantity);
          });
```

事务必须包含读取请求状态、条件扣减和插入订单。数据库连接由Spring绑定到当前事务，JdbcTemplate复用该连接；不是分别new连接。异常必须穿过事务边界才能按规则回滚。重复键竞态的生产处理还需数据库唯一约束和重试设计。

## 面试机制 边界与取舍

- 为什么不能把事务只包在insert上？库存修改会落在事务外
- TransactionTemplate和@Transactional怎么选？前者边界显式，后者依赖代理；追问自调用
- 为什么H2通过不能证明MySQL所有行为？实现、方言、锁与隔离不同
- 库存不足如何防止负库存？条件更新并检查影响行数

## 独立迁移与验收

不查标准解，修改一个合同边界并增加测试；再解释一个错误实现为什么会被拒绝。完成编码、诊断和追问才能记录掌握，阅读标准解不等于独立掌握。实际构建、集成、界面验收状态见课程根的中文阶段报告。
