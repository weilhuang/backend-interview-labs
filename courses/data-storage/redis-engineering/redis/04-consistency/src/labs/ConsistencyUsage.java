package labs;

import labs.support.*;

public final class ConsistencyUsage {
  public static void main(String[] args) throws Exception {
    try (var db = new MySqlLab().start();
        var lab = new RedisLab().start();
        var j = lab.connect()) {
      var store = new Consistency.Store(db::connect);
      store.initialize();
      String prefix = lab.key("demo:");
      System.out.println("初读=" + Consistency.read(store, j, prefix, 1));
      store.update(1, "价格已更新");
      System.out.println("待恢复事件=" + store.pending());
      store.recover(j, prefix, 20, () -> {});
      System.out.println("恢复后=" + Consistency.read(store, j, prefix, 1));
    }
  }
}
