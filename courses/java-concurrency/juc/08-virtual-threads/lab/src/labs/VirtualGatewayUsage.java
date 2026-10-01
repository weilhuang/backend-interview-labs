package labs;

import java.util.*;
import java.util.concurrent.*;

public final class VirtualGatewayUsage {
    public static void main(String[] args) throws Exception {
        try (var gateway = new VirtualGateway(2, 8)) {
            var tasks = new ArrayList<Future<String>>();
            for (int i = 0; i < 8; i++) {
                int id = i;
                tasks.add(
                        gateway.submit(
                                () -> "订单" + id + "，虚拟线程=" + Thread.currentThread().isVirtual()));
            }
            for (var task : tasks) System.out.println(task.get(2, TimeUnit.SECONDS));
        }
    }
}
