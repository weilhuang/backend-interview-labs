package labs.frameworks;

import static org.assertj.core.api.Assertions.*;

import org.junit.jupiter.api.*;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.transaction.UnexpectedRollbackException;

class LabTest {
  AnnotationConfigApplicationContext c;
  JdbcTemplate jdbc;
  Lab.Outer outer;

  @BeforeEach
  void 准备() {
    c = new AnnotationConfigApplicationContext(Lab.class);
    jdbc = c.getBean(JdbcTemplate.class);
    outer = c.getBean(Lab.Outer.class);
  }

  @AfterEach
  void 清理() {
    c.close();
  }

  @Test
  void 捕获内部异常仍不可提交共享事务() {
    assertThatThrownBy(outer::catchInner).isInstanceOf(UnexpectedRollbackException.class);
    assertThat(jdbc.queryForObject("select count(*) from events", Integer.class)).isZero();
  }

  @Test
  void 独立事务保留而外层回滚() {
    assertThatThrownBy(outer::failAfterAudit).isInstanceOf(IllegalStateException.class);
    assertThat(jdbc.queryForList("select label from events", String.class)).containsExactly("独立审计");
  }

  @Test
  void 直接过代理回滚() {
    assertThatThrownBy(outer::ownFailure).isInstanceOf(IllegalStateException.class);
    assertThat(jdbc.queryForObject("select count(*) from events", Integer.class)).isZero();
  }

  @Test
  void 受检异常规则必须明确() {
    assertThatThrownBy(outer::checkedDefault).isInstanceOf(Lab.Outer.CheckedFailure.class);
    assertThat(jdbc.queryForObject("select count(*) from events", Integer.class)).isEqualTo(1);
    assertThatThrownBy(outer::checkedRollback).isInstanceOf(Lab.Outer.CheckedFailure.class);
    assertThat(jdbc.queryForObject("select count(*) from events", Integer.class)).isEqualTo(1);
  }

  @Test
  void 新线程不自动继承事务() throws Exception {
    assertThat(outer.childThreadHasTransaction()).isFalse();
  }

  @Test
  void 自调用反例没有事务() {
    assertThatThrownBy(outer::withoutProxy).isInstanceOf(IllegalStateException.class);
    assertThat(jdbc.queryForList("select label from events", String.class))
        .containsExactly("自调用写入");
  }
}
