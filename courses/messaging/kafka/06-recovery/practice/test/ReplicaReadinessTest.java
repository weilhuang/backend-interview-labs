import static org.junit.jupiter.api.Assertions.*;

import org.apache.kafka.clients.admin.TopicDescription;
import org.apache.kafka.common.Node;
import org.apache.kafka.common.TopicPartitionInfo;
import org.apache.kafka.common.errors.InterruptException;
import org.apache.kafka.common.errors.LeaderNotAvailableException;
import org.apache.kafka.common.errors.TopicAuthorizationException;
import org.apache.kafka.common.errors.UnknownTopicOrPartitionException;
import org.junit.jupiter.api.Test;

import java.time.Duration;
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.ExecutionException;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.TimeoutException;
import java.util.concurrent.atomic.AtomicInteger;

class ReplicaReadinessTest {
    private static final List<Node> NODES =
            List.of(
                    new Node(1, "broker1", 9092),
                    new Node(2, "broker2", 9092),
                    new Node(3, "broker3", 9092));

    @Test
    void 初次查不到元数据与暂缺leader之后必须等到三个ISR() throws Exception {
        FakeTime time = new FakeTime();
        List<Future<TopicDescription>> replies =
                List.of(
                        failed(new UnknownTopicOrPartitionException("主题尚未传播")),
                        failed(new LeaderNotAvailableException("leader尚未传播")),
                        CompletableFuture.completedFuture(topic(2)),
                        CompletableFuture.completedFuture(topic(3)));
        AtomicInteger calls = new AtomicInteger();
        TopicDescription ready =
                ReplicaReadiness.awaitTopic(
                        "events",
                        1,
                        Duration.ofSeconds(1),
                        ignored -> replies.get(calls.getAndIncrement()),
                        time);
        assertEquals(3, ready.partitions().getFirst().isr().size());
        assertEquals(4, calls.get());
        assertEquals(Duration.ofMillis(300).toNanos(), time.now);
    }

    @Test
    void 一直查不到主题必须按总预算失败并保留最后原因() {
        FakeTime time = new FakeTime();
        UnknownTopicOrPartitionException missing = new UnknownTopicOrPartitionException("仍未传播");
        List<Integer> budgets = new ArrayList<>();
        AssertionError failure =
                assertThrows(
                        AssertionError.class,
                        () ->
                                ReplicaReadiness.awaitTopic(
                                        "__consumer_offsets",
                                        0,
                                        Duration.ofMillis(250),
                                        timeoutMillis -> {
                                            budgets.add(timeoutMillis);
                                            return failed(missing);
                                        },
                                        time));
        assertSame(missing, failure.getCause());
        assertTrue(failure.getMessage().contains("__consumer_offsets"));
        assertTrue(failure.getMessage().contains("尝试=3"));
        assertEquals(List.of(250, 150, 50), budgets);
        assertEquals(Duration.ofMillis(250).toNanos(), time.now);
    }

    @Test
    void 缺元数据空分区及任何未同步分区均不得越过屏障() {
        List<TopicDescription> notReady = new ArrayList<>();
        notReady.add(null);
        notReady.add(new TopicDescription("events", false, List.of()));
        notReady.add(topic(2));
        notReady.add(
                new TopicDescription(
                        "events",
                        false,
                        List.of(
                                partition(0, NODES.getFirst(), NODES, NODES),
                                partition(1, NODES.getFirst(), NODES, NODES.subList(0, 2)))));
        notReady.add(
                new TopicDescription(
                        "events", false, List.of(partition(0, Node.noNode(), NODES, NODES))));
        notReady.add(
                new TopicDescription(
                        "events",
                        false,
                        List.of(partition(0, NODES.getFirst(), NODES.subList(0, 2), NODES))));
        for (TopicDescription description : notReady) {
            FakeTime time = new FakeTime();
            AssertionError failure =
                    assertThrows(
                            AssertionError.class,
                            () ->
                                    ReplicaReadiness.awaitTopic(
                                            "events",
                                            0,
                                            Duration.ofMillis(250),
                                            ignored ->
                                                    CompletableFuture.completedFuture(description),
                                            time));
            assertEquals(Duration.ofMillis(250).toNanos(), time.now);
            assertTrue(failure.getMessage().contains("RF=3和ISR=3"));
            assertTrue(failure.getMessage().contains(String.valueOf(description)));
        }
    }

    @Test
    void 授权错误与非暂态异常立即失败而不等待() {
        for (RuntimeException permanent :
                List.of(
                        new TopicAuthorizationException("无权限"),
                        new IllegalArgumentException("错误请求"))) {
            FakeTime time = new FakeTime();
            AtomicInteger calls = new AtomicInteger();
            ExecutionException failure =
                    assertThrows(
                            ExecutionException.class,
                            () ->
                                    ReplicaReadiness.awaitTopic(
                                            "events",
                                            1,
                                            Duration.ofSeconds(45),
                                            ignored -> {
                                                calls.incrementAndGet();
                                                return failed(permanent);
                                            },
                                            time));
            assertSame(permanent, failure.getCause());
            assertEquals(1, calls.get());
            assertEquals(0, time.now);
        }
    }

    @Test
    void 请求超时最多五秒且最后一次请求不能超过剩余总预算() {
        FakeTime time = new FakeTime();
        List<Integer> requestBudgets = new ArrayList<>();
        List<Long> futureBudgets = new ArrayList<>();
        List<CompletableFuture<TopicDescription>> futures = new ArrayList<>();
        AssertionError failure =
                assertThrows(
                        AssertionError.class,
                        () ->
                                ReplicaReadiness.awaitTopic(
                                        "events",
                                        1,
                                        Duration.ofMillis(5250),
                                        timeoutMillis -> {
                                            requestBudgets.add(timeoutMillis);
                                            CompletableFuture<TopicDescription> future =
                                                    new CompletableFuture<>() {
                                                        @Override
                                                        public TopicDescription get(
                                                                long timeout, TimeUnit unit)
                                                                throws TimeoutException {
                                                            long nanos = unit.toNanos(timeout);
                                                            futureBudgets.add(nanos);
                                                            time.now += nanos;
                                                            throw new TimeoutException("没有元数据响应");
                                                        }
                                                    };
                                            futures.add(future);
                                            return future;
                                        },
                                        time));
        assertEquals(List.of(5000, 150), requestBudgets);
        assertEquals(
                List.of(Duration.ofSeconds(5).toNanos(), Duration.ofMillis(150).toNanos()),
                futureBudgets);
        assertTrue(futures.stream().allMatch(Future::isCancelled));
        assertInstanceOf(TimeoutException.class, failure.getCause());
        assertEquals(Duration.ofMillis(5250).toNanos(), time.now);
    }

    @Test
    void 取得Future耗时也计入deadline且逾期就绪不得成功() {
        FakeTime time = new FakeTime();
        assertThrows(
                AssertionError.class,
                () ->
                        ReplicaReadiness.awaitTopic(
                                "events",
                                1,
                                Duration.ofMillis(250),
                                ignored -> {
                                    time.now += Duration.ofMillis(100).toNanos();
                                    return new CompletableFuture<>() {
                                        @Override
                                        public TopicDescription get(long timeout, TimeUnit unit) {
                                            assertEquals(
                                                    Duration.ofMillis(150).toNanos(),
                                                    unit.toNanos(timeout));
                                            time.now += unit.toNanos(timeout);
                                            return topic(3);
                                        }
                                    };
                                },
                                time));
        assertEquals(Duration.ofMillis(250).toNanos(), time.now);
    }

    @Test
    void 请求与轮询等待被中断均立即退出并保留中断标志() {
        for (boolean duringGet : List.of(true, false)) {
            FakeTime time =
                    new FakeTime() {
                        @Override
                        public void pause(long nanos) throws InterruptedException {
                            throw new InterruptedException("轮询中断");
                        }
                    };
            AtomicInteger calls = new AtomicInteger();
            try {
                assertThrows(
                        InterruptedException.class,
                        () ->
                                ReplicaReadiness.awaitTopic(
                                        "events",
                                        1,
                                        Duration.ofSeconds(45),
                                        ignored -> {
                                            calls.incrementAndGet();
                                            if (!duringGet)
                                                return CompletableFuture.completedFuture(topic(2));
                                            return new CompletableFuture<>() {
                                                @Override
                                                public TopicDescription get(
                                                        long timeout, TimeUnit unit)
                                                        throws InterruptedException {
                                                    throw new InterruptedException("请求中断");
                                                }
                                            };
                                        },
                                        time));
                assertTrue(Thread.currentThread().isInterrupted());
                assertEquals(1, calls.get());
            } finally {
                Thread.interrupted();
            }
        }
    }

    @Test
    void 预先中断与Kafka中断不重试且保留标志() {
        FakeTime time = new FakeTime();
        AtomicInteger calls = new AtomicInteger();
        try {
            Thread.currentThread().interrupt();
            assertThrows(
                    InterruptedException.class,
                    () ->
                            ReplicaReadiness.awaitTopic(
                                    "events",
                                    1,
                                    Duration.ofSeconds(45),
                                    ignored -> {
                                        calls.incrementAndGet();
                                        return CompletableFuture.completedFuture(topic(3));
                                    },
                                    time));
            assertTrue(Thread.currentThread().isInterrupted());
            assertEquals(0, calls.get());
        } finally {
            Thread.interrupted();
        }
        try {
            assertThrows(
                    InterruptException.class,
                    () ->
                            ReplicaReadiness.awaitTopic(
                                    "events",
                                    1,
                                    Duration.ofSeconds(45),
                                    ignored -> {
                                        throw new InterruptException(
                                                new InterruptedException("Kafka调用中断"));
                                    },
                                    time));
            assertTrue(Thread.currentThread().isInterrupted());
        } finally {
            Thread.interrupted();
        }
    }

    private static CompletableFuture<TopicDescription> failed(Throwable cause) {
        return CompletableFuture.failedFuture(cause);
    }

    private static TopicDescription topic(int isr) {
        return new TopicDescription(
                "events",
                false,
                List.of(partition(0, NODES.getFirst(), NODES, NODES.subList(0, isr))));
    }

    private static TopicPartitionInfo partition(
            int id, Node leader, List<Node> replicas, List<Node> isr) {
        return new TopicPartitionInfo(id, leader, replicas, isr);
    }

    private static class FakeTime implements ReplicaReadiness.Time {
        long now;

        public long nanoTime() {
            return now;
        }

        public void pause(long nanos) throws InterruptedException {
            now += nanos;
        }
    }
}
