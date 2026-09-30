# C06-06 公开标准答案

## 完整实现

```java
package labs;

import java.sql.*;

/** 日志配置观察器；不把配置值或一次重启误称为断电/介质损坏证明。 */
public final class RecoveryLab {
    public record Policy(int redoFlush, int binlogSync, boolean binlogEnabled) {
        public boolean strictLocalCommit() {
            return redoFlush == 1 && binlogSync == 1 && binlogEnabled;
        }

        public String scope() {
            return "只讨论本机日志提交设置；复制、存储硬件与备份另行验证";
        }
    }

    private RecoveryLab() {}

    public static Policy inspect(Connection c) throws SQLException {
        // BEGIN_STUDENT
        return new Policy(
                (int) Db.scalar(c, "SELECT @@innodb_flush_log_at_trx_commit"),
                (int) Db.scalar(c, "SELECT @@sync_binlog"),
                Db.scalar(c, "SELECT @@log_bin") == 1);
        // END_STUDENT
    }

    public static void confirmed(Connection c, long id) throws SQLException {
        Db.transaction(
                c,
                tx -> {
                    Db.update(tx, "INSERT INTO c06_recovery VALUES(?,?)", id, "已确认事务");
                    return null;
                });
    }

    public static void pending(Connection c, long id) throws SQLException {
        c.setAutoCommit(false);
        Db.update(c, "INSERT INTO c06_recovery VALUES(?,?)", id, "未提交事务");
    }
}
```

## 逐步解析

标准解Policy保存实际配置，strictLocalCommit只是本机配置分类，scope显式限制保证。confirmed用事务插入后commit；pending开启事务但不commit。恢复测试通过Docker API对唯一容器ID发送KILL而非remove，避免丢失其数据目录，再显式等待JDBC可用。测试末尾关闭失效连接不覆盖主要断言。容器重启保留目录不等于具备外部备份。

1. 先确认输入边界与调用者所有的连接，不能在查询辅助方法中提前关闭调用者连接
2. 所有动态值绑定到PreparedStatement；表名/语句结构为课程常量
3. 事务成功才commit，SQL或运行期异常走rollback，后续状态恢复不能悄悄改变业务结果
4. 对照本题全部ContractTest和DatabaseTest，正常结果、边界和故障都要解释
5. 源码阅读、计划、锁诊断和恢复范围属于观察验收，不用固定耗时或私有字段伪装稳定API
6. 替代方案与迁移练习见task.md，任何实现只要满足契约都可接受；不能删除测试放宽契约

## 复杂度、失败边界与替代方案

redo用于崩溃后恢复已经写入日志的页修改，undo支持事务回滚与一致性读旧版本；binlog记录服务层数据变更，用于复制和时间点恢复链路。刷redo、刷binlog、副本确认和备份是不同边界。设置innodb_flush_log_at_trx_commit=1和sync_binlog=1强化本机提交持久化配置，但存储设备是否兑现fsync仍有假设。一次SIGKILL不等于宿主断电、磁盘损坏或完整灾备验证。

写一份PITR演练清单：备份点、binlog范围、目标时刻、凭据权限、隔离恢复库、对账和RTO/RPO。实际复制延迟与PITR并未由单容器测试覆盖。

## 调用方

```java
package labs;

/** 调用前用 Schema.main 显式重置合成数据；密码从环境读取。 */
public final class Usage {
    public static void main(String[] args) throws Exception {
        try (java.sql.Connection c = Db.local()) {
            System.out.println(RecoveryLab.inspect(c));
            RecoveryLab.confirmed(c, 99);
            System.out.println(
                    "确认记录=" + Db.scalar(c, "SELECT COUNT(*) FROM c06_recovery WHERE id=99"));
        }
    }
}
```

## 检查命令

从课程根执行 ./gradlew :mysql-06-recovery-06-durability:test。真实MySQL未运行时不能把纯逻辑绿灯称为完整通过。
