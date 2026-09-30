package labs;

import java.time.Duration;
import java.util.concurrent.TimeUnit;

public final class BoundedExecutorUsage {
    public static void main(String[] args) throws Exception {
        var pool = new BoundedExecutor(1, 2, 2);
        try {
            var future = pool.submit(() -> "订单已校验");
            System.out.println(future.get(2, TimeUnit.SECONDS));
        } finally {
            pool.shutdown(Duration.ofSeconds(2));
            System.out.println("池已退出=" + pool.awaitStopped(Duration.ofSeconds(2)));
        }
    }
}
