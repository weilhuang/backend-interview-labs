# C06-07 公开标准答案

## 完整实现

```java
package labs;

import java.sql.*;
import java.util.concurrent.Semaphore;

/** 请求去重和扣库存写入同一事务。请求 ID 必须绑定参数，重复键不可掩盖参数冲突。 */
public final class StockLab {
    public enum Result {
        APPLIED,
        REPLAY,
        SOLD_OUT
    }

    private StockLab() {}

    public static Result reserve(Db.ConnectionFactory factory, String request, long sku, int amount)
            throws SQLException {
        if (request == null || request.isBlank() || request.length() > 80 || amount <= 0)
            throw new IllegalArgumentException("请求编号长度为 1 到 80，数量必须为正");
        try (Connection c = factory.open()) {
            try {
                return Db.transaction(
                        c,
                        tx -> {
                            Db.update(
                                    tx,
                                    "INSERT INTO c06_reservation(request_id,sku,quantity)"
                                        + " VALUES(?,?,?)",
                                    request,
                                    sku,
                                    amount);
                            // BEGIN_STUDENT
                            int changed =
                                    Db.update(
                                            tx,
                                            "UPDATE c06_stock SET"
                                                + " quantity=quantity-?,version=version+1 WHERE"
                                                + " sku=? AND quantity>=?",
                                            amount,
                                            sku,
                                            amount);
                            if (changed != 1) throw new SoldOut();
                            return Result.APPLIED;
                            // END_STUDENT
                        });
            } catch (SoldOut e) {
                return Result.SOLD_OUT;
            } catch (SQLException e) {
                if (e.getErrorCode() != 1062) throw e;
                try (PreparedStatement p =
                                Db.prepare(
                                        c,
                                        "SELECT sku,quantity FROM c06_reservation WHERE"
                                            + " request_id=?",
                                        request);
                        ResultSet r = p.executeQuery()) {
                    if (!r.next()) throw e;
                    if (r.getLong(1) != sku || r.getInt(2) != amount)
                        throw new IllegalArgumentException("同一个请求编号不能对应不同扣减参数");
                    return Result.REPLAY;
                }
            }
        }
    }

    private static final class SoldOut extends SQLException {}

    public static boolean optimistic(Connection c, long sku, long version, int amount)
            throws SQLException {
        if (amount <= 0) throw new IllegalArgumentException("数量必须为正");
        return Db.update(
                        c,
                        "UPDATE c06_stock SET quantity=quantity-?,version=version+1 WHERE sku=? AND"
                            + " version=? AND quantity>=?",
                        amount,
                        sku,
                        version,
                        amount)
                == 1;
    }

    /** 容量护栏是教学简化，不是连接池：真正池化还要处理连接健康与会话状态复位。 */
    public static final class Gate {
        private final Semaphore permits;

        public Gate(int n) {
            if (n < 1) throw new IllegalArgumentException("并发上限必须为正");
            permits = new Semaphore(n);
        }

        public <T> T run(Db.ConnectionFactory factory, Db.Work<T> work) throws SQLException {
            if (!permits.tryAcquire()) throw new SQLException("数据库并发预算已满");
            try (Connection c = factory.open()) {
                return work.run(c);
            } finally {
                permits.release();
            }
        }

        public int available() {
            return permits.availablePermits();
        }
    }
}
```

## 逐步解析

业务先校验request和amount再连接；INSERT请求去重行后做条件UPDATE。SoldOut携带控制结果但作为SQLException触发rollback，随后返回SOLD_OUT。只有1062进入重放检查，必须比对sku和quantity，不能把任何完整性异常都称为重复请求。乐观锁比较version，成功递增。Gate用try/finally归还许可，try-with-resources关闭连接；它不缓存连接、不验证存活、不做会话复位。

1. 先确认输入边界与调用者所有的连接，不能在查询辅助方法中提前关闭调用者连接
2. 所有动态值绑定到PreparedStatement；表名/语句结构为课程常量
3. 事务成功才commit，SQL或运行期异常走rollback，后续状态恢复不能悄悄改变业务结果
4. 对照本题全部ContractTest和DatabaseTest，正常结果、边界和故障都要解释
5. 源码阅读、计划、锁诊断和恢复范围属于观察验收，不用固定耗时或私有字段伪装稳定API
6. 替代方案与迁移练习见task.md，任何实现只要满足契约都可接受；不能删除测试放宽契约

## 复杂度、失败边界与替代方案

先读库存再无条件写会产生竞态。单条条件UPDATE把“检查和扣减”置于同一行更新协议，受影响行数决定结果。幂等记录与扣减必须同一事务提交，否则会出现去重成功但没扣减或扣减成功但没去重。乐观版本UPDATE进一步约束观察版本，失败需要重新读取和重新判断业务，而不是无脑重试旧版本。信号量Gate只是并发容量护栏，并非实现了生产连接池。

把Gate换成固定版本HikariCP，测试借用超时、故障连接、事务状态复位与泄漏；再设计读副本陈旧库存的反例和主库裁决方案。

## 调用方

```java
package labs;

/** 调用前用 Schema.main 显式重置合成数据；密码从环境读取。 */
public final class Usage {
    public static void main(String[] args) throws Exception {
        try (java.sql.Connection c = Db.local()) {
            System.out.println(StockLab.reserve(Db::local, "usage-one", 101, 1));
            System.out.println(
                    "剩余=" + Db.scalar(c, "SELECT quantity FROM c06_stock WHERE sku=101"));
        }
    }
}
```

## 检查命令

从课程根执行 ./gradlew :mysql-07-stock-07-inventory:test。真实MySQL未运行时不能把纯逻辑绿灯称为完整通过。

同请求并发测试先提交一个数量为2的基础请求，并从新连接检查库存8、version1和绑定参数的去重行；成功后完整reset，才运行原来的8请求、4线程场景。并发阶段必须得到1次APPLIED、7次REPLAY，参数冲突被拒绝，最终库存9、version1且只留1条去重记录。这个顺序让未完成的代码先暴露直接的TODO，不让其并发INSERT回滚引发的真实死锁遮住学习者错误；没有降低竞争，也没有忽略数据库异常。

本题reserve保留单次事务接口，不自动重试1213或连接错误。[MySQL 8.4错误处理说明](https://dev.mysql.com/doc/refman/8.4/en/innodb-error-handling.html)要求已确认死锁回滚后重试整笔事务；如果把本题扩展为生产重试接口，应设置有限次数、退避及新连接，并重新执行去重和扣减。COMMIT应答丢失或连接异常不能据此推定未提交，不能盲目重试；必须先按请求ID核对结果。当前测试中的1213仍作为真实失败上报，单请求基线不证明任意负载下都不会死锁。

## 其他完整实现

### PoolLab.java

```java
package labs;

import com.zaxxer.hikari.HikariConfig;
import com.zaxxer.hikari.HikariDataSource;

/** 真实HikariCP连接池实验。借用超时、连接数与生命周期都有明确上限。 */
public final class PoolLab {
    private PoolLab() {}

    public static HikariDataSource create(String jdbc, String user, String password, int maximum) {
        if (maximum < 1 || maximum > 8) throw new IllegalArgumentException("教学连接池上限必须在1到8之间");
        HikariConfig config = new HikariConfig();
        config.setJdbcUrl(jdbc);
        config.setUsername(user);
        config.setPassword(password);
        config.setMaximumPoolSize(maximum);
        config.setMinimumIdle(0);
        config.setConnectionTimeout(300);
        config.setValidationTimeout(250);
        config.setPoolName("c06-实验连接池");
        config.setAutoCommit(true);
        return new HikariDataSource(config);
    }
}
```

