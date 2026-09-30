package labs.distributed.support;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
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

  public static Database database(MySQLContainer<?> container) {
    return new Database(container.getJdbcUrl(), container.getUsername(), container.getPassword());
  }

  /** 重启同一个隔离容器，保留数据层；用真实查询确认恢复，不以固定睡眠当就绪。 */
  public static void restartAndAwait(MySQLContainer<?> container) throws Exception {
    container.getDockerClient().restartContainerCmd(container.getContainerId()).exec();
    Database database = database(container);
    long end = System.nanoTime() + java.time.Duration.ofSeconds(90).toNanos();
    Exception last = null;
    while (System.nanoTime() < end) {
      try {
        if (database.scalar("SELECT 1") == 1) return;
      } catch (java.sql.SQLException unavailable) {
        last = unavailable;
      }
      Thread.sleep(100);
    }
    throw new IllegalStateException("MySQL重启后未在预算内恢复查询", last);
  }
}
