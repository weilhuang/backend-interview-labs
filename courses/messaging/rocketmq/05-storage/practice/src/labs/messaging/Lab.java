package labs.messaging;

import java.util.HashSet;
import java.util.List;
import java.util.Set;

public final class Lab {
    /** 对照已获得发送确认的业务ID与恢复后的读取结果，重复投递不能掩盖缺失。 */
    public static List<String> missing(Set<String> acknowledged, List<Event> recovered) {
        // 学习区开始
        Set<String> actual = new HashSet<>();
        for (Event event : recovered) actual.add(event.id());
        return acknowledged.stream().filter(id -> !actual.contains(id)).sorted().toList();
        // 学习区结束
    }

    /** 这是确认边界教学模型，不是RocketMQ刷盘或复制源码。 */
    public record Durability(boolean synchronousFlush, int acknowledgedReplicas) {}

    public static String risk(Durability durability) {
        if (durability.acknowledgedReplicas() < 1) throw new IllegalArgumentException("副本数至少为一");
        if (!durability.synchronousFlush()) return "进程已确认仍可能存在未刷盘窗口";
        if (durability.acknowledgedReplicas() == 1) return "已同步刷盘但仍有单机磁盘故障风险";
        return "已满足声明副本确认数，仍需验证故障域与恢复";
    }
}
