package labs.capstone;

import java.time.Duration;

/** C14-04：把接单就绪与下游积压分开；绝不能通过清空表来恢复。 */
public final class RecoveryPolicy {
    private RecoveryPolicy() {}

    public record Decision(boolean ready, boolean degraded, String action) {}

    public static Decision decide(
            boolean database, boolean redis, boolean kafka, boolean rpc, long pending, long limit) {
        // 学习区开始
        if (pending < 0 || limit < 1) throw new IllegalArgumentException("积压和容量上限不合法");
        if (!database) return new Decision(false, true, "暂停接单，检查MySQL连接与恢复状态");
        if (pending >= limit) return new Decision(false, true, "积压达到预算，拒绝新单并优先重放");
        if (!kafka || !rpc) return new Decision(true, true, "允许预算内接单，保留outbox并恢复下游");
        if (!redis) return new Decision(true, true, "绕过缓存查询MySQL，限制数据库压力");
        return new Decision(true, false, "正常接单并持续推进读模型");
        // 学习区结束
    }

    public static Duration retryDelay(int attempt) {
        if (attempt < 0) throw new IllegalArgumentException("重试次数不能为负");
        return Duration.ofMillis(250L << Math.min(attempt, 6));
    }
}
