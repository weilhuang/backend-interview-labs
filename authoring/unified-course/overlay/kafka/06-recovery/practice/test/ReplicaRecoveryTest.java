import static org.junit.jupiter.api.Assertions.*;

import org.apache.kafka.clients.admin.TopicDescription;
import org.apache.kafka.common.Node;
import org.apache.kafka.common.TopicPartitionInfo;
import org.apache.kafka.common.Uuid;
import org.apache.kafka.common.errors.TopicAuthorizationException;
import org.junit.jupiter.api.Test;

import java.time.Duration;
import java.util.ArrayList;
import java.util.Collection;
import java.util.List;
import java.util.Set;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.ExecutionException;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.TimeoutException;

/** 公开退化反例；只验证本地预算/观察合同，不能替代ReplicaTest真实Kafka验收。 */
class ReplicaRecoveryTest {
    private static final Uuid TOPIC_ID = new Uuid(1, 2);
    private static final List<Node> NODES = List.of(
            new Node(1, "broker1", 9092), new Node(2, "broker2", 9092), new Node(3, "broker3", 9092));
    private static final Set<Integer> SURVIVORS = Set.of(2, 3);

    @Test
    void 必须新leader及两个未停止ISR且RF仍为三() {
        assertTrue(ReplicaRecovery.recovered(topic(2, List.of(2, 3)), TOPIC_ID, 1, SURVIVORS));
        assertTrue(ReplicaRecovery.recovered(topic(3, List.of(1, 3)), TOPIC_ID, 2, Set.of(1, 3)));
        assertTrue(ReplicaRecovery.recovered(topic(1, List.of(1, 2)), TOPIC_ID, 3, Set.of(1, 2)));
        List<TopicDescription> bad = new ArrayList<>();
        bad.add(null);
        bad.add(new TopicDescription("events", false, List.of(), Set.of(), TOPIC_ID));
        bad.add(topic(1, List.of(2, 3))); // 旧leader
        bad.add(topic(-1, List.of(2, 3))); // 无leader
        bad.add(topic(2, List.of(2))); // ISR1
        bad.add(topic(2, List.of(1, 2))); // size=2却含死节点
        bad.add(topic(2, List.of(1, 2, 3))); // 注入后的陈旧ISR3
        bad.add(topic(3, List.of(2, 2))); // 重复ISR
        bad.add(new TopicDescription("events", false,
                List.of(new TopicPartitionInfo(0, NODES.get(1), NODES.subList(1, 3), NODES.subList(1, 3))),
                Set.of(), TOPIC_ID)); // RF2不得降级过关
        bad.add(new TopicDescription("events", false, topic(2, List.of(2, 3)).partitions(),
                Set.of(), new Uuid(9, 9))); // 不得接受重建的同名主题
        for (TopicDescription candidate : bad) {
            assertFalse(ReplicaRecovery.recovered(candidate, TOPIC_ID, 1, SURVIVORS));
        }
    }

    @Test
    void get超时保留同一pending不撤销也不新建重叠请求() throws Exception {
        FakeTime time = new FakeTime();
        FakeSession session = new FakeSession(time);
        TimedFuture<TopicDescription> pending = new TimedFuture<>(time, 550, topic(2, List.of(2, 3)));
        session.topicReply = pending;
        run(session, time, 1000);
        assertEquals(1, session.clusterCalls);
        assertEquals(1, session.topicCalls);
        assertEquals(List.of(200L, 200L, 200L), pending.waitMillis);
        assertEquals(0, pending.cancels);
        assertEquals(550, time.millis());
        assertEquals(1, session.closes);
    }

    @Test
    void 请求与末次休眠裁剪到同一deadline且不足一毫秒不发RPC() throws Exception {
        FakeTime time = new FakeTime();
        FakeSession session = new FakeSession(time);
        session.topicReply = CompletableFuture.completedFuture(topic(2, List.of(2)));
        assertThrows(TimeoutException.class, () -> run(session, time, 725));
        assertEquals(List.of(725, 625, 525, 425, 325, 225, 125, 25), session.topicBudgets);
        assertEquals(List.of(100L, 100L, 100L, 100L, 100L, 100L, 100L, 25L), time.pauses);
        assertEquals(725, time.millis());
        assertEquals(1, session.closes);
        var tiny = new ReplicaRecovery.Deadline(time, Duration.ofNanos(999_999));
        assertThrows(TimeoutException.class, tiny::apiMillis);
        assertEquals(5000, new ReplicaRecovery.Deadline(time, Duration.ofSeconds(75)).apiMillis());
    }

    @Test
    void 逾期成功快照不得通过() {
        FakeTime time = new FakeTime();
        FakeSession session = new FakeSession(time);
        session.topicReply = new CompletableFuture<>() {
            @Override public TopicDescription get(long timeout, TimeUnit unit) {
                time.now += Duration.ofMillis(300).toNanos();
                return topic(2, List.of(2, 3));
            }
        };
        assertThrows(TimeoutException.class, () -> run(session, time, 250));
        assertEquals(1, session.topicCalls);
        assertEquals(1, session.closes);
    }

    @Test
    void observer不可达必须失败且只保留一个请求() {
        FakeTime time = new FakeTime();
        FakeSession session = new FakeSession(time);
        TimedFuture<Collection<Node>> unreachable = new TimedFuture<>(time, Long.MAX_VALUE, NODES);
        session.nodes = unreachable;
        assertThrows(TimeoutException.class, () -> run(session, time, 500));
        assertEquals(1, session.clusterCalls);
        assertEquals(0, session.topicCalls);
        assertEquals(List.of(200L, 200L, 100L), unreachable.waitMillis);
        assertEquals(0, unreachable.cancels);
        assertEquals(1, session.closes);
    }

    @Test
    void 存活broker缺失或controller仍是死节点必须失败() {
        for (boolean missingBroker : List.of(false, true)) {
            FakeTime time = new FakeTime();
            FakeSession session = new FakeSession(time);
            if (missingBroker) session.nodes = CompletableFuture.completedFuture(List.of(NODES.get(1)));
            else session.controller = CompletableFuture.completedFuture(NODES.getFirst());
            assertThrows(TimeoutException.class, () -> run(session, time, 250));
            assertEquals(1, session.closes);
        }
    }

    @Test
    void 底层持续超时不能退化为通过() {
        FakeTime time = new FakeTime();
        FakeSession session = new FakeSession(time);
        session.topicReply = CompletableFuture.failedFuture(new org.apache.kafka.common.errors.TimeoutException());
        assertThrows(TimeoutException.class, () -> run(session, time, 250));
        assertEquals(3, session.topicCalls);
        assertEquals(250, time.millis());
        assertEquals(1, session.closes);
    }

    @Test
    void 授权错误立即失败不按暂态重试() {
        FakeTime time = new FakeTime();
        FakeSession session = new FakeSession(time);
        session.topicReply = CompletableFuture.failedFuture(new TopicAuthorizationException("events"));
        var failure = assertThrows(ExecutionException.class, () -> run(session, time, 1000));
        assertInstanceOf(TopicAuthorizationException.class, failure.getCause());
        assertEquals(1, session.topicCalls);
        assertEquals(0, time.millis());
        assertEquals(1, session.closes);
    }

    @Test
    void Admin创建耗时耗尽预算则只清理不发请求() {
        FakeTime time = new FakeTime();
        FakeSession session = new FakeSession(time);
        var deadline = new ReplicaRecovery.Deadline(time, Duration.ofMillis(250));
        assertThrows(TimeoutException.class, () -> ReplicaRecovery.observe(millis -> {
            assertEquals(250, millis);
            time.now += Duration.ofMillis(250).toNanos();
            return session;
        }, TOPIC_ID, 1, SURVIVORS, deadline, new ReplicaRecovery.Evidence()));
        assertEquals(0, session.clusterCalls);
        assertEquals(0, session.topicCalls);
        assertEquals(1, session.closes);
    }

    @Test
    void 关闭属于原预算且关闭后迟到成功仍失败() throws Exception {
        FakeTime time = new FakeTime();
        FakeSession session = new FakeSession(time);
        session.closeMillis = 250;
        var evidence = new ReplicaRecovery.Evidence();
        var deadline = new ReplicaRecovery.Deadline(time, Duration.ofMillis(250));
        var result = ReplicaRecovery.observe(ignored -> session, TOPIC_ID, 1, SURVIVORS, deadline, evidence);
        assertTrue(evidence.closeCompleted);
        assertThrows(AssertionError.class, () -> ReplicaRecovery.awaitLifecycle(
                CompletableFuture.completedFuture(result), deadline, evidence));
    }

    @Test
    void 关闭挂起不能因daemon或元数据成功而通过() {
        FakeTime time = new FakeTime();
        var evidence = new ReplicaRecovery.Evidence();
        evidence.stage = "admin-close";
        evidence.closeStarted = true;
        var deadline = new ReplicaRecovery.Deadline(time, Duration.ofMillis(250));
        TimedFuture<TopicDescription> stuckClose = new TimedFuture<>(time, Long.MAX_VALUE, topic(2, List.of(2, 3)));
        AssertionError failure = assertThrows(AssertionError.class,
                () -> ReplicaRecovery.awaitLifecycle(stuckClose, deadline, evidence));
        assertTrue(failure.getMessage().contains("closeCompleted=false"));
        assertEquals(250, time.millis());
        assertEquals(0, stuckClose.cancels);
    }

    @Test
    void 生命周期未确认close即使future成功也失败() {
        FakeTime time = new FakeTime();
        var evidence = new ReplicaRecovery.Evidence();
        assertThrows(AssertionError.class, () -> ReplicaRecovery.awaitLifecycle(
                CompletableFuture.completedFuture(topic(2, List.of(2, 3))),
                new ReplicaRecovery.Deadline(time, Duration.ofSeconds(1)), evidence));
    }

    @Test
    void 中断退出并执行清理不继续发新请求() {
        FakeTime time = new FakeTime();
        FakeSession session = new FakeSession(time);
        session.topicReply = new CompletableFuture<>() {
            @Override public TopicDescription get(long timeout, TimeUnit unit) throws InterruptedException {
                throw new InterruptedException("test interruption");
            }
        };
        assertThrows(InterruptedException.class, () -> run(session, time, 1000));
        assertEquals(1, session.topicCalls);
        assertEquals(1, session.closes);
    }

    @Test
    void 有界日志保留截断标志且拒绝凭据和配置行() {
        ReplicaEvidence evidence = new ReplicaEvidence();
        for (int i = 0; i < 130; i++) evidence.stage("test", "id=" + i);
        evidence.container(2, frame("[QuorumController id=2] elected leader password=do-not-copy"));
        evidence.container(2, frame("[KafkaRaftClient] transition " + "x".repeat(500)));
        String snapshot = evidence.snapshot();
        assertTrue(snapshot.contains("boundedEvents=120/120"));
        assertTrue(snapshot.contains("dropped=11"));
        assertTrue(snapshot.contains("filtered=1"));
        assertTrue(snapshot.contains("truncated=true"));
        assertFalse(snapshot.contains("do-not-copy"));
    }

 @Test void everySensitiveMarkerAcrossLineSeparatorsIsRejected() {
  for(String separator: new String[]{"\n", "\r", "\r\n", "\u0085", "\u2028", "\u2029"})
   for(String keyword: new String[]{"PASSWORD", "SeCrEt", "Token", "CREDENTIAL", "SASL", "sSl", "CONFIG", "ENVIRONMENT"}) {
    ReplicaEvidence evidence = new ReplicaEvidence();
    evidence.container(1,frame("[QuorumController id=1] elected leader"+separator+keyword+"=synthetic-do-not-copy"));
    String snapshot = evidence.snapshot();
    assertFalse(snapshot.contains("synthetic-do-not-copy"));
    assertTrue(snapshot.contains("filtered=1"));
    assertTrue(snapshot.contains("boundedEvents=0/120"));
   }
 }
 @Test void usefulNormalEventsAreRetained() {
  ReplicaEvidence evidence = new ReplicaEvidence();
  evidence.container(2,frame("[QuorumController id=2] elected leader"));
  assertTrue(evidence.snapshot().contains("elected leader"));
  assertTrue(evidence.snapshot().contains("boundedEvents=1/120"));
  assertTrue(evidence.snapshot().contains("filtered=0"));
 }

    private static org.testcontainers.containers.output.OutputFrame frame(String text) {
        return new org.testcontainers.containers.output.OutputFrame(
                org.testcontainers.containers.output.OutputFrame.OutputType.STDOUT,
                text.getBytes(java.nio.charset.StandardCharsets.UTF_8));
    }
    private static TopicDescription run(FakeSession session, FakeTime time, long millis) throws Exception {
        return ReplicaRecovery.observe(ignored -> session, TOPIC_ID, 1, SURVIVORS,
                new ReplicaRecovery.Deadline(time, Duration.ofMillis(millis)), new ReplicaRecovery.Evidence());
    }
    private static TopicDescription topic(int leader, List<Integer> isr) {
        Node node = leader < 0 ? Node.noNode() : NODES.get(leader - 1);
        return new TopicDescription("events", false, List.of(new TopicPartitionInfo(0, node, NODES,
                isr.stream().map(id -> NODES.get(id - 1)).toList())), Set.of(), TOPIC_ID);
    }
    private static final class FakeTime implements ReplicaRecovery.Time {
        long now;
        final List<Long> pauses = new ArrayList<>();
        public long nanoTime() { return now; }
        public void pause(long nanos) { pauses.add(TimeUnit.NANOSECONDS.toMillis(nanos)); now += nanos; }
        long millis() { return TimeUnit.NANOSECONDS.toMillis(now); }
    }
    private static final class FakeSession implements ReplicaRecovery.Session {
        final FakeTime time;
        int clusterCalls, topicCalls, closes;
        long closeMillis;
        final List<Integer> topicBudgets = new ArrayList<>();
        final List<Duration> closeBudgets = new ArrayList<>();
        Future<Collection<Node>> nodes = CompletableFuture.completedFuture(NODES.subList(1, 3));
        Future<Node> controller = CompletableFuture.completedFuture(NODES.get(1));
        Future<TopicDescription> topicReply = CompletableFuture.completedFuture(ReplicaRecoveryTest.topic(2, List.of(2, 3)));
        FakeSession(FakeTime time) { this.time = time; }
        public ReplicaRecovery.ClusterCall cluster(int millis) {
            clusterCalls++;
            return new ReplicaRecovery.ClusterCall(nodes, controller);
        }
        public Future<TopicDescription> topic(int millis) {
            topicCalls++;
            topicBudgets.add(millis);
            return topicReply;
        }
        public void close(Duration timeout) {
            assertEquals(Duration.ZERO, timeout, "不得另开关闭宽限预算");
            closeBudgets.add(timeout);
            closes++;
            time.now += Duration.ofMillis(closeMillis).toNanos();
        }
    }
    private static final class TimedFuture<T> implements Future<T> {
        final FakeTime time;
        final long readyMillis;
        final T result;
        int cancels;
        final List<Long> waitMillis = new ArrayList<>();
        TimedFuture(FakeTime time, long readyMillis, T result) {
            this.time = time; this.readyMillis = readyMillis; this.result = result;
        }
        public T get(long timeout, TimeUnit unit) throws TimeoutException {
            long wait = unit.toNanos(timeout);
            waitMillis.add(TimeUnit.NANOSECONDS.toMillis(wait));
            if (readyMillis == Long.MAX_VALUE || readyMillis * 1_000_000 > time.now + wait) {
                time.now += wait;
                throw new TimeoutException();
            }
            time.now = readyMillis * 1_000_000;
            return result;
        }
        public T get() { throw new AssertionError("禁止无预算get"); }
        public boolean cancel(boolean interrupt) { cancels++; return false; }
        public boolean isCancelled() { return false; }
        public boolean isDone() { return time.millis() >= readyMillis; }
    }
}
