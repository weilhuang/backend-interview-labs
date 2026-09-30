package labs.distributed.capacity;

import labs.distributed.dubbo.Inventory;

/** 两套真实RPC共用同一持久化业务合同，不在协议适配器中重复实现幂等。 */
public final class DubboDatabaseInventory implements Inventory {
  private final DatabaseInventory backend;

  public DubboDatabaseInventory(DatabaseInventory backend) {
    this.backend = backend;
  }

  @Override
  public String quote(String sku) {
    return Integer.toString(backend.quote(sku));
  }

  @Override
  public int reserve(String key, String sku, int quantity) {
    return backend.reserve(key, sku, quantity);
  }
}
