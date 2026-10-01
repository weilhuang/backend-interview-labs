package labs.jvm;

import java.util.concurrent.*;
import java.util.concurrent.atomic.AtomicInteger;

public final class ResourceGate {
    private final Semaphore permits;
    private final AtomicInteger active = new AtomicInteger();
    private final AtomicInteger peak = new AtomicInteger();

    public ResourceGate(int maximum) {
        if (maximum < 1 || maximum > 8) throw new IllegalArgumentException("并发限制须为1至8");
        permits = new Semaphore(maximum);
    }

    public <T> T call(Callable<T> action) throws Exception {
        // 作答开始
        java.util.Objects.requireNonNull(action, "业务操作不能为空");
        permits.acquire();
        try {
            int now = active.incrementAndGet();
            peak.updateAndGet(previous -> previous > now ? previous : now);
            try {
                return action.call();
            } finally {
                active.decrementAndGet();
            }
        } finally {
            permits.release();
        }
        // 作答结束
    }

    public int active() {
        return active.get();
    }

    public int peak() {
        return peak.get();
    }

    public int available() {
        return permits.availablePermits();
    }
}
