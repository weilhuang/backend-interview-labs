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
