import jdk.jfr.Recording;

import labs.VirtualGateway;

import java.nio.file.*;
import java.time.Duration;
import java.util.*;
import java.util.concurrent.*;

// 独立诊断进程：最多8请求/2下游并发/15秒等待/8MiB记录，不访问任何真实服务。
public final class ConcurrencyDiagnostics {
    public static void main(String[] args) throws Exception {
        if (args.length != 1) throw new IllegalArgumentException("需要一个记录输出文件路径");
        Path output = Path.of(args[0]);
        var ready = new CountDownLatch(2);
        var release = new CountDownLatch(1);
        try (var recording = new Recording();
                var gateway = new VirtualGateway(2, 8)) {
            recording.setName("受控虚拟线程诊断");
            recording.setMaxSize(8L * 1024 * 1024);
            recording.setMaxAge(Duration.ofSeconds(20));
            recording.enable("jdk.ThreadPark").withThreshold(Duration.ZERO);
            recording.enable("jdk.VirtualThreadStart");
            recording.enable("jdk.VirtualThreadEnd");
            recording.enable("jdk.VirtualThreadPinned").withThreshold(Duration.ZERO);
            recording.start();
            var tasks = new ArrayList<Future<Integer>>();
            for (int i = 0; i < 8; i++) {
                int id = i;
                tasks.add(
                        gateway.submit(
                                () -> {
                                    ready.countDown();
                                    release.await();
                                    return id;
                                }));
            }
            if (!ready.await(3, TimeUnit.SECONDS)) throw new IllegalStateException("实验未到达受控等待状态");
            System.out.println("READY pid=" + ProcessHandle.current().pid());
            System.out.flush();
            Thread.ofPlatform()
                    .daemon()
                    .name("实验-控制输入")
                    .start(
                            () -> {
                                try {
                                    System.in.read();
                                } catch (Exception ignored) {
                                } finally {
                                    release.countDown();
                                }
                            });
            release.await(15, TimeUnit.SECONDS);
            release.countDown();
            int sum = 0;
            for (var task : tasks) sum += task.get(2, TimeUnit.SECONDS);
            if (sum != 28) throw new AssertionError("业务结果不正确");
            recording.stop();
            recording.dump(output);
            System.out.println("业务合计=" + sum);
            System.out.println("JFR=" + output);
        } finally {
            release.countDown();
        }
    }
}
