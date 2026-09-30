package labs.distributed.support;

import com.github.dockerjava.api.model.ExposedPort;
import java.io.IOException;
import java.net.URI;
import java.net.URISyntaxException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.sql.SQLException;
import java.util.Properties;
import org.testcontainers.containers.MySQLContainer;
import org.testcontainers.utility.DockerImageName;

/** 镜像版本只从仓库共享台账或发行包随附快照读取。 */
public final class Images {
  private Images() {}

  public static String get(String key) {
    Path path = Path.of(System.getProperty("lab.versions", "../../infra/versions.env"));
    Properties properties = new Properties();
    try (var input = Files.newInputStream(path)) {
      properties.load(input);
    } catch (IOException failure) {
      throw new IllegalStateException("不能读取共享镜像台账：" + path, failure);
    }
    String value = properties.getProperty(key);
    if (value == null || value.isBlank() || value.endsWith(":latest")) {
      throw new IllegalStateException("共享台账缺少固定镜像：" + key);
    }
    return value;
  }

  public static MySQLContainer<?> mysql() {
    return new MySQLContainer<>(DockerImageName.parse(get("MYSQL_IMAGE")))
        .withDatabaseName("distributed_lab")
        .withUsername("lab")
        .withPassword("lab_only_password");
  }

  /** 每次主动 inspect 当前绑定；Testcontainers 启动时的 inspect 缓存不保证跨重启有效。 */
  public static Database database(MySQLContainer<?> container) throws SQLException {
    try {
      var current =
          container.getDockerClient().inspectContainerCmd(container.getContainerId()).exec();
      var bindings =
          current.getNetworkSettings().getPorts().getBindings().get(ExposedPort.tcp(3306));
      if (bindings == null || bindings.length == 0) {
        throw new SQLException("MySQL端口尚未重新发布");
      }
      int port = Integer.parseInt(bindings[0].getHostPortSpec());
      String url = withMappedPort(container.getJdbcUrl(), port);
      return new Database(url, container.getUsername(), container.getPassword());
    } catch (RuntimeException failure) {
      throw new SQLException("无法读取MySQL容器当前端口绑定", failure);
    }
  }

  /** 只替换当前映射端口，保留数据库名、IPv6主机和驱动查询参数。 */
  public static String withMappedPort(String jdbcUrl, int port) {
    if (jdbcUrl == null || !jdbcUrl.startsWith("jdbc:mysql://") || port < 1 || port > 65535) {
      throw new IllegalArgumentException("MySQL JDBC地址或映射端口非法");
    }
    URI original = URI.create(jdbcUrl.substring("jdbc:".length()));
    try {
      URI current =
          new URI(
              original.getScheme(),
              original.getUserInfo(),
              original.getHost(),
              port,
              original.getPath(),
              original.getQuery(),
              original.getFragment());
      return "jdbc:" + current.toASCIIString();
    } catch (URISyntaxException failure) {
      throw new IllegalArgumentException("不能重建MySQL JDBC地址", failure);
    }
  }

  /** 重启保留数据层；返回新端点，调用方必须显式重建Store/XA对象，普通连接池不会自动发现。 */
  public static Database restartAndAwait(MySQLContainer<?> container) throws Exception {
    container.getDockerClient().restartContainerCmd(container.getContainerId()).exec();
    long end = System.nanoTime() + java.time.Duration.ofSeconds(90).toNanos();
    SQLException last = null;
    while (System.nanoTime() < end) {
      try {
        Database current = database(container);
        if (current.scalar("SELECT 1") == 1) return current;
      } catch (SQLException unavailable) {
        last = unavailable;
      }
      Thread.sleep(100);
    }
    throw new IllegalStateException("MySQL重启后未在预算内恢复查询", last);
  }
}
