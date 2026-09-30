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
      try {
        if (!current.awaitTermination(2, TimeUnit.SECONDS)) current.shutdownNow();
      } catch (InterruptedException e) {
        current.shutdownNow();
        Thread.currentThread().interrupt();
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
