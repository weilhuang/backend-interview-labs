# 07 前端HTTP与数据库完整联调

对应完整课程：C04-07。JDK 21，Spring Boot 3.5.16 / Framework 6.2.19。先修和运行方法见课程首页；本节全部源码、调用方、测试和标准解公开。

## 企业场景

把内存练习升级为真实SpringBoot/JDBC完整服务，预置界面不改，后端以唯一约束与事务保护请求。明确多实例竞态的结果未知与重试边界。

## 实际操作与逐步编码

1. 运行预置页面与Usage，观察订单写入真实H2数据库
2. 实现Store.create的事务、重复检查、GeneratedKeyHolder
3. 用HTTP测试核对数据库真实状态
4. 对比02节内存模型和本节持久层，不把H2内存数据库当生产持久部署
5. 阅读依赖锁与迁移检查清单，解释升级Boot大版本的验证范围

**Academy导入模式**：用本题Check检查；打开Usage.java的main运行按钮，或在Gradle工具窗口执行本模块test、usage、run。归档缺少Wrapper时不要在导入目录运行./gradlew。

**源码仓库/普通Gradle副本CLI模式**：运行本节检查：`./gradlew :07-integrated-service:test`。运行完整调用方：`./gradlew :07-integrated-service:usage`。服务型示例另可执行 `./gradlew :07-integrated-service:run`，停止使用 Ctrl+C。

## 正确性合同

保留02节HTTP合同；数据库request_id唯一。并发同键竞争可能返回明确409重试提示，不能假称跨进程锁。成功后事务内的数据一致；输入错误不产生记录。H2是可重建教学数据库，MySQL部署属于共享环境集成验收。

## 核心机制与图解

```text
[预置前端] -> [Controller] -> [事务服务] -> [JdbcTemplate] -> [数据库]
                                    |                            |
                               [错误回滚]                    [唯一约束]
                                    |                            |
                                    +---------- [稳定HTTP合同] --+
```

预置前端只调用相同API，存储实现变化不应破坏契约。数据库唯一约束是多实例的最终防线；先查询再写入仍可能竞态，因此冲突必须可解释并有重试合同。升级依赖必须检查BOM、starter、测试包、Servlet/Validation兼容、配置和完整回归，不能仅改版本号。

## 固定版本源码阅读

[Boot数据源自动配置](https://github.com/spring-projects/spring-boot/blob/0566f6933049aca6bc5ffc6d559fffade9cd2e0c/spring-boot-project/spring-boot-autoconfigure/src/main/java/org/springframework/boot/autoconfigure/jdbc/DataSourceAutoConfiguration.java)与[JdbcTemplate](https://github.com/spring-projects/spring-framework/blob/6214eae8bd02c2ed7ab382bb8d16a9cc6de49522/spring-jdbc/src/main/java/org/springframework/jdbc/core/JdbcTemplate.java)。从HTTP跟到连接获取、SQL执行和事务提交。

记录入口、关键分支、输入、状态与版本。不要求背整段源码；必须说明哪条观察支持你的结论。自动测试通过不等于源码讲解已通过人工评阅。

## 渐进提示

1. 先读完整调用方与测试，写出正常、边界和失败的差别
2. 只修改标出的练习区，把合同转化为分支或框架API调用
3. 对照本节真实源码入口，解释是哪一层执行校验或事务/代理行为

## 公开标准解

下面是所有练习区的完整实现；完整文件也在项目中公开。学生起点和标准解分开，不需要解锁。

```java
      if (r.quantity() < 1 || r.quantity() > 100 || r.unitPriceFen() < 1)
        throw new IllegalArgumentException("数量或金额不合法");
      long total = Math.multiplyExact(r.quantity(), r.unitPriceFen());
      return tx.execute(
          status -> {
            var old =
                jdbc.query("select * from orders where request_id=?", this::row, r.requestId());
            if (!old.isEmpty()) {
              Order x = old.get(0);
              if (!x.sku().equals(r.sku())
                  || x.quantity() != r.quantity()
                  || x.unitPriceFen() != r.unitPriceFen()) throw new Conflict();
              return new Creation(x, false);
            }
            var key = new org.springframework.jdbc.support.GeneratedKeyHolder();
            jdbc.update(
                connection -> {
                  var statement =
                      connection.prepareStatement(
                          "insert into orders(request_id,sku,quantity,unit_price,total)"
                              + " values(?,?,?,?,?)",
                          java.sql.Statement.RETURN_GENERATED_KEYS);
                  statement.setString(1, r.requestId());
                  statement.setString(2, r.sku());
                  statement.setInt(3, r.quantity());
                  statement.setLong(4, r.unitPriceFen());
                  statement.setLong(5, total);
                  return statement;
                },
                key);
            return new Creation(
                new Order(
                    java.util.Objects.requireNonNull(key.getKey()).longValue(),
                    r.requestId(),
                    r.sku(),
                    r.quantity(),
                    r.unitPriceFen(),
                    total),
                true);
          });
```

预置前端只调用相同API，存储实现变化不应破坏契约。数据库唯一约束是多实例的最终防线；先查询再写入仍可能竞态，因此冲突必须可解释并有重试合同。升级依赖必须检查BOM、starter、测试包、Servlet/Validation兼容、配置和完整回归，不能仅改版本号。

## 面试机制 边界与取舍

- 完整服务与CRUD样例差在哪？有失败、重试、生命周期和可验证合同
- 并发先查后写为何不够？多个事务可同时看见不存在
- 如何把H2换成MySQL？配置、驱动、迁移与真实集成测试一起更换
- Boot3升级到4如何评估？先查官方迁移说明与依赖边界，本课不声称已完成Boot4运行验收

## 独立迁移与验收

不查标准解，修改一个合同边界并增加测试；再解释一个错误实现为什么会被拒绝。完成编码、诊断和追问才能记录掌握，阅读标准解不等于独立掌握。实际构建、集成、界面验收状态见课程根的中文阶段报告。
