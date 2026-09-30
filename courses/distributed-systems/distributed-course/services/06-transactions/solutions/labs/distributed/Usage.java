package labs.distributed;

import java.nio.file.Files;
import labs.distributed.support.*;
import labs.distributed.transactions.*;

public final class Usage {
  public static void main(String[] args) throws Exception {
    if (args.length != 1 || !args[0].equals("--docker")) {
      System.out.println("真实双数据库调用：./gradlew :06-transactions:run -PappArgs=--docker");
      System.out.println("此入口创建隔离MySQL，演示TCC确认、Saga与XA恢复；当前未启动容器");
      return;
    }
    try (var first = Images.mysql().withUsername("root");
        var second = Images.mysql().withUsername("root")) {
      first.start();
      second.start();
      var a = Images.database(first);
      var b = Images.database(second);
      var inventory = new TccInventory(a);
      inventory.initialize(10);
      var payment = new PaymentLedger(b);
      payment.initialize(100);
      var saga = new Saga(a, inventory, payment);
      saga.initialize();
      saga.start("demo-order", 2, 30);
      System.out.println("预留后：" + saga.step("demo-order", point -> {}));
      System.out.println("支付后：" + saga.step("demo-order", point -> {}));
      System.out.println("发货确认：" + inventory.confirm("demo-order"));
      System.out.println("库存守恒合计：" + a.scalar("SELECT available+reserved+sold FROM tcc_stock"));
      for (var db : java.util.List.of(a, b)) {
        db.execute("CREATE TABLE xa_account (id INT PRIMARY KEY, balance INT NOT NULL)");
        db.execute("INSERT INTO xa_account VALUES (1, 100)");
      }
      var directory = Files.createTempDirectory("distributed-xa-demo-");
      var journal = directory.resolve("decision.log");
      new XaTransfer(a, b, journal).transfer("demo_xa", 20, false, true);
      System.out.println("已落盘决策，重建协调器完成分支：" + new XaTransfer(a, b, journal).recover("demo_xa"));
      System.out.println(
          "两个余额："
              + a.scalar("SELECT balance FROM xa_account")
              + "/"
              + b.scalar("SELECT balance FROM xa_account"));
      Files.delete(journal);
      Files.delete(directory);
    }
  }
}
