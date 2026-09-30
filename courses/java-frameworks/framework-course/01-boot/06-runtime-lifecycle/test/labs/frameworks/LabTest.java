package labs.frameworks;

import static org.assertj.core.api.Assertions.*;

import java.util.concurrent.*;
import org.junit.jupiter.api.*;
import org.springframework.boot.actuate.health.*;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;

class LabTest {
  @Test
  void Spring启动与关闭资源() throws Exception {
    var c = new AnnotationConfigApplicationContext(Lab.class);
    var gate = c.getBean(Lab.Gate.class);
    assertThat(gate.isRunning()).isTrue();
    assertThat(c.getBean(HealthIndicator.class).health().getStatus()).isEqualTo(Status.UP);
    assertThat(gate.submit(() -> 42).get(2, TimeUnit.SECONDS)).isEqualTo(42);
    c.close();
    assertThat(gate.isRunning()).isFalse();
    assertThat(gate.terminated()).isTrue();
    assertThatThrownBy(() -> gate.submit(() -> 1)).isInstanceOf(RejectedExecutionException.class);
  }

  @Test
  void 已接收任务有机会完成() throws Exception {
    var gate = new Lab.Gate();
    gate.start();
    var started = new CountDownLatch(1);
    var release = new CountDownLatch(1);
    var result =
        gate.submit(
            () -> {
              started.countDown();
              release.await();
              return 7;
            });
    assertThat(started.await(2, TimeUnit.SECONDS)).isTrue();
    try (var closer = Executors.newSingleThreadExecutor()) {
      var stopped = closer.submit((Runnable) gate::stop);
      release.countDown();
      stopped.get(3, TimeUnit.SECONDS);
    }
    assertThat(result.get()).isEqualTo(7);
    assertThat(gate.terminated()).isTrue();
  }

  @Test
  void 队列饱和明确拒绝() throws Exception {
    var gate = new Lab.Gate();
    gate.start();
    var entered = new CountDownLatch(1);
    var release = new CountDownLatch(1);
    try {
      gate.submit(
          () -> {
            entered.countDown();
            release.await();
            return 1;
          });
      assertThat(entered.await(2, TimeUnit.SECONDS)).isTrue();
      gate.submit(() -> 2);
      gate.submit(() -> 3);
      assertThatThrownBy(() -> gate.submit(() -> 4)).isInstanceOf(RejectedExecutionException.class);
    } finally {
      release.countDown();
      gate.stop();
    }
    assertThat(gate.terminated()).isTrue();
  }

  @Test
  void 重复停止幂等() {
    var gate = new Lab.Gate();
    gate.start();
    gate.stop();
    gate.stop();
    assertThat(gate.isRunning()).isFalse();
  }
}
