package labs.capstone;

import static labs.capstone.Model.*;

import static org.junit.jupiter.api.Assertions.*;

import org.junit.jupiter.api.Test;

import java.time.Duration;
import java.util.*;

class DefenseIntegrationTest {
    @Test
    void 新变体乱序取消重复身份与未知响应最终可审计() throws Exception {
        try (var env = new RealServices()) {
            Random random = new Random(1405);
            for (int i = 0; i < 8; i++) {
                String id = "blind-" + i;
                int quantity = random.nextInt(2) + 1;
                Command c = new Command(id, "book", quantity);
                if (i % 3 == 0) {
                    assertThrows(
                            Unknown.class, () -> env.orders.place(c, Fault.AFTER_ORDER_COMMIT));
                } else env.orders.place(c, Fault.NONE);
                env.orders.place(c, Fault.NONE);
                if (i % 2 == 0) env.orders.cancel(id);
            }
            assertTrue(
                    Audit.inspect(env.db.inventory(), env.db.orders(), env.db.deliveries()).stream()
                            .allMatch(f -> f.severity().equals("LAG")));
            env.flow.publish(Fault.NONE);
            env.flow.consume("blind", Duration.ofSeconds(12), Fault.NONE);
            assertTrue(
                    Audit.inspect(env.db.inventory(), env.db.orders(), env.db.deliveries())
                            .isEmpty());
            env.flow.consume("second-group-replay", Duration.ofSeconds(12), Fault.NONE);
            assertTrue(
                    Audit.inspect(env.db.inventory(), env.db.orders(), env.db.deliveries())
                            .isEmpty());
            assertEquals(12, env.db.scalar("SELECT COUNT(*) FROM inbox"));
            try (var c = env.db.open();
                    var s = c.createStatement()) {
                s.executeUpdate("UPDATE inventory SET available=available-1 WHERE sku='book'");
            }
            assertTrue(
                    Audit.inspect(env.db.inventory(), env.db.orders(), env.db.deliveries()).stream()
                            .anyMatch(f -> f.severity().equals("ERROR")));
        }
    }
}
