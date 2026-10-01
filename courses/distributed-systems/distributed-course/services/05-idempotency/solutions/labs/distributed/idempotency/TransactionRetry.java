package labs.distributed.idempotency;

import java.sql.SQLException;
import java.time.Duration;
import java.util.concurrent.ThreadLocalRandom;
import labs.distributed.support.Database;

/** 仅重试数据库明确已回滚的本地事务；连接中断或提交响应丢失不能盲目重放。 */
public final class TransactionRetry {
  @FunctionalInterface
  public interface Sleeper {
    void sleep(Duration delay) throws InterruptedException;
  }

  private final int maxAttempts;
  private final Sleeper sleeper;

  public TransactionRetry(int maxAttempts, Sleeper sleeper) {
    if (maxAttempts < 1 || maxAttempts > 4) {
      throw new IllegalArgumentException("事务尝试次数必须在1到4之间");
    }
    this.maxAttempts = maxAttempts;
    this.sleeper = java.util.Objects.requireNonNull(sleeper);
  }

  public static TransactionRetry bounded() {
    return new TransactionRetry(4, Thread::sleep);
  }

  /** 回调只能包含同一数据库的可回滚工作；不得包含邮件、HTTP或另一数据库提交。 */
  public <T> T run(Database database, Database.Work<T> work) throws SQLException {
    for (int attempt = 1; ; attempt++) {
      try {
        // 每次都重新打开连接并执行完整事务，不能只重放最后一条失败SQL。
        return database.transaction(work);
      } catch (SQLException failure) {
        boolean rolledBackDeadlock =
            failure.getErrorCode() == 1213
                && "40001".equals(failure.getSQLState())
                && failure.getSuppressed().length == 0;
        if (!rolledBackDeadlock || attempt == maxAttempts) throw failure;
        long maximumMillis = 5L << (attempt - 1);
        Duration delay = Duration.ofMillis(ThreadLocalRandom.current().nextLong(maximumMillis + 1));
        try {
          sleeper.sleep(delay);
        } catch (InterruptedException interrupted) {
          Thread.currentThread().interrupt();
          SQLException stopped = new SQLException("事务重试等待被中断，停止继续尝试", "57014", interrupted);
          stopped.addSuppressed(failure);
          throw stopped;
        }
      }
    }
  }
}
