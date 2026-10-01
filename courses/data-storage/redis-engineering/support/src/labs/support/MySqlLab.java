package labs.support;

import java.sql.Connection;
import java.sql.DriverManager;
import java.sql.SQLException;
import org.testcontainers.containers.MySQLContainer;
import org.testcontainers.utility.DockerImageName;

/** 只创建一次性实验库；凭据为隔离容器的公开fixture。 */
public final class MySqlLab implements AutoCloseable {
  public final MySQLContainer<?> container =
      new MySQLContainer<>(DockerImageName.parse(Images.get("MYSQL_IMAGE")))
          .withDatabaseName("c07_lab")
          .withUsername("c07")
          .withPassword("c07_fixture");

  public MySqlLab start() {
    container.start();
    return this;
  }

  public Connection connect() throws SQLException {
    return DriverManager.getConnection(
        container.getJdbcUrl()
            + (container.getJdbcUrl().contains("?") ? "&" : "?")
            + "connectTimeout=1000&socketTimeout=3000",
        container.getUsername(),
        container.getPassword());
  }

  @Override
  public void close() {
    container.close();
  }
}
