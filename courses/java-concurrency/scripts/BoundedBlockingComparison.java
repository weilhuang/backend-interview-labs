import java.util.*;
import java.util.concurrent.*;
import java.util.concurrent.atomic.AtomicInteger;

// 观察用合成阻塞负载；sleep仅代表相同的外部等待，不充当测试线程的协调工具。
public final class BoundedBlockingComparison {
    public static void main(String[] args) throws Exception {
        if (args.length != 1 || !Set.of("platform", "virtual").contains(args[0])) {
            throw new IllegalArgumentException("参数只能为platform或virtual");
        }
        int requests = 16;
        int downstreamLimit = 2;
        var slots = new Semaphore(downstreamLimit);
        var active = new AtomicInteger();
        var maximum = new AtomicInteger();
        var tasks = new ArrayList<Future<Long>>();
        long started = System.nanoTime();
        ExecutorService executor =
                args[0].equals("virtual")
                        ? Executors.newVirtualThreadPerTaskExecutor()
                        : Executors.newFixedThreadPool(8);
        try (executor) {
            for (int i = 0; i < requests; i++) {
                long submitted = System.nanoTime();
                tasks.add(
                        executor.submit(
                                () -> {
                                    slots.acquire();
                                    try {
                                        int count = active.incrementAndGet();
                                        maximum.accumulateAndGet(count, Math::max);
                                        try {
                                            Thread.sleep(40);
                                        } finally {
                                            active.decrementAndGet();
                                        }
                                    } finally {
                                        slots.release();
                                    }
                                    return System.nanoTime() - submitted;
                                }));
            }
            var latency = new ArrayList<Long>();
            for (var task : tasks) {
                latency.add(task.get(3, TimeUnit.SECONDS));
            }
            Collections.sort(latency);
            if (maximum.get() > downstreamLimit || slots.availablePermits() != downstreamLimit) {
                throw new AssertionError("资源不变量被破坏");
            }
            double elapsedMillis = (System.nanoTime() - started) / 1_000_000.0;
            double p50 = latency.get((latency.size() - 1) / 2) / 1_000_000.0;
            double p95 = latency.get((int) Math.ceil(latency.size() * 0.95) - 1) / 1_000_000.0;
            System.out.printf(
                    Locale.ROOT,
                    "模式=%s，请求=%d，下游最大并发=%d，总毫秒=%.3f，P50=%.3f，P95=%.3f%n",
                    args[0],
                    requests,
                    maximum.get(),
                    elapsedMillis,
                    p50,
                    p95);
            System.out.println("这是小规模单次观察，不是性能排名或生产容量承诺");
        } finally {
            executor.shutdownNow();
            if (!executor.awaitTermination(2, TimeUnit.SECONDS)) {
                throw new IllegalStateException("实验线程未退出");
            }
        }
    }
}
