import org.apache.kafka.clients.admin.Admin;
import org.apache.kafka.clients.admin.DescribeTopicsOptions;
import org.apache.kafka.clients.admin.TopicDescription;
import org.apache.kafka.common.errors.InterruptException;
import org.apache.kafka.common.errors.LeaderNotAvailableException;
import org.apache.kafka.common.errors.UnknownTopicOrPartitionException;

import java.time.Duration;
import java.util.List;
import java.util.concurrent.ExecutionException;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.TimeoutException;

/** 仅用于故障前的元数据/三副本屏障，不重试业务发送、消费或整个测试。 */
final class ReplicaReadiness {
    private static final long REQUEST_NANOS = Duration.ofSeconds(5).toNanos();
    private static final long POLL_NANOS = Duration.ofMillis(100).toNanos();

    interface Probe {
        Future<TopicDescription> describe(int timeoutMillis);
    }

    interface Time {
        long nanoTime();

        void pause(long nanos) throws InterruptedException;
    }

    private static final Time SYSTEM_TIME =
            new Time() {
                public long nanoTime() {
                    return System.nanoTime();
                }

                public void pause(long nanos) throws InterruptedException {
                    TimeUnit.NANOSECONDS.sleep(nanos);
                }
            };

    private ReplicaReadiness() {}

    static TopicDescription awaitTopic(
            Admin admin, String topic, int expectedPartitions, Duration timeout)
            throws ExecutionException, InterruptedException {
        return awaitTopic(
                topic,
                expectedPartitions,
                timeout,
                timeoutMillis ->
                        admin.describeTopics(
                                        List.of(topic),
                                        new DescribeTopicsOptions().timeoutMs(timeoutMillis))
                                .allTopicNames()
                                .thenApply(topics -> topics.get(topic)),
                SYSTEM_TIME);
    }

    // 注入单调时钟与异步探针，纯测试无需睡眠或启动Kafka。
    static TopicDescription awaitTopic(
            String topic, int expectedPartitions, Duration timeout, Probe probe, Time time)
            throws ExecutionException, InterruptedException {
        long budget = timeout.toNanos();
        if (budget <= 0 || expectedPartitions < 0) {
            throw new IllegalArgumentException("就绪预算必须为正，分区数必须为非负（0表示任意非空主题）");
        }
        long started = time.nanoTime();
        int attempts = 0;
        String lastObservation = "尚未取得元数据";
        Throwable lastFailure = null;
        try {
            while (true) {
                if (Thread.currentThread().isInterrupted()) {
                    throw new InterruptedException("等待主题就绪前线程已中断");
                }
                long remaining = budget - (time.nanoTime() - started);
                if (remaining <= 0) break;
                long requestBudget = Math.min(REQUEST_NANOS, remaining);
                long requestStarted = time.nanoTime();
                // Kafka的毫秒预算向上取整；Future另受精确纳秒总预算约束。
                int timeoutMillis = (int) Math.max(1, (requestBudget + 999_999) / 1_000_000);
                attempts++;
                Future<TopicDescription> pending = null;
                try {
                    pending = probe.describe(timeoutMillis);
                    long requestRemaining =
                            Math.min(
                                    requestBudget - (time.nanoTime() - requestStarted),
                                    budget - (time.nanoTime() - started));
                    if (requestRemaining <= 0) throw new TimeoutException("元数据调用已耗尽请求预算");
                    TopicDescription description =
                            pending.get(requestRemaining, TimeUnit.NANOSECONDS);
                    lastObservation = String.valueOf(description);
                    // 晚于总deadline的成功也不得让屏障通过。
                    if (budget - (time.nanoTime() - started) > 0
                            && hasThreeReplicas(description, expectedPartitions)) {
                        return description;
                    }
                } catch (ExecutionException failure) {
                    if (failure.getCause() instanceof InterruptException) {
                        Thread.currentThread().interrupt();
                        throw failure;
                    }
                    if (!transientMetadataFailure(failure.getCause())) throw failure;
                    lastFailure = failure.getCause();
                    lastObservation = lastFailure.toString();
                } catch (TimeoutException failure) {
                    if (pending != null) pending.cancel(true);
                    lastFailure = failure;
                    lastObservation = failure.toString();
                } catch (UnknownTopicOrPartitionException
                        | LeaderNotAvailableException
                        | org.apache.kafka.common.errors.TimeoutException failure) {
                    lastFailure = failure;
                    lastObservation = failure.toString();
                }
                remaining = budget - (time.nanoTime() - started);
                if (remaining > 0) time.pause(Math.min(POLL_NANOS, remaining));
            }
        } catch (InterruptedException | InterruptException interrupted) {
            Thread.currentThread().interrupt();
            throw interrupted;
        }
        throw new AssertionError(
                "等待主题="
                        + topic
                        + " 的非空元数据、有效leader、RF=3和ISR=3超时；预算="
                        + timeout
                        + "，尝试="
                        + attempts
                        + "，最后观察="
                        + lastObservation,
                lastFailure);
    }

    private static boolean transientMetadataFailure(Throwable failure) {
        return failure instanceof UnknownTopicOrPartitionException
                || failure instanceof LeaderNotAvailableException
                || failure instanceof org.apache.kafka.common.errors.TimeoutException;
    }

    private static boolean hasThreeReplicas(TopicDescription topic, int expectedPartitions) {
        return topic != null
                && !topic.partitions().isEmpty()
                && (expectedPartitions == 0 || topic.partitions().size() == expectedPartitions)
                && topic.partitions().stream()
                        .allMatch(
                                partition ->
                                        partition.leader() != null
                                                && partition.leader().id() >= 0
                                                && partition.replicas().size() == 3
                                                && partition.isr().size() == 3
                                                && partition.replicas().containsAll(partition.isr())
                                                && partition.isr().contains(partition.leader()));
    }
}
