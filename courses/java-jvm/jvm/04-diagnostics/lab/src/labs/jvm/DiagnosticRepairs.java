package labs.jvm;

import java.util.*;
import java.util.concurrent.*;

public final class DiagnosticRepairs {
    private DiagnosticRepairs() {}

    public static long finiteChecksum(int count) {
        if (count < 0 || count > 1000000) throw new IllegalArgumentException("工作量须为0至1000000");
        long sum = 0;
        for (int i = 0; i < count; i++) sum += i;
        return sum;
    }

    public static int boundedRetention(int count, int maximum) {
        if (count < 0 || count > 64 || maximum < 1 || maximum > 8)
            throw new IllegalArgumentException("保留预算非法");
        Deque<byte[]> items = new ArrayDeque<>();
        try {
            for (int i = 0; i < count; i++) {
                if (items.size() == maximum) items.removeFirst();
                items.addLast(new byte[1024]);
            }
            return items.size();
        } finally {
            items.clear();
        }
    }

    public static final class Counter {
        private int count;

        public int incrementAfter(Callable<?> outsideLock) throws Exception {
            outsideLock.call();
            synchronized (this) {
                return ++count;
            }
        }

        public synchronized int value() {
            return count;
        }
    }

    public static boolean closePool(ThreadPoolExecutor pool) throws InterruptedException {
        pool.shutdown();
        if (pool.awaitTermination(1, TimeUnit.SECONDS)) return true;
        pool.shutdownNow();
        return pool.awaitTermination(2, TimeUnit.SECONDS);
    }
}
