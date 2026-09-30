package labs.support;

import java.time.Duration;
import java.util.UUID;
import java.util.function.BooleanSupplier;
import org.testcontainers.DockerClientFactory;
import org.testcontainers.containers.GenericContainer;
import org.testcontainers.containers.Network;
import org.testcontainers.utility.DockerImageName;
import redis.clients.jedis.Jedis;

/** 仅操作本对象创建的临时容器；不用宿主机Redis，不执行全库清空。 */
public final class RedisLab implements AutoCloseable {
  public final GenericContainer<?> container;
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
    return this;
  }

  public String key(String name) {
    return prefix + name;
  }

  public Jedis connect() {
    return new Jedis(container.getHost(), container.getMappedPort(6379), 500, 500);
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
          try (Jedis j = connect()) {
            return "PONG".equals(j.ping());
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
