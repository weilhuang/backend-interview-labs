package labs.frameworks;

import javax.sql.DataSource;
import org.springframework.context.annotation.*;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.datasource.DataSourceTransactionManager;
import org.springframework.jdbc.datasource.embedded.*;
import org.springframework.transaction.*;
import org.springframework.transaction.annotation.*;

@Configuration
@EnableTransactionManagement
public class Lab {
  @Bean
  DataSource ds() {
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
  PlatformTransactionManager transactionManager(DataSource ds) {
    return new DataSourceTransactionManager(ds);
  }

  @Bean
  Inner inner(JdbcTemplate jdbc) {
    return new Inner(jdbc);
  }

  @Bean
  Outer outer(JdbcTemplate jdbc, Inner inner) {
    return new Outer(jdbc, inner);
  }

  public static class Inner {
    final JdbcTemplate jdbc;

    public Inner(JdbcTemplate j) {
      jdbc = j;
    }

    // 练习区开始
    @Transactional(propagation = Propagation.REQUIRED)
    // 练习区结束
    public void required() {
      jdbc.update("insert into events(label) values('内部失败')");
      throw new IllegalStateException("内部失败");
    }

    // 练习区开始
    @Transactional(propagation = Propagation.REQUIRES_NEW)
    // 练习区结束
    public void independent() {
      jdbc.update("insert into events(label) values('独立审计')");
    }
  }

  public static class Outer {
    final JdbcTemplate jdbc;
    final Inner inner;

    public Outer(JdbcTemplate j, Inner i) {
      jdbc = j;
      inner = i;
    }

    // 练习区开始
    @Transactional
    // 练习区结束
    public void catchInner() {
      jdbc.update("insert into events(label) values('外部')");
      try {
        inner.required();
      } catch (IllegalStateException ignored) {
        /* 保留错误场景：捕获异常并不会清除共享事务的仅回滚标记。 */
      }
    }

    // 练习区开始
    @Transactional
    // 练习区结束
    public void failAfterAudit() {
      jdbc.update("insert into events(label) values('外部')");
      inner.independent();
      throw new IllegalStateException("外部失败");
    }

    public static class CheckedFailure extends Exception {}

    @Transactional
    public void checkedDefault() throws CheckedFailure {
      jdbc.update("insert into events(label) values('受检异常默认提交')");
      throw new CheckedFailure();
    }

    @Transactional(rollbackFor = CheckedFailure.class)
    public void checkedRollback() throws CheckedFailure {
      jdbc.update("insert into events(label) values('受检异常显式回滚')");
      throw new CheckedFailure();
    }

    @Transactional
    public boolean childThreadHasTransaction() throws Exception {
      try (var worker = java.util.concurrent.Executors.newSingleThreadExecutor()) {
        return worker
            .submit(
                (java.util.concurrent.Callable<Boolean>)
                    org.springframework.transaction.support.TransactionSynchronizationManager
                        ::isActualTransactionActive)
            .get();
      }
    }

    public void withoutProxy() {
      ownFailure();
    }

    @Transactional
    public void ownFailure() {
      jdbc.update("insert into events(label) values('自调用写入')");
      throw new IllegalStateException("自调用失败");
    }
  }

  public static void main(String[] args) {
    try (var c = new AnnotationConfigApplicationContext(Lab.class)) {
      try {
        c.getBean(Outer.class).failAfterAudit();
      } catch (IllegalStateException ignored) {
      }
      System.out.println(
          "外层回滚后保留："
              + c.getBean(JdbcTemplate.class)
                  .queryForList("select label from events", String.class));
    }
  }
}
