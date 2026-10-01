package labs.jvm;

import java.util.*;
import java.util.concurrent.*;
import java.util.concurrent.locks.LockSupport;

public final class IncidentMain {
    private static final List<byte[]> retained = new ArrayList<>();
    private static volatile long checksum;

    public static void main(String[] args) throws Exception {
        if (args.length != 1 || !Set.of("cpu", "lock", "retention", "pool").contains(args[0]))
            throw new IllegalArgumentException("只允许cpu、lock、retention、pool");
        String mode = args[0];
        var release = new CountDownLatch(1);
        List<Thread> workers = new ArrayList<>();
        ThreadPoolExecutor executor = null;
        long deadline = System.nanoTime() + TimeUnit.SECONDS.toNanos(12);
        try {
            switch (mode) {
                case "cpu" ->
                        workers.add(
                                Thread.ofPlatform()
                                        .name("实验-CPU热点")
                                        .start(
                                                () -> {
                                                    long end =
                                                            System.nanoTime()
                                                                    + TimeUnit.SECONDS.toNanos(10);
                                                    long x = 1;
                                                    while (System.nanoTime() < end
                                                            && !Thread.currentThread()
                                                                    .isInterrupted()) {
                                                        for (int i = 0; i < 200000; i++)
                                                            x = x * 1664525 + 1013904223;
                                                        checksum = x;
                                                        LockSupport.parkNanos(
                                                                TimeUnit.MILLISECONDS.toNanos(10));
                                                    }
                                                }));
                case "lock" -> {
                    Object monitor = new Object();
                    var held = new CountDownLatch(1);
                    workers.add(
                            Thread.ofPlatform()
                                    .name("实验-持锁等待")
                                    .start(
                                            () -> {
                                                synchronized (monitor) {
                                                    held.countDown();
                                                    await(release);
                                                }
                                            }));
                    if (!held.await(2, TimeUnit.SECONDS)) throw new IllegalStateException("锁实验未就绪");
                    workers.add(
                            Thread.ofPlatform()
                                    .name("实验-竞争锁")
                                    .start(
                                            () -> {
                                                synchronized (monitor) {
                                                    checksum++;
                                                }
                                            }));
                }
                case "retention" -> {
                    for (int i = 0; i < 16; i++) {
                        byte[] block = new byte[262144];
                        block[0] = (byte) i;
                        retained.add(block);
                    }
                }
                case "pool" -> {
                    var started = new CountDownLatch(2);
                    executor =
                            new ThreadPoolExecutor(
                                    2,
                                    2,
                                    0L,
                                    TimeUnit.MILLISECONDS,
                                    new ArrayBlockingQueue<>(2),
                                    Thread.ofPlatform().name("实验-池-", 0).factory(),
                                    new ThreadPoolExecutor.AbortPolicy());
                    Runnable waiting =
                            () -> {
                                started.countDown();
                                await(release);
                            };
                    executor.execute(waiting);
                    executor.execute(waiting);
                    if (!started.await(2, TimeUnit.SECONDS))
                        throw new IllegalStateException("线程池未就绪");
                    executor.execute(waiting);
                    executor.execute(waiting);
                    try {
                        executor.execute(waiting);
                        throw new AssertionError("第5个任务应被拒绝");
                    } catch (RejectedExecutionException expected) {
                        System.out.println("第5个任务按合同拒绝；活跃=2，排队=2");
                    }
                }
            }
            System.out.println(
                    "READY 模式="
                            + mode
                            + "，PID="
                            + ProcessHandle.current().pid()
                            + "，保留字节="
                            + (retained.size() * 262144));
            System.out.flush();
            long remaining = deadline - System.nanoTime();
            if (remaining > 0) release.await(remaining, TimeUnit.NANOSECONDS);
        } finally {
            release.countDown();
            retained.clear();
            for (Thread t : workers) t.interrupt();
            for (Thread t : workers) t.join(2000);
            if (executor != null) {
                executor.shutdownNow();
                if (!executor.awaitTermination(2, TimeUnit.SECONDS))
                    throw new IllegalStateException("线程池未停止");
            }
            System.out.println("实验已清理，保留块=" + retained.size() + "，校验=" + checksum);
        }
    }

    private static void await(CountDownLatch latch) {
        try {
            latch.await(12, TimeUnit.SECONDS);
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
        }
    }
}
