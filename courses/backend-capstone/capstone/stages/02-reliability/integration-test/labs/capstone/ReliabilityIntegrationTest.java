package labs.capstone;

import static labs.capstone.Model.*;

import static org.junit.jupiter.api.Assertions.*;

import org.junit.jupiter.api.Test;

import java.util.*;
import java.util.concurrent.*;

class ReliabilityIntegrationTest {
    @Test
    void 真实MySQL并发幂等约束和Redis失败仍守恒() throws Exception {
        try (var env = new RealServices()) {
            var command = new Command("retry", "book", 2);
            assertThrows(Unknown.class, () -> env.orders.place(command, Fault.AFTER_ORDER_COMMIT));
            assertEquals(1, env.orders.place(command, Fault.NONE).version());
            assertEquals(18, env.db.scalar("SELECT available FROM inventory"));
            assertThrows(
                    Conflict.class,
                    () -> env.orders.place(new Command("retry", "book", 3), Fault.NONE));
            env.orders.place(new Command("Case", "book", 1), Fault.NONE);
            env.orders.place(new Command("case", "book", 1), Fault.NONE);
            assertEquals(3, env.db.scalar("SELECT COUNT(*) FROM orders"));
            try (var executor = Executors.newFixedThreadPool(12)) {
                var jobs = new ArrayList<Callable<Boolean>>();
                for (int i = 0; i < 40; i++) {
                    int n = i;
                    jobs.add(
                            () -> {
                                try {
                                    env.orders.place(
                                            new Command("parallel-" + n, "book", 1), Fault.NONE);
                                    return true;
                                } catch (Conflict expected) {
                                    return false;
                                }
                            });
                }
                long successes = 0;
                for (var f : executor.invokeAll(jobs, 30, TimeUnit.SECONDS)) {
                    if (f.get()) successes++;
                }
                assertEquals(16, successes);
            }
            assertEquals(0, env.db.scalar("SELECT available FROM inventory"));
            assertEquals(19, env.db.scalar("SELECT COUNT(*) FROM orders"));
            env.orders.find("retry", false);
            env.redis.getDockerClient().stopContainerCmd(env.redis.getContainerId()).exec();
            env.orders.cancel("retry");
            env.orders.cancel("retry");
            assertEquals(2, env.db.scalar("SELECT available FROM inventory"));
            assertEquals("CANCELLED", env.orders.find("retry", false).status());
            assertEquals(20, env.db.scalar("SELECT COUNT(*) FROM outbox"));
            assertTrue(
                    Audit.inspect(env.db.inventory(), env.db.orders(), List.of()).stream()
                            .noneMatch(x -> x.severity().equals("ERROR")));
        }
    }

    @Test
    void 同号并发下单只扣一次且并发取消只释放一次() throws Exception {
        try (var env = new RealServices();
                var executor = Executors.newFixedThreadPool(12)) {
            var start = new CyclicBarrier(12);
            var jobs = new ArrayList<Callable<Order>>();
            for (int i = 0; i < 12; i++)
                jobs.add(
                        () -> {
                            start.await(10, TimeUnit.SECONDS);
                            return env.orders.place(
                                    new Command("same-intent", "book", 3), Fault.NONE);
                        });
            for (var result : executor.invokeAll(jobs, 30, TimeUnit.SECONDS))
                assertEquals("RESERVED", result.get().status());
            assertEquals(17, env.db.scalar("SELECT available FROM inventory"));
            assertEquals(1, env.db.scalar("SELECT COUNT(*) FROM orders"));
            assertEquals(1, env.db.scalar("SELECT COUNT(*) FROM outbox"));
            var cancelling = new CyclicBarrier(12);
            jobs.clear();
            for (int i = 0; i < 12; i++)
                jobs.add(
                        () -> {
                            cancelling.await(10, TimeUnit.SECONDS);
                            return env.orders.cancel("same-intent");
                        });
            for (var result : executor.invokeAll(jobs, 30, TimeUnit.SECONDS))
                assertEquals("CANCELLED", result.get().status());
            assertEquals(20, env.db.scalar("SELECT available FROM inventory"));
            assertEquals(2, env.db.scalar("SELECT COUNT(*) FROM outbox"));
            assertEquals(1, env.db.scalar("SELECT COUNT(*) FROM orders"));
        }
    }
}
