package labs;

import labs.support.*;

public final class LeasesUsage {
  public static void main(String[] args) throws Exception {
    try (var db = new MySqlLab().start();
        var lab = new RedisLab().start();
        var j = lab.connect()) {
      var resource = new Leases.FencedResource(db::connect);
      resource.initialize();
      var fenced = Leases.acquireFenced(j, lab.key("lease"), 10_000, resource).orElseThrow();
      try {
        System.out.println("资源端接收=" + resource.write(fenced.fence(), "库存批处理结果"));
      } finally {
        System.out.println("仅释放自己的租约=" + Leases.release(j, fenced.lease()));
      }
    }
  }
}
