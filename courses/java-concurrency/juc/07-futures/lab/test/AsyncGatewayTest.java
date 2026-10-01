import static org.junit.jupiter.api.Assertions.*;

import labs.AsyncGateway;

import org.junit.jupiter.api.*;

import java.time.Duration;
import java.util.*;
import java.util.concurrent.*;

@Timeout(10)
class AsyncGatewayTest {
    static final class ManualTimer implements AsyncGateway.Timer {
        Runnable action;
        boolean cancelled;
        Duration delay;

        public AsyncGateway.Ticket schedule(Duration delay, Runnable action) {
            this.delay = delay;
            this.action = action;
            return () -> cancelled = true;
        }

        void expire() {
            if (!cancelled) action.run();
        }
    }

    @Test
    void parallelResultsCombineAndCancelAlarm() {
        var timer = new ManualTimer();
        var first = new CompletableFuture<String>();
        var second = new CompletableFuture<String>();
        var combined = AsyncGateway.aggregate(first, second, Duration.ofSeconds(1), timer);
        second.complete("库存");
        assertFalse(combined.isDone());
        first.complete("订单");
        assertEquals(new AsyncGateway.Summary("订单", "库存"), combined.join());
        assertTrue(timer.cancelled);
        timer.expire();
        assertFalse(combined.isCompletedExceptionally());
    }

    @Test
    void optionalFailureDegradesButPrimaryFailureFailsImmediately() {
        var timer = new ManualTimer();
        var primary = new CompletableFuture<String>();
        var optional = new CompletableFuture<String>();
        var result = AsyncGateway.aggregate(primary, optional, Duration.ofSeconds(1), timer);
        optional.completeExceptionally(new IllegalStateException("推荐故障"));
        primary.complete("订单");
        assertEquals("次要服务降级", result.join().secondary());
        var critical = new CompletableFuture<String>();
        var pending = new CompletableFuture<String>();
        var failed =
                AsyncGateway.aggregate(critical, pending, Duration.ofSeconds(1), new ManualTimer());
        critical.completeExceptionally(new IllegalArgumentException("订单失败"));
        assertTrue(failed.isDone());
        assertInstanceOf(
                IllegalArgumentException.class,
                assertThrows(CompletionException.class, failed::join).getCause());
        assertFalse(pending.isDone());
    }

    @Test
    void deadlineDoesNotPretendToInterruptUpstream() {
        var timer = new ManualTimer();
        var primary = new CompletableFuture<String>();
        var optional = new CompletableFuture<String>();
        var result = AsyncGateway.aggregate(primary, optional, Duration.ZERO, timer);
        timer.expire();
        assertInstanceOf(
                TimeoutException.class,
                assertThrows(CompletionException.class, result::join).getCause());
        assertFalse(primary.isCancelled());
        assertFalse(optional.isDone());
        primary.complete("太晚");
        optional.complete("太晚");
        assertTrue(result.isCompletedExceptionally());
    }

    @Test
    void contextIsClearedEvenAfterFailureAndPermitsAreReturned() {
        var jobs = new ArrayDeque<Runnable>();
        var gateway = new AsyncGateway(jobs::add, 1);
        var first =
                gateway.request(
                        "请求甲",
                        () -> {
                            assertEquals("请求甲", gateway.currentRequest());
                            throw new IllegalStateException("模拟错误");
                        });
        var rejected = gateway.request("请求乙", () -> 2);
        assertInstanceOf(
                RejectedExecutionException.class,
                assertThrows(CompletionException.class, rejected::join).getCause());
        jobs.remove().run();
        assertTrue(first.isCompletedExceptionally());
        assertNull(gateway.currentRequest(), "线程复用前必须清除上下文");
        var next = gateway.request("请求丙", () -> gateway.currentRequest());
        jobs.remove().run();
        assertEquals("请求丙", next.join());
        assertNull(gateway.currentRequest());
    }

    @Test
    void executorRejectionDoesNotLeakPermit() {
        var count = new java.util.concurrent.atomic.AtomicInteger();
        var gateway =
                new AsyncGateway(
                        job -> {
                            if (count.getAndIncrement() == 0)
                                throw new RejectedExecutionException("执行器拒绝");
                            job.run();
                        },
                        1);
        assertTrue(gateway.request("甲", () -> 1).isCompletedExceptionally());
        assertEquals(2, gateway.request("乙", () -> 2).join());
    }

    @Test
    void aggregateTimeoutKeepsBulkheadOccupiedUntilRealWorkFinishes() throws Exception {
        var entered = new CountDownLatch(1);
        var release = new CountDownLatch(1);
        var timer = new ManualTimer();
        try (var pool = Executors.newSingleThreadExecutor()) {
            var gateway = new AsyncGateway(pool, 1);
            var slow =
                    gateway.request(
                            "请求甲",
                            () -> {
                                entered.countDown();
                                try {
                                    release.await();
                                } catch (InterruptedException error) {
                                    Thread.currentThread().interrupt();
                                    throw new CompletionException(error);
                                }
                                return "结果";
                            });
            try {
                assertTrue(entered.await(2, TimeUnit.SECONDS));
                var aggregate =
                        AsyncGateway.aggregate(
                                slow,
                                CompletableFuture.completedFuture("推荐"),
                                Duration.ofSeconds(1),
                                timer);
                timer.expire();
                assertTrue(aggregate.isCompletedExceptionally());
                assertFalse(slow.isDone());
                assertTrue(gateway.request("请求乙", () -> "不能进入").isCompletedExceptionally());
                release.countDown();
                assertEquals("结果", slow.get(2, TimeUnit.SECONDS));
                pool.submit(() -> {}).get(2, TimeUnit.SECONDS);
                assertEquals("恢复", gateway.request("请求丙", () -> "恢复").get(2, TimeUnit.SECONDS));
            } finally {
                release.countDown();
            }
        }
    }

    @Test
    void cancelledResultStillNeedsUnderlyingCleanup() {
        var jobs = new ArrayDeque<Runnable>();
        var gateway = new AsyncGateway(jobs::add, 1);
        var ran = new java.util.concurrent.atomic.AtomicBoolean();
        var pending =
                gateway.request(
                        "甲",
                        () -> {
                            ran.set(true);
                            return 1;
                        });
        assertTrue(pending.cancel(true));
        jobs.remove().run();
        assertTrue(ran.get());
        assertNull(gateway.currentRequest());
        var next = gateway.request("乙", () -> 2);
        jobs.remove().run();
        assertEquals(2, next.join());
    }
}
