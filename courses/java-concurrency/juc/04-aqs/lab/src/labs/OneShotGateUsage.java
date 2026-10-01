package labs;

import java.util.concurrent.*;

public final class OneShotGateUsage {
    public static void main(String[] args) throws Exception {
        var gate = new OneShotGate();
        var done = new CountDownLatch(2);
        var permits = new Semaphore(1);
        try (var pool = Executors.newFixedThreadPool(2)) {
            for (int i = 0; i < 2; i++)
                pool.submit(
                        () -> {
                            try {
                                gate.await();
                                permits.acquire();
                                try {
                                    System.out.println("单许可执行区");
                                } finally {
                                    permits.release();
                                }
                            } catch (InterruptedException e) {
                                Thread.currentThread().interrupt();
                            } finally {
                                done.countDown();
                            }
                        });
            gate.open();
            if (!done.await(2, TimeUnit.SECONDS)) throw new IllegalStateException("任务未完成");
        }
        System.out.println("全部完成");
    }
}
