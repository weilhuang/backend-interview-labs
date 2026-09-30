package labs.frameworks;

import static org.assertj.core.api.Assertions.*;

import java.nio.file.*;
import java.util.Properties;
import org.junit.jupiter.api.*;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.datasource.*;
import org.springframework.transaction.support.TransactionTemplate;
import org.testcontainers.containers.MySQLContainer;
import org.testcontainers.junit.jupiter.*;

@Tag("docker")
@Testcontainers
class MySqlContractTest {
  static String image() {
    String path = System.getenv("LAB_SHARED_VERSIONS");
    if (path == null)
      throw new IllegalStateException("请设置LAB_SHARED_VERSIONS为仓库infra/versions.env，不能复制镜像版本");
    try (var in = Files.newInputStream(Path.of(path))) {
      var p = new Properties();
      p.load(in);
      String image = p.getProperty("MYSQL_IMAGE");
      if (image == null || image.isBlank()) throw new IllegalStateException("共享镜像台账缺少MYSQL_IMAGE");
      return image;
    } catch (java.io.IOException e) {
      throw new IllegalStateException("无法读取共享镜像台账", e);
    }
  }

  @Container static final MySQLContainer<?> mysql = new MySQLContainer<>(image());

  @Test
  void 真实MySQL回滚合同() {
    var ds =
        new DriverManagerDataSource(mysql.getJdbcUrl(), mysql.getUsername(), mysql.getPassword());
    var jdbc = new JdbcTemplate(ds);
    jdbc.execute("create table stock(sku varchar(64) primary key,remaining integer not null)");
    jdbc.execute(
        "create table orders(request_id varchar(128) primary key,quantity integer not null)");
    jdbc.update("insert into stock values('BOOK',10)");
    var s = new Lab.Service(jdbc, new TransactionTemplate(new DataSourceTransactionManager(ds)));
    assertThatThrownBy(() -> s.place("失败", 3, true)).isInstanceOf(IllegalStateException.class);
    assertThat(s.remaining()).isEqualTo(10);
    s.place("成功", 2, false);
    assertThat(s.remaining()).isEqualTo(8);
  }
}
