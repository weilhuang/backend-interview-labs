package labs.messaging;

import java.util.HashSet;
import java.util.Set;

/** 进程内对照模型，只验证消息契约与幂等算法，不能替代数据库持久化。 */
public final class Lab {
    private final Set<String> seen = new HashSet<>();
    private long total;

    public synchronized boolean accept(Event event) {
        // 学习区开始
        if (!seen.add(event.id())) return false;
        try {
            total = Math.addExact(total, event.cents());
            return true;
        } catch (ArithmeticException overflow) {
            seen.remove(event.id());
            throw overflow;
        }
        // 学习区结束
    }

    public synchronized long total() {
        return total;
    }
}
