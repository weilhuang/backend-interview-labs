# C06-04 公开标准答案

## 完整实现

```java
package labs;

import java.sql.*;

/** 两个真实会话按代码顺序交错，不用线程随机调度或睡眠猜测快照建立时刻。 */
public final class IsolationLab {
    public record Trace(long first, long second, long locking) {}

    private IsolationLab() {}

    public static Trace observe(Connection reader, Connection writer, int isolation)
            throws SQLException {
        if (!reader.getAutoCommit() || !writer.getAutoCommit())
            throw new SQLException("实验需要两个空闲自动提交会话");
        int old = reader.getTransactionIsolation();
        reader.setTransactionIsolation(isolation);
        reader.setAutoCommit(false);
        Throwable primary = null;
        try {
            long first = Db.scalar(reader, "SELECT quantity FROM c06_stock WHERE sku=101");
            Db.update(writer, "UPDATE c06_stock SET quantity=quantity+1 WHERE sku=101");
            // BEGIN_STUDENT
            long second = Db.scalar(reader, "SELECT quantity FROM c06_stock WHERE sku=101");
            long locking =
                    Db.scalar(reader, "SELECT quantity FROM c06_stock WHERE sku=101 FOR UPDATE");
            return new Trace(first, second, locking);
            // END_STUDENT
        } catch (SQLException | RuntimeException | Error failure) {
            primary = failure;
            throw failure;
        } finally {
            SQLException cleanup = null;
            try {
                reader.rollback();
            } catch (SQLException failure) {
                cleanup = failure;
            }
            if (cleanup == null) {
                try {
                    reader.setAutoCommit(true);
                    reader.setTransactionIsolation(old);
                } catch (SQLException failure) {
                    cleanup = failure;
                }
            }
            if (cleanup != null) {
                // 回滚或会话复位失败后丢弃连接，不让下一位调用者承担未知状态。
                try {
                    reader.close();
                } catch (SQLException close) {
                    cleanup.addSuppressed(close);
                }
                if (primary != null) primary.addSuppressed(cleanup);
                else throw cleanup;
            }
        }
    }

    public static long expectedSecond(int isolation) {
        return switch (isolation) {
            case Connection.TRANSACTION_REPEATABLE_READ -> 10;
            case Connection.TRANSACTION_READ_COMMITTED -> 11;
            default -> throw new IllegalArgumentException("这里只研究 RC/RR");
        };
    }
}
```

## 逐步解析

代码顺序本身是屏障：第一次读取完成之后才允许writer执行自动提交UPDATE，再执行第二次读取。没有依赖线程恰好调度。reader关闭自动提交前检查两连接空闲；finally rollback并恢复自动提交和原隔离级别。第二次锁定读会读取11，即便之前RR普通读是10。测试只验证列出的场景；purge、长事务undo增长和崩溃恢复是额外观察。

1. 先确认输入边界与调用者所有的连接，不能在查询辅助方法中提前关闭调用者连接
2. 所有动态值绑定到PreparedStatement；表名/语句结构为课程常量
3. 事务成功才commit，SQL或运行期异常走rollback，后续状态恢复不能悄悄改变业务结果
4. 对照本题全部ContractTest和DatabaseTest，正常结果、边界和故障都要解释
5. 源码阅读、计划、锁诊断和恢复范围属于观察验收，不用固定耗时或私有字段伪装稳定API
6. 替代方案与迁移练习见task.md，任何实现只要满足契约都可接受；不能删除测试放宽契约

## 复杂度、失败边界与替代方案

一致性非锁定读通过Read View选择可见的记录版本，必要时沿undo版本链回溯。RR通常在第一次一致性读建立视图并复用；RC每条一致性读使用新的快照。事务自己的写入可见，因此不能把事务内所有结果描述成简单的历史数据库快照。锁定读、UPDATE使用当前版本和锁语义，不能从RR快照读的观察推导所有操作都不出现新行。

设计“检查余额后扣款”的反例，再改成条件UPDATE，解释隔离级别不能替代业务原子条件。

## 调用方

```java
package labs;

/** 调用前用 Schema.main 显式重置合成数据；密码从环境读取。 */
public final class Usage {
    public static void main(String[] args) throws Exception {
        try (java.sql.Connection c = Db.local()) {
            try (java.sql.Connection other = Db.local()) {
                System.out.println(
                        IsolationLab.observe(
                                c, other, java.sql.Connection.TRANSACTION_REPEATABLE_READ));
            }
        }
    }
}
```

## 检查命令

从课程根执行 ./gradlew :mysql-04-isolation-04-mvcc:test。真实MySQL未运行时不能把纯逻辑绿灯称为完整通过。
