package labs.frameworks;

import java.util.concurrent.*;
import org.springframework.boot.actuate.health.*;
import org.springframework.context.*;
import org.springframework.context.annotation.*;

@Configuration
public class Lab {
  public static class Gate implements SmartLifecycle {
    private volatile boolean running;
    private ExecutorService executor;

    public synchronized void start() {
      if (!running) {
        executor =
            new ThreadPoolExecutor(
                1,
                1,
                0,
                TimeUnit.MILLISECONDS,
                new ArrayBlockingQueue<>(2),
                r -> new Thread(r, "框架实验任务线程"),
                new ThreadPoolExecutor.AbortPolicy());
        running = true;
      }
    }

    public synchronized <T> Future<T> submit(Callable<T> work) {
      if (!running) throw new RejectedExecutionException("服务已停止接单");
      return executor.submit(work);
    }

    public boolean isRunning() {
      return running;
    }

    public void stop() {
      // 练习区开始
      ExecutorService current;
      synchronized (this) {
        if (!running) return;
        running = false;
        current = executor;
        current.shutdown();
      }
      // 总预算2秒：先给正常完成1.5秒，再为中断后的资源清理预留时间。
      long deadline = System.nanoTime() + TimeUnit.SECONDS.toNanos(2);
      boolean interrupted = false;
      try {
        boolean complete = false;
        try {
          complete = current.awaitTermination(1500, TimeUnit.MILLISECONDS);
        } catch (InterruptedException e) {
          interrupted = true;
        }
        if (!complete) {
          // shutdownNow只移出等待队列，不会替调用方取消那些Future。
          for (Runnable task : current.shutdownNow()) {
            if (task instanceof Future<?> future) future.cancel(false);
          }
          while (!current.isTerminated()) {
            long remaining = deadline - System.nanoTime();
            if (remaining <= 0) throw new IllegalStateException("任务未响应取消，关闭预算已耗尽");
            try {
              if (current.awaitTermination(remaining, TimeUnit.NANOSECONDS)) break;
            } catch (InterruptedException e) {
              // 清理仍受同一总预算约束；退出时再恢复调用线程的中断信号。
              interrupted = true;
            }
          }
        }
      } finally {
        if (interrupted) Thread.currentThread().interrupt();
      }
      // 练习区结束
    }

    public boolean terminated() {
      return executor != null && executor.isTerminated();
    }
  }

  @Bean
  Gate gate() {
    return new Gate();
  }

  @Bean
  HealthIndicator workHealth(Gate gate) {
    return () ->
        (gate.isRunning() ? Health.up() : Health.down())
            .withDetail("accepting", gate.isRunning())
            .build();
  }

  public static void main(String[] args) throws Exception {
    try (var c = new AnnotationConfigApplicationContext(Lab.class)) {
      System.out.println("任务结果：" + c.getBean(Gate.class).submit(() -> 42).get());
    }
  }
}
