package labs;

import java.time.Duration;
import java.util.Objects;
import java.util.concurrent.*;
import java.util.concurrent.atomic.AtomicReference;

public final class CooperativeWorker {
    @FunctionalInterface
    public interface Work {
        void run() throws Exception;
    }

    private final CountDownLatch started = new CountDownLatch(1), stopped = new CountDownLatch(1);
    private final AtomicReference<Throwable> failure = new AtomicReference<>();
    private final Thread thread;

    public CooperativeWorker(Work work, Runnable cleanup) {
        Objects.requireNonNull(work);
        Objects.requireNonNull(cleanup);
        thread =
                Thread.ofPlatform()
                        .daemon()
                        .name("实验-可取消工作者")
                        .unstarted(
                                () -> {
                                    started.countDown();
                                    try {
                                        work.run();
                                    } catch (InterruptedException cancelled) {
                                        Thread.currentThread().interrupt();
                                    } catch (Throwable problem) {
                                        failure.set(problem);
                                    } finally {
                                        try {
                                            cleanup.run();
                                        } catch (Throwable problem) {
                                            failure.compareAndSet(null, problem);
                                        } finally {
                                            stopped.countDown();
                                        }
                                    }
                                });
    }

    public void start() {
        thread.start();
    }

    public boolean awaitStarted(Duration budget) throws InterruptedException {
        return started.await(nanos(budget), TimeUnit.NANOSECONDS);
    }

    public boolean awaitStopped(Duration budget) throws InterruptedException {
        return stopped.await(nanos(budget), TimeUnit.NANOSECONDS);
    }

    public boolean cancelAndAwait(Duration budget) throws InterruptedException {
        // 答案开始：取消
        long wait = nanos(budget);
        thread.interrupt();
        return stopped.await(wait, TimeUnit.NANOSECONDS);
        // 答案结束：取消
    }

    public Throwable failure() {
        return failure.get();
    }

    public boolean alive() {
        return thread.isAlive();
    }

    private static long nanos(Duration budget) {
        Objects.requireNonNull(budget);
        if (budget.isNegative()) throw new IllegalArgumentException("预算不能为负");
        return budget.toNanos();
    }
}
