import org.testcontainers.containers.output.OutputFrame;

import java.util.ArrayDeque;
import java.util.Deque;
import java.util.Locale;

/** 启动前注册，leader容器被stop/remove前即保留控制面日志；失败时不追加远程诊断RPC。 */
final class ReplicaEvidence {
    private static final int LIMIT = 120;
    private static final int WIDTH = 400;
    private final Deque<String> lines = new ArrayDeque<>();
    private final long started = System.nanoTime();
    private long dropped;
    private long filtered;
    private boolean truncated;

    synchronized void container(int brokerId, OutputFrame frame) {
        String line = frame.getUtf8StringWithoutLineEnding();
        String lower = line.toLowerCase(Locale.ROOT);
        // 限定生命周期/选主/ISR事件；不接受配置、环境、认证材料或任意异常堆栈dump。
        boolean event = lower.contains("transition") || lower.contains("elected")
                || lower.contains("leader change") || lower.contains("isr")
                || lower.contains("fenced") || lower.contains("unfenced")
                || lower.contains("shutting down") || lower.contains("fatal");
        boolean logger = line.contains("KafkaRaftClient") || line.contains("QuorumController")
                || line.contains("BrokerServer") || line.contains("ReplicaManager")
                || line.contains("Partition") || line.contains("BrokerLifecycleManager");
        boolean unsafe = java.util.stream.Stream.of(
                "password", "secret", "token", "credential", "sasl", "ssl", "config", "environment")
                .anyMatch(lower::contains);
        if (!event || !logger || unsafe) { filtered++; return; }
        line = line.replaceAll("[\\p{Cntrl}]", " ");
        if (line.length() > WIDTH) { line = line.substring(0, WIDTH); truncated = true; }
        add("broker=" + brokerId + " stream=" + frame.getType() + " " + line);
    }

    synchronized void stage(String stage, String safeFields) { add("stage=" + stage + " " + safeFields); }

    private void add(String line) {
        if (lines.size() == LIMIT) { lines.removeFirst(); dropped++; }
        lines.addLast("elapsedMs=" + ((System.nanoTime() - started) / 1_000_000) + " " + line);
    }

    synchronized String snapshot() {
        return "boundedEvents=" + lines.size() + "/" + LIMIT + ", dropped=" + dropped
                + ", filtered=" + filtered + ", truncated=" + truncated + "\n"
                + String.join("\n", lines);
    }
}
