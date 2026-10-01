package labs.support;

import com.github.dockerjava.api.model.ExposedPort;
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
