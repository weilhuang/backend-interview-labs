package labs.capstone;

import static labs.capstone.Model.*;

import io.grpc.*;

import labs.capstone.protocol.*;

import java.time.Duration;
import java.util.*;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.locks.ReentrantLock;

/** 页面、CLI与测试共用的实际调用方；不缓存健康结果冒充服务可用。 */
public final class Runtime implements AutoCloseable {
    public final Database db;
    public final OrderCache cache;
    public final OrderService orders;
    public final DeliveryFlow flow;
    private final Config config;
    private final ManagedChannel channel;
    private final ReentrantLock replayLock = new ReentrantLock();

    public Runtime(Config config) throws Exception {
        this.config = config;
        db = new Database(config.jdbc(), config.user(), config.password());
        try {
            db.initialize();
        } catch (Exception e) {
            db.close();
            throw e;
        }
        cache = new OrderCache(config.redisHost(), config.redisPort());
        orders = new OrderService(db, cache);
        channel =
                ManagedChannelBuilder.forAddress(config.rpcHost(), config.rpcPort())
                        .usePlaintext()
                        .build();
        flow = new DeliveryFlow(db, config.brokers(), channel);
    }

    public Map<String, Boolean> health() {
        boolean database;
        try {
            database = db.scalar("SELECT 1") == 1;
        } catch (Exception e) {
            database = false;
        }
        boolean rpc;
        try {
            rpc =
                    DeliveryGrpc.newBlockingStub(channel)
                            .withDeadlineAfter(500, TimeUnit.MILLISECONDS)
                            .probe(ProbeRequest.getDefaultInstance())
                            .getStatus()
                            .equals("READY");
        } catch (Exception e) {
            rpc = false;
        }
        return Map.of(
                "database",
                database,
                "redis",
                cache.healthy(),
                "kafka",
                Broker.healthy(config.brokers()),
                "rpc",
                rpc);
    }

    public long projectionLag() throws java.sql.SQLException {
        return db.scalar(
                "SELECT COUNT(*) FROM orders o LEFT JOIN deliveries d ON o.request_id=d.request_id"
                    + " WHERE d.request_id IS NULL OR d.version<o.version");
    }

    public long backlog() throws java.sql.SQLException {
        return Math.max(
                db.scalar("SELECT COUNT(*) FROM outbox WHERE published=FALSE"), projectionLag());
    }

    public Map<String, Object> dashboard() throws Exception {
        Map<String, Boolean> health = health();
        var snapshot = db.snapshot();
        var inventory = snapshot.inventory();
        var orders = snapshot.orders();
        var deliveries = snapshot.deliveries();
        long pending = db.scalar("SELECT COUNT(*) FROM outbox WHERE published=FALSE");
        return Map.of(
                "inventory",
                inventory,
                "orders",
                orders,
                "deliveries",
                deliveries,
                "outboxPending",
                pending,
                "projectionLag",
                projectionLag(),
                "inboxCount",
                db.scalar("SELECT COUNT(*) FROM inbox"),
                "health",
                health,
                "decision",
                RecoveryPolicy.decide(
                        health.get("database"),
                        health.get("redis"),
                        health.get("kafka"),
                        health.get("rpc"),
                        backlog(),
                        1000),
                "audit",
                Audit.inspect(inventory, orders, deliveries));
    }

    public Map<String, Integer> replay() throws Exception {
        if (!replayLock.tryLock()) throw new Conflict("已有重放执行中，请等待本轮结束");
        try {
            Broker.initialize(config.brokers());
            int published = flow.publish(Fault.NONE);
            int consumed =
                    flow.consume("capstone-projection-v1", Duration.ofSeconds(6), Fault.NONE);
            return Map.of("published", published, "consumed", consumed);
        } finally {
            replayLock.unlock();
        }
    }

    public void close() {
        channel.shutdown();
        boolean interrupted = false;
        try {
            if (!channel.awaitTermination(3, TimeUnit.SECONDS)) channel.shutdownNow();
        } catch (InterruptedException e) {
            interrupted = true;
            channel.shutdownNow();
        } finally {
            db.close();
            if (interrupted) Thread.currentThread().interrupt();
        }
    }
}
