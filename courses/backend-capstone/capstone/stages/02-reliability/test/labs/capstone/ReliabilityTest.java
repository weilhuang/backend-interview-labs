package labs.capstone;

import static labs.capstone.Model.*;

import static org.junit.jupiter.api.Assertions.*;

import org.junit.jupiter.api.*;

import java.sql.*;

class ReliabilityTest {
    Database db;
    OrderService service;

    @BeforeEach
    void setup() throws Exception {
        db = FastDatabase.open();
        service = new OrderService(db, new OrderCache("127.0.0.1", 1));
    }

    @AfterEach
    void close() {
        db.close();
    }

    @Test
    void 成功扣减与事件一起提交() throws Exception {
        var order = service.place(new Command("A", "book", 3), Fault.NONE);
        assertEquals("RESERVED", order.status());
        assertEquals(17, db.scalar("SELECT available FROM inventory"));
        assertEquals(1, db.scalar("SELECT COUNT(*) FROM outbox"));
    }

    @Test
    void 失败不能留下订单和事件() {
        assertThrows(Conflict.class, () -> service.place(new Command("A", "book", 21), Fault.NONE));
        assertDoesNotThrow(
                () -> {
                    assertEquals(20, db.scalar("SELECT available FROM inventory"));
                    assertEquals(0, db.scalar("SELECT COUNT(*) FROM orders"));
                    assertEquals(0, db.scalar("SELECT COUNT(*) FROM outbox"));
                });
    }

    @Test
    void 提交后响应丢失仍留下完整事实() throws Exception {
        assertThrows(
                Unknown.class,
                () -> service.place(new Command("A", "book", 2), Fault.AFTER_ORDER_COMMIT));
        assertEquals(18, db.scalar("SELECT available FROM inventory"));
        assertNotNull(service.find("A", true));
    }

    @Test
    void 取消只释放一次并且写入第二个事件() throws Exception {
        service.place(new Command("A", "book", 2), Fault.NONE);
        assertEquals("CANCELLED", service.cancel("A").status());
        service.cancel("A");
        assertEquals(20, db.scalar("SELECT available FROM inventory"));
        assertEquals(2, db.scalar("SELECT COUNT(*) FROM outbox"));
    }

    @Test
    void 取消不存在订单不得制造库存() {
        assertThrows(Conflict.class, () -> service.cancel("missing"));
        assertDoesNotThrow(() -> assertEquals(20, db.scalar("SELECT available FROM inventory")));
    }

    @Test
    void 数据库约束失败应回滚之前修改() throws Exception {
        try (Connection c = db.open();
                Statement s = c.createStatement()) {
            s.execute("ALTER TABLE outbox ADD CONSTRAINT blocked CHECK(event_id<>'bad:1')");
        }
        assertThrows(
                SQLException.class, () -> service.place(new Command("bad", "book", 2), Fault.NONE));
        assertEquals(20, db.scalar("SELECT available FROM inventory"));
        assertEquals(0, db.scalar("SELECT COUNT(*) FROM orders"));
    }
}
