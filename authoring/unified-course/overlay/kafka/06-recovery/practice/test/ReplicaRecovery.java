import org.apache.kafka.clients.admin.Admin;
import org.apache.kafka.clients.admin.DescribeClusterOptions;
import org.apache.kafka.clients.admin.DescribeTopicsOptions;
import org.apache.kafka.clients.admin.TopicDescription;
import org.apache.kafka.common.Node;
import org.apache.kafka.common.TopicCollection;
import org.apache.kafka.common.Uuid;
import org.apache.kafka.common.errors.InterruptException;
import org.apache.kafka.common.errors.LeaderNotAvailableException;
import org.apache.kafka.common.errors.UnknownTopicIdException;
import org.apache.kafka.common.errors.UnknownTopicOrPartitionException;

import java.time.Duration;
import java.util.Collection;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.concurrent.ExecutionException;
import java.util.concurrent.Future;
import java.util.concurrent.FutureTask;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.TimeoutException;
import java.util.stream.Collectors;

/** 故障后只读观察器；不替换原producer/consumer，不重试业务发送。 */
final class ReplicaRecovery {
    private static final long REQUEST_NANOS = Duration.ofSeconds(5).toNanos();
    private static final long POLL_NANOS = Duration.ofMillis(100).toNanos();
    private static final long GET_NANOS = Duration.ofMillis(200).toNanos();

    interface Time {
        long nanoTime();
        void pause(long nanos) throws InterruptedException;
    }

    static final Time SYSTEM_TIME = new Time() {
        public long nanoTime() { return System.nanoTime(); }
        public void pause(long nanos) throws InterruptedException { TimeUnit.NANOSECONDS.sleep(nanos); }
    };

    static final class Deadline {
        final Time time;
        final long started;
        final long budget;
        Deadline(Time time, Duration timeout) {
            this.time = time;
            this.started = time.nanoTime();
            this.budget = timeout.toNanos();
            if (budget <= 0) throw new IllegalArgumentException("恢复预算必须为正");
        }
        long remaining() { return Math.max(0, budget - (time.nanoTime() - started)); }
        void check() throws TimeoutException {
            if (remaining() == 0) throw new TimeoutException("恢复全局deadline已到");
        }
        int apiMillis() throws TimeoutException {
            // 向下取整；不足1ms不再发新RPC，不让SDK毫秒精度越过总预算。
            long millis = TimeUnit.NANOSECONDS.toMillis(Math.min(REQUEST_NANOS, remaining()));
            if (millis == 0) throw new TimeoutException("不足1ms，不再发起Admin调用");
            return (int) millis;
        }
    }

    record ClusterCall(Future<Collection<Node>> nodes, Future<Node> controller) {}
    interface Session {
        ClusterCall cluster(int timeoutMillis);
        Future<TopicDescription> topic(int timeoutMillis);
        // 只允许在隔离owner线程调用；返回必须表示I/O线程真正退出。
        void close(Duration timeout);
    }
    interface Factory { Session open(int timeoutMillis); }

    /** 白名单状态；不记录完整异常message、客户端配置或环境。 */
    static final class Evidence {
        volatile String stage = "not-started";
        volatile String pending = "none";
        volatile String lastCluster = "unobserved";
        volatile String lastTopic = "unobserved";
        volatile String failure = "none";
        volatile int attempts;
        volatile boolean closeStarted;
        volatile boolean closeCompleted;
        @Override public String toString() {
            return "stage=" + stage + ", attempts=" + attempts + ", pending=" + pending
                    + ", cluster=" + lastCluster + ", topic=" + lastTopic + ", failure=" + failure
                    + ", closeStarted=" + closeStarted + ", closeCompleted=" + closeCompleted;
        }
    }

    private ReplicaRecovery() {}

    static TopicDescription await(
            String survivingBootstrap, Uuid topicId, int stoppedId, Set<Integer> survivors,
            Duration timeout, Evidence evidence) throws InterruptedException {
        Deadline deadline = new Deadline(SYSTEM_TIME, timeout);
        Factory factory = timeoutMillis -> {
            Admin admin = Admin.create(Map.of(
                    "bootstrap.servers", survivingBootstrap,
                    "client.id", "replica-recovery-observer",
                    "default.api.timeout.ms", Integer.toString(timeoutMillis),
                    "request.timeout.ms", Integer.toString(timeoutMillis)));
            return new Session() {
                public ClusterCall cluster(int millis) {
                    var result = admin.describeCluster(new DescribeClusterOptions().timeoutMs(millis));
                    return new ClusterCall(result.nodes(), result.controller());
                }
                public Future<TopicDescription> topic(int millis) {
                    // Kafka3.9.1按名称查询会先隐式describeCluster()且不继承Options预算。
                    // 按已确认UUID查询直接使用Metadata API，不开第二套隐藏deadline。
                    return admin.describeTopics(TopicCollection.ofTopicIds(List.of(topicId)),
                                    new DescribeTopicsOptions().timeoutMs(millis))
                            .topicIdValues().get(topicId);
                }
                public void close(Duration timeout) {
                    // 3.9.1 ZERO设置立即hard-shutdown，却执行join(0)。只能在owner内调用。
                    // close会吞下InterruptedException并恢复标志；清除后重试，不能误报已退出。
                    boolean interrupted = Thread.interrupted();
                    while (true) {
                        admin.close(timeout);
                        if (!Thread.interrupted()) break;
                        interrupted = true;
                    }
                    if (interrupted) Thread.currentThread().interrupt();
                }
            };
        };
        FutureTask<TopicDescription> lifecycle = new FutureTask<>(
                () -> observe(factory, topicId, stoppedId, survivors, deadline, evidence));
        // Admin.create可同步DNS解析，close(0)可阻塞；二者均在同一个可审查的生命周期内。
        Thread owner = new Thread(lifecycle, "replica-recovery-owner");
        owner.setDaemon(true);
        owner.start();
        try {
            return awaitLifecycle(lifecycle, deadline, evidence);
        } catch (InterruptedException interrupted) {
            owner.interrupt();
            Thread.currentThread().interrupt();
            throw interrupted;
        } catch (AssertionError failure) {
            owner.interrupt();
            throw failure;
        }
    }

    static TopicDescription awaitLifecycle(
            Future<TopicDescription> lifecycle, Deadline deadline, Evidence evidence)
            throws InterruptedException {
        try {
            deadline.check();
            TopicDescription result = lifecycle.get(deadline.remaining(), TimeUnit.NANOSECONDS);
            deadline.check();
            if (!evidence.closeCompleted) throw new AssertionError("观察器关闭未确认：" + evidence);
            return result;
        } catch (ExecutionException | TimeoutException failure) {
            throw new AssertionError("恢复合同未完成（不得据此判定Kafka已恢复）：boundaryFailure="
                    + safeFailure(failure) + ", elapsedMs="
                    + ((deadline.time.nanoTime() - deadline.started) / 1_000_000) + ", " + evidence);
        }
    }

    // 可注入时钟/探针，公开纯测试不启动Kafka；只有生命周期返回才能判定成功。
    static TopicDescription observe(
            Factory factory, Uuid topicId, int stoppedId, Set<Integer> survivors,
            Deadline deadline, Evidence evidence) throws Exception {
        if (topicId == null || topicId.equals(Uuid.ZERO_UUID)
                || survivors.size() != 2 || survivors.contains(stoppedId)) {
            throw new IllegalArgumentException("必须提供故障前topic UUID与两个未停止broker ID");
        }
        Session session = null;
        try {
            evidence.stage = "admin-create";
            session = factory.open(deadline.apiMillis());
            while (true) {
                deadline.check();
                if (Thread.currentThread().isInterrupted()) throw new InterruptedException();
                evidence.attempts++;
                try {
                    evidence.stage = "describe-cluster";
                    ClusterCall cluster = session.cluster(deadline.apiMillis());
                    Collection<Node> nodes = waitFor(cluster.nodes(), deadline, evidence, "cluster-nodes");
                    Node controller = waitFor(cluster.controller(), deadline, evidence, "cluster-controller");
                    Set<Integer> nodeIds = ids(nodes);
                    evidence.lastCluster = "nodes=" + nodeIds + ", controller=" + id(controller);
                    evidence.stage = "describe-topic-id";
                    TopicDescription topic = waitFor(session.topic(deadline.apiMillis()), deadline,
                            evidence, "topic-id");
                    evidence.lastTopic = partitionEvidence(topic);
                    deadline.check();
                    if (nodeIds.containsAll(survivors) && survivors.contains(id(controller))
                            && recovered(topic, topicId, stoppedId, survivors)) return topic;
                } catch (ExecutionException failure) {
                    evidence.failure = safeFailure(failure);
                    if (failure.getCause() instanceof InterruptException) {
                        Thread.currentThread().interrupt();
                        throw failure;
                    }
                    if (!transientFailure(failure.getCause())) throw failure;
                }
                long remaining = deadline.remaining();
                if (remaining > 0) deadline.time.pause(Math.min(POLL_NANOS, remaining));
            }
        } catch (Exception failure) {
            evidence.failure = safeFailure(failure);
            throw failure;
        } finally {
            if (session != null) {
                evidence.stage = "admin-close";
                evidence.closeStarted = true;
                // 不另起close预算；外层等待始终使用最初deadline。
                session.close(Duration.ZERO);
                evidence.closeCompleted = true;
                evidence.stage = "closed";
            }
        }
    }

    static <T> T waitFor(Future<T> pending, Deadline deadline, Evidence evidence, String operation)
            throws InterruptedException, ExecutionException, TimeoutException {
        while (true) {
            deadline.check();
            evidence.pending = operation + ":done=" + pending.isDone();
            try {
                T result = pending.get(Math.min(GET_NANOS, deadline.remaining()), TimeUnit.NANOSECONDS);
                deadline.check(); // 拒绝超时之后才返回的成功快照。
                evidence.pending = operation + ":terminal";
                return result;
            } catch (ExecutionException failure) {
                evidence.pending = operation + ":terminal-failure";
                throw failure;
            } catch (TimeoutException callerTimeout) {
                // get超时不撤回Kafka RPC。保留同一个Future，不cancel、不重叠新请求。
                evidence.pending = operation + ":caller-timeout,done=" + pending.isDone();
                deadline.check();
            }
        }
    }

    static boolean recovered(TopicDescription topic, Uuid topicId, int stoppedId, Set<Integer> survivors) {
        if (topic == null || !topicId.equals(topic.topicId()) || topic.partitions().size() != 1) return false;
        var partition = topic.partitions().getFirst();
        Set<Integer> replicas = ids(partition.replicas());
        Set<Integer> isr = ids(partition.isr());
        return partition.partition() == 0 && replicas.equals(Set.of(1, 2, 3))
                && partition.replicas().size() == 3 && partition.isr().size() == 2
                && isr.equals(survivors) && !isr.contains(stoppedId)
                && survivors.contains(id(partition.leader())) && isr.contains(id(partition.leader()));
    }

    static String partitionEvidence(TopicDescription topic) {
        if (topic == null) return "null";
        return "partitions=" + topic.partitions().stream().map(p -> "p=" + p.partition()
                + ", leader=" + id(p.leader()) + ", replicas=" + ids(p.replicas())
                + ", isr=" + ids(p.isr())).toList();
    }
    private static Set<Integer> ids(Collection<Node> nodes) {
        return nodes.stream().map(Node::id).collect(Collectors.toSet());
    }
    private static int id(Node node) { return node == null ? -1 : node.id(); }
    private static boolean transientFailure(Throwable failure) {
        return failure instanceof UnknownTopicOrPartitionException
                || failure instanceof UnknownTopicIdException
                || failure instanceof LeaderNotAvailableException
                || failure instanceof org.apache.kafka.common.errors.TimeoutException;
    }
    private static String safeFailure(Throwable failure) {
        StringBuilder types = new StringBuilder();
        for (int depth = 0; failure != null && depth < 5; depth++, failure = failure.getCause()) {
            if (depth > 0) types.append(" <- ");
            types.append(failure.getClass().getName());
        }
        return types.toString();
    }
}
