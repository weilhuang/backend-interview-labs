# 02 MySQL事务、并发库存与缓存边界

## 本节要交付什么

这一步把业务合同落到真正的持久化边界。插入唯一请求、条件扣库存、追加outbox必须在同一个连接和事务内完成。UPDATE inventory SET available=available-? WHERE available>=?把检查与扣减结合；先查库存再在Java里减，会在并发下破坏不变量。

遇到MySQL1062只代表请求身份已经存在，不能吞掉所有SQLException。先回滚当前事务，再锁读已有订单并比较参数。库存不足和写outbox失败都回滚订单与库存。取消锁住订单行，第一次取消归还数量、迁移版本并追加事件；重复取消直接返回。不得在这个数据库事务内做Redis、Kafka或RPC网络调用。

缓存采用旁路读取和提交后尽力失效，TTL为5秒；失败时回源。并发旧读回填仍可能短暂出现旧值，因此这个策略不宣称强一致。fresh=true、库存判定和审计都走MySQL。请实现place与cancel两个学习区，然后增加一次outbox约束失败的回滚测试。

## 先运行完整调用方

启动本检查点后，用页面原号提交2件、再提交一次；库存只下降2。改数量3观察409。缓存查询一次后取消，强一致查询立即CANCELLED。运行真实集成时40个不同请求争抢16件剩余库存，只有16个成功；缓存停止后取消仍能提交。

从课程根运行 `./gradlew :02-reliability:test :02-reliability:usage`。实际数据库与网络验收用 `./gradlew :02-reliability:integrationTest`，需要Docker。完整网页调用用 `CAPSTONE_STAGE=02-reliability scripts/course.sh start`。所有测试和调用方都可见；不需要先抄完其他阶段的学习区。

```text
事务开始
  唯一订单身份 -> 条件扣库存 -> outbox事件 -> COMMIT
       |冲突            |不足          |失败
       +--> 查原结果     +------ ROLLBACK -----+
COMMIT之后：缓存失效 / HTTP应答可能丢失；业务事实不回滚
```

## 完整项目在哪里

本节只替换 `src/labs/capstone/OrderService.java`。公共应用在 `app/src/main/java/labs/capstone/`，中文页面在 `app/src/main/resources/static/index.html`，五个公开标准实现在 `reference/<阶段名>/src/labs/capstone/`。每个标准实现使用独立源码根；Gradle和IDEA只为本节加入其余四阶段的标准实现，本节同名类始终来自学习区，防止测试绕过你的实现。`test/`与`integration-test/`是本节测试；`shared/`是可见的公共测试支撑。根README给出完整结构、接口与启动依赖。

## 逐步动手

1. 在纸上写出本节的失败分支，先预测每次调用是否允许推进状态
2. 运行现有测试，逐个实现学习区；为一个边界补充可见测试
3. 用Usage或页面实际调用，再运行真实集成；记录编译、快测、容器、浏览器各自结果
4. 不看下方答案，解释一个错误实现为什么会被你的新测试拒绝

## 递进提示

1. 先让所有写入共享同一个Connection，关闭自动提交，并给每条失败路径安排rollback。
2. 唯一键冲突不能证明参数相同；回滚后用FOR UPDATE读取已提交结果。
3. 取消必须先锁订单再归还库存。缓存失效和故障注入放在commit之后。

## 核心源码与断点证据

阅读[Spring6.2.19 DataSourceTransactionManager.doBegin/doCommit/doRollback](https://github.com/spring-projects/spring-framework/blob/v6.2.19/spring-jdbc/src/main/java/org/springframework/jdbc/datasource/DataSourceTransactionManager.java)与[MySQL8.4 InnoDB锁说明](https://dev.mysql.com/doc/refman/8.4/en/innodb-locking.html)。本实验故意使用显式JDBC事务暴露边界，不声称用了@Transactional。对照源码中的autoCommit切换，在place的executeUpdate、commit与rollback打断点；记录outbox写失败时三个表都不改变的证据。EXPLAIN订单主键查询与outbox_pending索引查询，解释唯一查找与批量扫描的区别。

## 面试递进

**机制：事务为什么不能跨HTTP与Kafka自动生效？**

本地数据库事务只能约束该连接上的数据库修改，远端确认是另一个持久化边界。

**边界：commit成功但客户端没收到200怎么办？**

保留原请求号查询或重试；同号参数校验返回原状态。超时只表示客户端不知道结果。

**取舍：为什么不用Redis分布式锁防超卖？**

库存事实在MySQL，条件更新和约束直接保护它；加锁不能替代事务，反而增加租约过期窗口。

**追问：8连接池够不够？**

先测事务持有时间、到达率、竞争热点与超时，再给容量依据。这个数字只是课堂预算，不是生产推荐。

## 标准答案与解释（直接可读）

下面是完整作者实现，不依赖折叠渲染或解锁。先对照关键分支，再重新独立实现；公开答案不会被导出排除。

```java
package labs.capstone;

import static labs.capstone.Model.*;

import java.sql.*;

/** C14-02：请求身份、库存和outbox在一个MySQL事务中提交。 */
public final class OrderService {
    private final Database db;
    private final OrderCache cache;

    public OrderService(Database db, OrderCache cache) {
        this.db = db;
        this.cache = cache;
    }

    public Order place(Command command, Fault fault) throws SQLException {
        OrderRules.validate(command);
        Order result;
        // 学习区开始
        try (Connection c = db.open()) {
            c.setAutoCommit(false);
            try {
                // 先插入唯一请求身份。同一身份的并发请求会等待前一事务结束。
                try (PreparedStatement p =
                        c.prepareStatement("INSERT INTO orders VALUES(?,?,?,'RESERVED',1)")) {
                    p.setString(1, command.requestId());
                    p.setString(2, command.sku());
                    p.setInt(3, command.quantity());
                    p.executeUpdate();
                } catch (SQLException duplicate) {
                    if (duplicate.getErrorCode() != 1062) throw duplicate;
                    c.rollback();
                    Order existing = Database.readOrder(c, command.requestId(), true);
                    if (existing == null) throw duplicate;
                    result = OrderRules.sameRequest(existing, command);
                    c.commit();
                    return result;
                }
                try (PreparedStatement p =
                        c.prepareStatement(
                                "UPDATE inventory SET available=available-? WHERE sku=? AND"
                                    + " available>=?")) {
                    p.setInt(1, command.quantity());
                    p.setString(2, command.sku());
                    p.setInt(3, command.quantity());
                    if (p.executeUpdate() != 1) throw new Conflict("库存不足或商品不存在");
                }
                result =
                        new Order(
                                command.requestId(),
                                command.sku(),
                                command.quantity(),
                                "RESERVED",
                                1);
                append(c, Event.of(result));
                c.commit();
            } catch (SQLException | RuntimeException failure) {
                c.rollback();
                throw failure;
            }
        }
        // 学习区结束
        cache.invalidate(result.requestId());
        if (fault == Fault.AFTER_ORDER_COMMIT) throw new Unknown("数据库已提交但响应丢失；只能用原请求号查询或重试");
        return result;
    }

    public Order cancel(String id) throws SQLException {
        OrderRules.identifier(id, "请求号");
        Order result;
        // 学习区开始
        try (Connection c = db.open()) {
            c.setAutoCommit(false);
            try {
                Order current = Database.readOrder(c, id, true);
                if (current == null) throw new Conflict("订单不存在");
                if (!OrderRules.mayCancel(current.status())) {
                    c.commit();
                    return current;
                }
                try (PreparedStatement p =
                        c.prepareStatement(
                                "UPDATE inventory SET available=available+? WHERE sku=?")) {
                    p.setInt(1, current.quantity());
                    p.setString(2, current.sku());
                    p.executeUpdate();
                }
                try (PreparedStatement p =
                        c.prepareStatement(
                                "UPDATE orders SET status='CANCELLED',version=version+1 WHERE"
                                    + " request_id=?")) {
                    p.setString(1, id);
                    p.executeUpdate();
                }
                result = new Order(id, current.sku(), current.quantity(), "CANCELLED", 2);
                append(c, Event.of(result));
                c.commit();
            } catch (SQLException | RuntimeException failure) {
                c.rollback();
                throw failure;
            }
        }
        // 学习区结束
        cache.invalidate(id);
        return result;
    }

    static void append(Connection c, Event event) throws SQLException {
        try (PreparedStatement p =
                c.prepareStatement(
                        "INSERT INTO outbox(event_id,request_id,payload) VALUES(?,?,?)")) {
            p.setString(1, event.eventId());
            p.setString(2, event.requestId());
            p.setString(3, Json.write(event));
            p.executeUpdate();
        }
    }

    public Order find(String id, boolean fresh) throws SQLException {
        OrderRules.identifier(id, "请求号");
        if (!fresh) {
            Order hit = cache.get(id);
            if (hit != null) return hit;
        }
        try (Connection c = db.open()) {
            Order order = Database.readOrder(c, id, false);
            if (order != null && !fresh) cache.put(order);
            return order;
        }
    }
}
```

为什么这样实现：前面定义的业务状态、失败边界与源码分支必须对应到代码；每次确认都只能声明它前面的效果已经完成。测试既检查返回值，也检查持久化事实和不会发生的副作用。模仿代码排版不是目标，能用不同写法维持相同合同才算通过。
