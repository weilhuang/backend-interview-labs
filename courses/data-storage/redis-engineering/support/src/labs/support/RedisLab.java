package labs.support;

import com.github.dockerjava.api.model.ExposedPort;
import java.time.Duration;
import java.util.UUID;
import java.util.function.BooleanSupplier;
import java.util.function.LongSupplier;
import java.util.function.Supplier;
import java.util.concurrent.TimeUnit;
import org.testcontainers.DockerClientFactory;
import org.testcontainers.containers.GenericContainer;
import org.testcontainers.containers.Network;
import org.testcontainers.utility.DockerImageName;
import redis.clients.jedis.Jedis;
import redis.clients.jedis.exceptions.JedisConnectionException;

/** 仅操作本对象创建的临时容器；不用宿主机Redis，不执行全库清空。 */
public final class RedisLab implements AutoCloseable {
  public final GenericContainer<?> container;
  private volatile int mappedPort;
  private final String prefix = "c07:" + UUID.randomUUID() + ":";

  public RedisLab(String... options) {
    this(null, null, options);
  }

  public RedisLab(Network network, String alias, String... options) {
    container =
        new GenericContainer<>(DockerImageName.parse(Images.get("REDIS_IMAGE")))
            .withExposedPorts(6379)
            .withStartupTimeout(Duration.ofSeconds(60));
    String[] command = new String[options.length + 1];
    command[0] = "redis-server";
    System.arraycopy(options, 0, command, 1, options.length);
    container.withCommand(command);
    if (network != null) container.withNetwork(network).withNetworkAliases(alias);
  }

  public RedisLab start() {
    container.start();
    mappedPort = container.getMappedPort(6379);
    return this;
  }

  public String key(String name) {
    return prefix + name;
  }

  /** 当前宿主端口；重启后由夹具inspect刷新，可能与初次启动不同。 */
  public int port() { return mappedPort; }

  public Jedis connect() {
    return new Jedis(container.getHost(), mappedPort, 500, 500);
  }

  /**
   * 仅用于故障后仍存活节点的夹具准备；成功返回已完成握手和PING的同一连接。
   * 15秒控制重试预算，单次连接/读取仍各限500ms；不重试调用方的任何业务命令。
   * 到期不再发起尝试；已经在途的连接/读取按原有socket超时结束，不声称严格15秒抢占。
   */
  public Jedis connectReady(String phase) {
    return connectReady(
        phase, this::connect, Duration.ofSeconds(15), System::nanoTime,
        nanos -> TimeUnit.NANOSECONDS.sleep(nanos));
  }

  @FunctionalInterface
  interface Sleeper {
    void sleep(long nanos) throws InterruptedException;
  }

  /** 包内测试缝：模拟时钟与连接，不启动Docker、不访问网络。 */
  static Jedis connectReady(
      String phase, Supplier<Jedis> connections, Duration budget,
      LongSupplier nanoTime, Sleeper sleeper) {
    if (budget.isZero() || budget.isNegative())
      throw new IllegalArgumentException("夹具就绪预算必须为正数");
    long started = nanoTime.getAsLong();
    long budgetNanos = budget.toNanos();
    int attempts = 0;
    JedisConnectionException lastFailure = null;
    while (nanoTime.getAsLong() - started < budgetNanos) {
      if (Thread.currentThread().isInterrupted())
        throw new FixtureReadinessException(phase + "：等待被取消", new InterruptedException());
      attempts++;
      Jedis connection = null;
      boolean ready = false;
      Throwable attemptFailure = null;
      try {
        connection = connections.get(); // Jedis构造握手失败也在此边界内。
        if (!"PONG".equals(connection.ping()))
          throw new FixtureReadinessException(phase + "：PING未返回PONG", null);
        // 返回同一连接；不先探活关闭再建立另一连接。
        if (nanoTime.getAsLong() - started < budgetNanos) {
          ready = true;
          return connection;
        }
        lastFailure = new JedisConnectionException("握手/PING返回时就绪预算已用尽");
        attemptFailure = lastFailure;
      } catch (JedisConnectionException unavailable) {
        lastFailure = unavailable; // 只重试连接异常，不吞业务异常、断言或其他运行时错误。
        attemptFailure = unavailable;
      } catch (RuntimeException | Error unexpected) {
        attemptFailure = unexpected;
        throw unexpected;
      } finally {
        if (!ready && connection != null) {
          try {
            connection.close();
          } catch (RuntimeException cleanupFailure) {
            var failure = new FixtureReadinessException(phase + "：失败连接关闭异常", cleanupFailure);
            if (attemptFailure != null) failure.addSuppressed(attemptFailure);
            throw failure; // 清理失败不被下次尝试或后续学生TODO掩盖。
          }
        }
      }
      long remaining = budgetNanos - (nanoTime.getAsLong() - started);
      if (remaining <= 0) break;
      try {
        sleeper.sleep(Math.min(TimeUnit.MILLISECONDS.toNanos(100), remaining));
      } catch (InterruptedException interrupted) {
        Thread.currentThread().interrupt();
        throw new FixtureReadinessException(phase + "：等待被取消", interrupted);
      }
    }
    throw new FixtureReadinessException(
        phase + "：Redis夹具连接/PING就绪超时，尝试次数=" + attempts
            + "，重试预算=" + budget.toMillis() + "ms（在途连接/读取每次各有500ms超时）",
        lastFailure);
  }

  /** 基础设施失败，不能充当学生答案被拒绝的证据。 */
  public static final class FixtureReadinessException extends IllegalStateException {
    FixtureReadinessException(String message, Throwable cause) {
      super(message, cause);
    }
  }

  public void crash() {
    DockerClientFactory.instance()
        .client()
        .killContainerCmd(container.getContainerId())
        .withSignal("SIGKILL")
        .exec();
  }

  public void restart() {
    DockerClientFactory.instance().client().startContainerCmd(container.getContainerId()).exec();
    await(
        "Redis重启就绪",
        () -> {
          try {
            // Docker 再次 start 同一容器时随机发布端口可能变化，不能继续用 GenericContainer 的旧快照。
            var state = DockerClientFactory.instance().client()
                .inspectContainerCmd(container.getContainerId()).exec();
            var bindings = state.getNetworkSettings().getPorts().getBindings().get(ExposedPort.tcp(6379));
            if (bindings == null || bindings.length == 0) return false;
            mappedPort = Integer.parseInt(bindings[0].getHostPortSpec());
            try (Jedis j = connect()) {
              return "PONG".equals(j.ping());
            }
          } catch (RuntimeException e) {
            return false;
          }
        });
  }

  public static void await(String description, BooleanSupplier condition) {
    long end = System.nanoTime() + Duration.ofSeconds(15).toNanos();
    do {
      if (condition.getAsBoolean()) return;
      try {
        Thread.sleep(25);
      } catch (InterruptedException e) {
        Thread.currentThread().interrupt();
        throw new IllegalStateException("等待被取消", e);
      }
    } while (System.nanoTime() < end);
    throw new IllegalStateException("等待超时：" + description);
  }

  @Override
  public void close() {
    container.close();
  }
}
