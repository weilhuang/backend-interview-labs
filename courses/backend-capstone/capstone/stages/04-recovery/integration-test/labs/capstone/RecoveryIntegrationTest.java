package labs.capstone;

import static labs.capstone.Model.*;

import static org.junit.jupiter.api.Assertions.*;

import org.junit.jupiter.api.Test;

import java.time.Duration;

class RecoveryIntegrationTest {
    @Test
    void 数据库重启后待发事件与订单事实保留() throws Exception {
        try (var env = new RealServices()) {
            env.orders.place(new Command("survive", "book", 3), Fault.NONE);
            assertEquals(1, env.db.scalar("SELECT COUNT(*) FROM outbox WHERE published=FALSE"));
            env.restartMysql();
            assertEquals(17, env.db.scalar("SELECT available FROM inventory"));
            assertEquals("RESERVED", env.orders.find("survive", true).status());
            assertEquals(1, env.db.scalar("SELECT COUNT(*) FROM outbox WHERE published=FALSE"));
            env.flow.publish(Fault.NONE);
            env.flow.consume("recovery", Duration.ofSeconds(12), Fault.NONE);
            assertEquals(0, env.db.scalar("SELECT COUNT(*) FROM outbox WHERE published=FALSE"));
            assertTrue(
                    Audit.inspect(env.db.inventory(), env.db.orders(), env.db.deliveries())
                            .isEmpty());
        }
    }
}
