package labs.frameworks;

import static org.assertj.core.api.Assertions.*;

import org.junit.jupiter.api.*;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;

class LabTest {
  AnnotationConfigApplicationContext context;
  Lab.Service service;

  @BeforeEach
  void 启动独立数据库() {
    context = new AnnotationConfigApplicationContext(Lab.class);
    service = context.getBean(Lab.Service.class);
  }

  @AfterEach
  void 关闭() {
    context.close();
  }

  @Test
  void 成功同时更新并重试幂等() {
    service.place("一", 3, false);
    service.place("一", 3, false);
    assertThat(service.remaining()).isEqualTo(7);
    assertThat(service.orders()).isEqualTo(1);
  }

  @Test
  void 扣减后失败必须全部回滚() {
    assertThatThrownBy(() -> service.place("失败", 4, true))
        .isInstanceOf(IllegalStateException.class);
    assertThat(service.remaining()).isEqualTo(10);
    assertThat(service.orders()).isZero();
  }

  @Test
  void 库存不足和非法数量不改状态() {
    assertThatThrownBy(() -> service.place("超量", 11, false))
        .isInstanceOf(IllegalStateException.class);
    assertThatThrownBy(() -> service.place("负值", -1, false))
        .isInstanceOf(IllegalArgumentException.class);
    assertThat(service.remaining()).isEqualTo(10);
    assertThat(service.orders()).isZero();
  }

  @Test
  void 同键不同数量拒绝() {
    service.place("一", 2, false);
    assertThatThrownBy(() -> service.place("一", 3, false))
        .isInstanceOf(IllegalArgumentException.class);
    assertThat(service.remaining()).isEqualTo(8);
  }
}
