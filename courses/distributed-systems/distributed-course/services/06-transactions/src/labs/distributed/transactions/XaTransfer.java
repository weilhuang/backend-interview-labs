package labs.distributed.transactions;

import com.mysql.cj.jdbc.MysqlXADataSource;
import java.nio.ByteBuffer;
import java.nio.channels.FileChannel;
import java.nio.charset.StandardCharsets;
import java.nio.file.*;
import java.sql.*;
import java.util.Arrays;
import javax.sql.XAConnection;
import javax.transaction.xa.*;
import labs.distributed.support.Database;

/** 实际MySQL XA两资源实验。单事务日志文件与单协调者，不能替代生产事务管理器。 */
public final class XaTransfer {
  public record Branch(String transaction, String branch) implements Xid {
    public int getFormatId() {
      return 0xC10;
    }

    public byte[] getGlobalTransactionId() {
      return transaction.getBytes(StandardCharsets.UTF_8);
    }

    public byte[] getBranchQualifier() {
      return branch.getBytes(StandardCharsets.UTF_8);
    }
  }

  private final Database first;
  private final Database second;
  private final Path journal;

  public XaTransfer(Database first, Database second, Path journal) {
    this.first = first;
    this.second = second;
    this.journal = journal;
  }

  private static XAConnection connect(Database database) throws SQLException {
    MysqlXADataSource source = new MysqlXADataSource();
    source.setUrl(database.url());
    source.setUser(database.user());
    source.setPassword(database.password());
    source.setConnectTimeout(5000);
    source.setSocketTimeout(15000);
    return source.getXAConnection();
  }

  private record XaHandle(XAConnection connection) implements AutoCloseable {
    XaHandle(Database database) throws SQLException {
      this(connect(database));
    }

    @Override
    public void close() throws SQLException {
      connection.close();
    }
  }

  private void decision(String id) throws java.io.IOException {
    Files.createDirectories(journal.toAbsolutePath().getParent());
    try (FileChannel file =
        FileChannel.open(journal, StandardOpenOption.CREATE_NEW, StandardOpenOption.WRITE)) {
      ByteBuffer bytes = StandardCharsets.UTF_8.encode("COMMIT " + id + "\n");
      while (bytes.hasRemaining()) file.write(bytes);
      file.force(true);
    }
    // 实验在Linux文件系统上运行，同时同步目录项，避免文件存在性只停留在缓存。
    try (FileChannel directory =
        FileChannel.open(journal.toAbsolutePath().getParent(), StandardOpenOption.READ)) {
      directory.force(true);
    }
  }

  public void transfer(String id, int amount, boolean stopAfterPrepare, boolean stopAfterDecision)
      throws Exception {
    if (!id.matches("[a-zA-Z0-9_-]{1,40}") || amount < 1)
      throw new IllegalArgumentException("事务标识或金额非法");
    if (Files.exists(journal)) throw new IllegalStateException("已有持久决策，只能恢复，禁止重新执行转账");
    try (var handleA = new XaHandle(first);
        var handleB = new XaHandle(second)) {
      XAConnection a = handleA.connection();
      XAConnection b = handleB.connection();
      XAResource ra = a.getXAResource();
      XAResource rb = b.getXAResource();
      Branch xa = new Branch(id, "a");
      Branch xb = new Branch(id, "b");
      boolean prepared = false;
      boolean startedA = false;
      boolean startedB = false;
      try {
        ra.start(xa, XAResource.TMNOFLAGS);
        startedA = true;
        rb.start(xb, XAResource.TMNOFLAGS);
        startedB = true;
        try (Connection ca = a.getConnection();
            Connection cb = b.getConnection()) {
          if (Database.update(
                  ca,
                  "UPDATE xa_account SET balance=balance-? WHERE id=1 AND balance>=?",
                  amount,
                  amount)
              != 1) {
            throw new IllegalArgumentException("转出余额不足");
          }
          Database.update(cb, "UPDATE xa_account SET balance=balance+? WHERE id=1", amount);
        }
        ra.end(xa, XAResource.TMSUCCESS);
        rb.end(xb, XAResource.TMSUCCESS);
        // 练习区开始
        if (ra.prepare(xa) != XAResource.XA_OK || rb.prepare(xb) != XAResource.XA_OK) {
          throw new IllegalStateException("预期两个写分支都进入PREPARED");
        }
        prepared = true;
        if (stopAfterPrepare) return;
        decision(id);
        if (stopAfterDecision) return;
        ra.commit(xa, false);
        rb.commit(xb, false);
        // 练习区结束
      } finally {
        // PREPARED后故意保留，恢复器根据持久化决策处理，不能在未知状态下擅自回滚。
        if (!prepared && startedA) {
          try {
            ra.end(xa, XAResource.TMFAIL);
          } catch (XAException ignored) {
          }
          try {
            ra.rollback(xa);
          } catch (XAException ignored) {
          }
        }
        if (!prepared && startedB) {
          try {
            rb.end(xb, XAResource.TMFAIL);
          } catch (XAException ignored) {
          }
          try {
            rb.rollback(xb);
          } catch (XAException ignored) {
          }
        }
      }
    }
  }

  public int recover(String id) throws Exception {
    boolean commit =
        Files.exists(journal) && Files.readString(journal).equals("COMMIT " + id + "\n");
    int recovered = 0;
    for (Database database : java.util.List.of(first, second)) {
      XAConnection connection = connect(database);
      try {
        XAResource resource = connection.getXAResource();
        Xid[] branches = resource.recover(XAResource.TMSTARTRSCAN);
        try {
          for (Xid branch : branches) {
            if (branch.getFormatId() != 0xC10
                || !Arrays.equals(
                    branch.getGlobalTransactionId(), id.getBytes(StandardCharsets.UTF_8))) continue;
            if (commit) resource.commit(branch, false);
            else resource.rollback(branch);
            recovered++;
          }
        } finally {
          resource.recover(XAResource.TMENDRSCAN);
        }
      } finally {
        connection.close();
      }
    }
    return recovered;
  }
}
