package labs;

import java.time.Duration;
import java.util.concurrent.*;

public final class AsyncGatewayUsage {
    public static void main(String[] args) throws Exception {
        try (var pool = Executors.newFixedThreadPool(2);
                var timer = new AsyncGateway.RealTimer()) {
            var gateway = new AsyncGateway(pool, 2);
            var order = gateway.request("请求-42", () -> "订单:" + gateway.currentRequest());
            var recommendation =
                    gateway.<String>request(
                            "请求-42",
                            () -> {
                                throw new IllegalStateException("推荐暂不可用");
                            });
            System.out.println(
                    AsyncGateway.aggregate(order, recommendation, Duration.ofSeconds(2), timer)
                            .get(3, TimeUnit.SECONDS));
        }
    }
}
