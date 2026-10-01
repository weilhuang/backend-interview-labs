package labs.distributed;

import static org.junit.jupiter.api.Assertions.*;

import java.util.UUID;
import labs.distributed.outbox.*;
import labs.distributed.support.Database;
import org.junit.jupiter.api.Test;

class ProjectionTest {
  Database memory() {
    return new Database(
        "jdbc:h2:mem:" + UUID.randomUUID() + ";MODE=MySQL;DB_CLOSE_DELAY=-1", "sa", "");
  }

  @Test
  void 业务和outbox同提交及参数冲突() throws Exception {
    var db = memory();
    var store = new OutboxStore(db);
    store.initialize();
    var event = store.change("e1", "book", -3);
    assertEquals(7, event.available());
    assertEquals(event, store.change("e1", "book", -3));
    assertThrows(IllegalArgumentException.class, () -> store.change("e1", "book", -4));
    assertThrows(IllegalArgumentException.class, () -> store.change("e2", "book", -20));
    assertEquals(1, db.scalar("SELECT COUNT(*) FROM outbox"));
    assertEquals(7, db.scalar("SELECT available FROM product"));
  }

  @Test
  void 乱序与重复不回退读模型且载荷冲突可见() throws Exception {
    var db = memory();
    var projector = new Projector(db);
    projector.initialize();
    var newer = new Event("e2", "book", 2, 6);
    var older = new Event("e1", "book", 1, 8);
    assertTrue(projector.apply(newer, () -> {}));
    assertTrue(projector.apply(older, () -> {}));
    assertFalse(projector.apply(newer, () -> {}));
    assertEquals(6, db.scalar("SELECT available FROM read_model"));
    assertThrows(
        IllegalArgumentException.class,
        () -> projector.apply(new Event("e2", "book", 2, 9), () -> {}));
  }

  @Test
  void inbox与读模型必须同事务否则会吞事件() throws Exception {
    var db = memory();
    var projector = new Projector(db);
    projector.initialize();
    var event = new Event("e1", "book", 1, 9);
    assertThrows(
        IllegalStateException.class,
        () ->
            projector.apply(
                event,
                () -> {
                  throw new IllegalStateException("提交前故障");
                }));
    assertEquals(0, db.scalar("SELECT COUNT(*) FROM inbox"));
    assertEquals(0, db.scalar("SELECT COUNT(*) FROM read_model"));
    assertTrue(projector.apply(event, () -> {}));
  }

  @Test
  void 消息解析拒绝恶意或不兼容字段() {
    assertThrows(IllegalArgumentException.class, () -> Event.decode("e|b|-1|4"));
    assertThrows(IllegalArgumentException.class, () -> Event.decode("e|b|1|4|extra"));
    assertThrows(IllegalArgumentException.class, () -> new Event("e", "b", Long.MAX_VALUE, 1));
    var event = new Event("e", "b", 1, 4);
    assertEquals(event, Event.decode(event.encode()));
  }
}
