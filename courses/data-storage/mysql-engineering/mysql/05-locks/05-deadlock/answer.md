# C06-05 公开标准答案

## 完整实现

```java
package labs;

import java.sql.*;

/** 只在明确死锁/锁等待错误上重试整个新事务；连接中断的提交结果可能未知。 */
public final class LockLab {
    private LockLab() {}

    public static boolean retryable(SQLException e) {
        // BEGIN_STUDENT
        return e.getErrorCode() == 1213 || e.getErrorCode() == 1205;
        // END_STUDENT
    }

    public static <T> T retry(Db.ConnectionFactory factory, int maxAttempts, Db.Work<T> work)
            throws SQLException {
        if (maxAttempts < 1 || maxAttempts > 5) throw new IllegalArgumentException("尝试次数必须为 1 到 5");
        for (int i = 1; ; i++)
            try (Connection c = factory.open()) {
                return Db.transaction(c, work);
            } catch (SQLException e) {
                if (i >= maxAttempts || !retryable(e)) throw e;
            }
    }

    public static void lockSku(Connection c, long sku) throws SQLException {
        Db.scalar(c, "SELECT quantity FROM c06_stock WHERE sku=? FOR UPDATE", sku);
    }

    public static void swapOne(Connection c, long from, long to) throws SQLException {
        if (from == to) throw new IllegalArgumentException("两个库存编号必须不同");
        // 全局按主键升序加锁，是本例消除相反顺序环路的办法。
        lockSku(c, Math.min(from, to));
        lockSku(c, Math.max(from, to));
        if (Db.update(
                        c,
                        "UPDATE c06_stock SET quantity=quantity-1 WHERE sku=? AND quantity>0",
                        from)
                != 1) throw new SQLException("源库存不足");
        Db.update(c, "UPDATE c06_stock SET quantity=quantity+1 WHERE sku=?", to);
    }
}
```

## 逐步解析

retry每次获取新连接并从头执行事务，不是只重复失败的UPDATE。Db.transaction在1205情况下显式rollback，避免误以为锁等待超时总能自动回滚整笔事务。当前重试上限1..5，演示快速重试；生产需在同一总deadline中加入退避与抖动，不能无限叠加网络重试。转移先验证两个SKU不同，再全局升序加锁，修改总量守恒。

1. 先确认输入边界与调用者所有的连接，不能在查询辅助方法中提前关闭调用者连接
2. 所有动态值绑定到PreparedStatement；表名/语句结构为课程常量
3. 事务成功才commit，SQL或运行期异常走rollback，后续状态恢复不能悄悄改变业务结果
4. 对照本题全部ContractTest和DatabaseTest，正常结果、边界和故障都要解释
5. 源码阅读、计划、锁诊断和恢复范围属于观察验收，不用固定耗时或私有字段伪装稳定API
6. 替代方案与迁移练习见task.md，任何实现只要满足契约都可接受；不能删除测试放宽契约

## 复杂度、失败边界与替代方案

记录锁、间隙锁、next-key锁的实际范围取决于索引、隔离级别和扫描条件。当前实验对主键范围[101,200)做FOR UPDATE，RR会阻止在覆盖间隙中插入150；RC对该场景一般不锁间隙，但外键检查和重复键等仍有例外。死锁并不自动说明数据库故障，是并发访问的一种可恢复结果；业务必须理解哪一整个事务被回滚。

把两个库存扩成三个SKU转移，建立全局锁顺序；用受控连接故障验证未把结果未知当成未提交。

## 调用方

```java
package labs;

/** 调用前用 Schema.main 显式重置合成数据；密码从环境读取。 */
public final class Usage {
    public static void main(String[] args) throws Exception {
        try (java.sql.Connection c = Db.local()) {
            Db.transaction(
                    c,
                    tx -> {
                        LockLab.swapOne(tx, 101, 102);
                        return null;
                    });
            System.out.println("总库存=" + Db.scalar(c, "SELECT SUM(quantity) FROM c06_stock"));
        }
    }
}
```

## 检查命令

从课程根执行 ./gradlew :mysql-05-locks-05-deadlock:test。真实MySQL未运行时不能把纯逻辑绿灯称为完整通过。
