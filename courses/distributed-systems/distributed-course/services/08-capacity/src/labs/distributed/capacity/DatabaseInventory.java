package labs.distributed.capacity;

import java.sql.SQLException;
import java.time.Duration;
import labs.distributed.grpc.Lab;
import labs.distributed.idempotency.IdempotencyStore;
import labs.distributed.support.Database;

/** 真实RPC背后的数据库实现：库存和幂等结果原子提交，容量保护覆盖整个请求。 */
public final class DatabaseInventory implements Lab.Backend {
  private final Database database;
  private final IdempotencyStore operations;
  public final Admission admission;

  public DatabaseInventory(Database database, int limit) {
    this.database = database;
    this.operations = new IdempotencyStore(database);
    this.admission = new Admission(limit);
  }

  public void initialize(int stock) throws SQLException {
    operations.initialize(stock);
  }

  @Override
  public int quote(String sku) {
    try {
      return admission.execute(
          () ->
              Math.toIntExact(database.scalar("SELECT available FROM inventory WHERE sku=?", sku)));
    } catch (java.util.concurrent.RejectedExecutionException failure) {
      throw failure;
    } catch (Exception failure) {
      throw new IllegalStateException("库存查询暂时失败", failure);
    }
  }

  @Override
  public int reserve(String key, String sku, int quantity) {
    try {
      return admission.execute(
          () -> {
            var request = new IdempotencyStore.Request(key, sku, quantity);
            var claim = operations.acquire(request, Duration.ofSeconds(30));
            if (claim.kind() == IdempotencyStore.Kind.BUSY)
              throw new IllegalStateException("相同请求正在处理，请稍后按同一键查询");
            int remaining =
                claim.kind() == IdempotencyStore.Kind.REPLAY
                    ? claim.result()
                    : operations.complete(request, claim, () -> {});
            if (remaining < 0) throw new IllegalArgumentException("库存不足");
            return remaining;
          });
    } catch (IllegalArgumentException | java.util.concurrent.RejectedExecutionException failure) {
      throw failure;
    } catch (Exception failure) {
      throw new IllegalStateException("库存操作结果未知，请按原幂等键恢复", failure);
    }
  }
}
