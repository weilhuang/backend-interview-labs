package labs;

import java.time.Duration;
import java.util.Objects;
import java.util.concurrent.locks.AbstractQueuedSynchronizer;

public final class OneShotGate {
    private static final class Sync extends AbstractQueuedSynchronizer {
        protected int tryAcquireShared(int ignored) {
            // 答案开始：获取
            return getState() == 1 ? 1 : -1;
            // 答案结束：获取
        }

        protected boolean tryReleaseShared(int ignored) {
            // 答案开始：打开
            return compareAndSetState(0, 1);
            // 答案结束：打开
        }

        boolean opened() {
            return getState() == 1;
        }
    }

    private final Sync sync = new Sync();

    public void open() {
        sync.releaseShared(1);
    }

    public boolean isOpen() {
        return sync.opened();
    }

    public void await() throws InterruptedException {
        sync.acquireSharedInterruptibly(1);
    }

    public boolean await(Duration budget) throws InterruptedException {
        Objects.requireNonNull(budget);
        if (budget.isNegative()) throw new IllegalArgumentException("预算不能为负");
        return sync.tryAcquireSharedNanos(1, budget.toNanos());
    }
}
