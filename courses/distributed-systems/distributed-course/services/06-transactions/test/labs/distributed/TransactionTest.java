package labs.distributed;

import static org.junit.jupiter.api.Assertions.*;

import java.util.UUID;
import labs.distributed.support.Database;
import labs.distributed.transactions.*;
import org.junit.jupiter.api.Test;

class TransactionTest {
  Database memory() {
    return new Database(
        "jdbc:h2:mem:" + UUID.randomUUID() + ";MODE=MySQL;DB_CLOSE_DELAY=-1", "sa", "");
  }

  @Test
  void 重复确认取消和库存守恒() throws Exception {
    var db = memory();
    var inventory = new TccInventory(db);
    inventory.initialize(10);
    assertTrue(inventory.reserve("b1", "book", 3));
    assertTrue(inventory.reserve("b1", "book", 3));
    assertThrows(IllegalArgumentException.class, () -> inventory.reserve("b1", "book", 2));
    assertTrue(inventory.confirm("b1"));
    assertTrue(inventory.confirm("b1"));
    assertFalse(inventory.cancel("b1"));
    assertEquals(3, db.scalar("SELECT sold FROM tcc_stock"));
    assertTrue(inventory.reserve("b2", "book", 4));
    assertTrue(inventory.cancel("b2"));
    assertTrue(inventory.cancel("b2"));
    assertEquals(10, db.scalar("SELECT available+reserved+sold FROM tcc_stock"));
    assertEquals(7, db.scalar("SELECT available FROM tcc_stock"));
  }

  @Test
  void 空回滚留下墓碑阻止悬挂预留() throws Exception {
    var db = memory();
    var inventory = new TccInventory(db);
    inventory.initialize(10);
    assertTrue(inventory.cancel("late"));
    assertFalse(inventory.reserve("late", "book", 2));
    assertFalse(inventory.confirm("late"));
    assertEquals(10, db.scalar("SELECT available FROM tcc_stock"));
  }

  @Test
  void Saga在参与者成功日志未写时重放且补偿失败可恢复() throws Exception {
    var journal = memory();
    var stockDb = memory();
    var payDb = memory();
    var stock = new TccInventory(stockDb);
    stock.initialize(10);
    var pay = new PaymentLedger(payDb);
    pay.initialize(10);
    var saga = new Saga(journal, stock, pay);
    saga.initialize();
    saga.start("s1", 2, 50);
    assertThrows(
        IllegalStateException.class,
        () ->
            saga.step(
                "s1",
                point -> {
                  throw new IllegalStateException("提交后崩溃");
                }));
    assertEquals(8, stockDb.scalar("SELECT available FROM tcc_stock"));
    var recovered = new Saga(journal, stock, pay);
    assertEquals("RESERVED", recovered.step("s1", point -> {}));
    assertEquals(8, stockDb.scalar("SELECT available FROM tcc_stock"));
    assertEquals("COMPENSATING", recovered.step("s1", point -> {}));
    assertThrows(
        IllegalStateException.class,
        () ->
            recovered.step(
                "s1",
                point -> {
                  throw new IllegalStateException("退款后崩溃");
                }));
    assertEquals("CANCELLED", recovered.step("s1", point -> {}));
    assertEquals("CANCELLED", recovered.step("s1", point -> {}));
    assertEquals(10, stockDb.scalar("SELECT available FROM tcc_stock"));
    assertEquals(10, payDb.scalar("SELECT credit FROM wallet"));
    assertFalse(pay.charge("s1", 50));
  }

  @Test
  void 失败预留也可以取消并阻止迟到重入() throws Exception {
    var db = memory();
    var inventory = new TccInventory(db);
    inventory.initialize(2);
    assertFalse(inventory.reserve("no-stock", "book", 3));
    assertTrue(inventory.cancel("no-stock"));
    assertFalse(inventory.reserve("no-stock", "book", 1));
    assertEquals(2, db.scalar("SELECT available FROM tcc_stock"));
  }

  @Test
  void 固定种子操作序列保持资源守恒() throws Exception {
    var db = memory();
    var inventory = new TccInventory(db);
    inventory.initialize(20);
    var random = new java.util.Random(42);
    for (int i = 0; i < 120; i++) {
      String id = "branch-" + random.nextInt(15);
      switch (random.nextInt(3)) {
        case 0 -> inventory.reserve(id, "book", 2);
        case 1 -> inventory.confirm(id);
        case 2 -> inventory.cancel(id);
        default -> throw new AssertionError("不存在的动作");
      }
      assertEquals(20, db.scalar("SELECT available+reserved+sold FROM tcc_stock"));
      assertTrue(db.scalar("SELECT available FROM tcc_stock") >= 0);
      assertTrue(db.scalar("SELECT reserved FROM tcc_stock") >= 0);
      assertTrue(db.scalar("SELECT sold FROM tcc_stock") >= 0);
    }
  }

  @Test
  void 支付成功但检查点丢失后可以明确转入补偿() throws Exception {
    var journal = memory();
    var stockDb = memory();
    var payDb = memory();
    var stock = new TccInventory(stockDb);
    stock.initialize(10);
    var pay = new PaymentLedger(payDb);
    pay.initialize(100);
    var saga = new Saga(journal, stock, pay);
    saga.initialize();
    saga.start("cancel-paid", 2, 30);
    assertEquals("RESERVED", saga.step("cancel-paid", point -> {}));
    assertThrows(
        IllegalStateException.class,
        () ->
            saga.step(
                "cancel-paid",
                point -> {
                  throw new IllegalStateException("检查点丢失");
                }));
    assertEquals(70, payDb.scalar("SELECT credit FROM wallet"));
    saga.requestCompensation("cancel-paid");
    assertEquals("CANCELLED", saga.step("cancel-paid", point -> {}));
    assertEquals(100, payDb.scalar("SELECT credit FROM wallet"));
    assertEquals(10, stockDb.scalar("SELECT available FROM tcc_stock"));
    assertFalse(pay.charge("cancel-paid", 30));
  }
}
