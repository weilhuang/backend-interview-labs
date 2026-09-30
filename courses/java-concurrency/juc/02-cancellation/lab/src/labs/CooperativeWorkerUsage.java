package labs;

import java.time.Duration;
import java.util.concurrent.CountDownLatch;

public final class CooperativeWorkerUsage {
    public static void main(String[] args) throws Exception {
        var ready = new CountDownLatch(1);
        var worker =
                new CooperativeWorker(
                        () -> {
                            ready.countDown();
                            new CountDownLatch(1).await();
                        },
                        () -> System.out.println("资源已释放"));
        worker.start();
        ready.await();
        System.out.println("关闭完成=" + worker.cancelAndAwait(Duration.ofSeconds(2)));
    }
}
