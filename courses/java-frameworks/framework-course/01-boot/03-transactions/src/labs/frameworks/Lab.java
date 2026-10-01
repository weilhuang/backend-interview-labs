package labs.frameworks;

import javax.sql.DataSource;
import org.springframework.context.annotation.*;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.datasource.DataSourceTransactionManager;
import org.springframework.jdbc.datasource.embedded.*;
import org.springframework.transaction.support.TransactionTemplate;

@Configuration
public class Lab {
  @Bean
  DataSource dataSource() {
    return new EmbeddedDatabaseBuilder()
        .generateUniqueName(true)
        .setType(EmbeddedDatabaseType.H2)
        .addScript("schema.sql")
        .build();
  }

  @Bean
  JdbcTemplate jdbc(DataSource ds) {
    return new JdbcTemplate(ds);
  }

  @Bean
  TransactionTemplate transactions(DataSource ds) {
    return new TransactionTemplate(new DataSourceTransactionManager(ds));
  }

  @Bean
  Service service(JdbcTemplate jdbc, TransactionTemplate tx) {
    return new Service(jdbc, tx);
  }

  public static class Service {
    final JdbcTemplate jdbc;
    final TransactionTemplate tx;

    public Service(JdbcTemplate jdbc, TransactionTemplate tx) {
      this.jdbc = jdbc;
      this.tx = tx;
    }

    public void place(String requestId, int quantity, boolean failAfterDebit) {
      // 练习区开始
      if (requestId == null || requestId.isBlank() || quantity < 1)
        throw new IllegalArgumentException("请求编号与数量不合法");
      tx.executeWithoutResult(
          status -> {
            var previous =
                jdbc.queryForList(
                    "select quantity from orders where request_id=?", Integer.class, requestId);
            if (!previous.isEmpty()) {
              if (previous.get(0) != quantity) throw new IllegalArgumentException("同一编号内容冲突");
              return;
            }
            int updated =
                jdbc.update(
                    "update stock set remaining=remaining-? where sku='BOOK' and remaining>=?",
                    quantity,
                    quantity);
            if (updated != 1) throw new IllegalStateException("库存不足");
            if (failAfterDebit) throw new IllegalStateException("模拟扣库存后写入失败");
            jdbc.update("insert into orders(request_id,quantity) values(?,?)", requestId, quantity);
          });
      // 练习区结束
    }

    public int remaining() {
      return jdbc.queryForObject("select remaining from stock where sku='BOOK'", Integer.class);
    }

    public int orders() {
      return jdbc.queryForObject("select count(*) from orders", Integer.class);
    }
  }

  public static void main(String[] args) {
    try (var c = new AnnotationConfigApplicationContext(Lab.class)) {
      var s = c.getBean(Service.class);
      s.place("示例订单", 2, false);
      System.out.println("剩余库存：" + s.remaining() + "，订单数：" + s.orders());
    }
  }
}
