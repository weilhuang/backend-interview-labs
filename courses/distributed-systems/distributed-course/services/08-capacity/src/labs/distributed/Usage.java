package labs.distributed;

import labs.distributed.capacity.*;
import labs.distributed.grpc.Lab;
import labs.distributed.grpc.protocol.ReserveRequest;
import labs.distributed.support.Images;

public final class Usage {
  public static void main(String[] args) throws Exception {
    int demand = Admission.requiredConcurrency(1000, 0.08, 1.5);
    System.out.println("1000次/秒、80毫秒、1.5倍余量，需要约" + demand + "个在途额度");
    System.out.println("示例ID位布局：" + IdLayout.compose(1000, 7, 1));
    if (args.length != 1 || !args[0].equals("--docker")) {
      System.out.println("真实调用：./gradlew :08-capacity:run -PappArgs=--docker；当前未启动容器");
      return;
    }
    try (var mysql = Images.mysql()) {
      mysql.start();
      var database = Images.database(mysql);
      var backend = new DatabaseInventory(database, 4);
      backend.initialize(5);
      try (var endpoint = new Lab.Endpoint(new Lab.Service(backend))) {
        var request =
            ReserveRequest.newBuilder().setKey("demo-order").setSku("book").setQuantity(2).build();
        System.out.println(
            "第一次真实RPC："
                + Lab.client(endpoint.channel, "demo-first", 5000).reserve(request).getAvailable());
        System.out.println(
            "相同业务键重放："
                + Lab.client(endpoint.channel, "demo-retry", 5000).reserve(request).getAvailable());
        System.out.println("MySQL最终库存：" + database.scalar("SELECT available FROM inventory"));
        System.out.println(
            "峰值在途/当前在途：" + backend.admission.peak() + "/" + backend.admission.active());
      }
    }
  }
}
