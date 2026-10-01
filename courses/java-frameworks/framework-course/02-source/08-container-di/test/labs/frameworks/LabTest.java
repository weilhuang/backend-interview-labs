package labs.frameworks;

import static org.assertj.core.api.Assertions.*;

import org.junit.jupiter.api.*;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;

class LabTest {
  public static class A {
    public A(B b) {}
  }

  public static class B {
    public B(A a) {}
  }

  public static class Bad {
    public Bad() {
      throw new IllegalStateException("模拟构造失败");
    }
  }

  @Test
  void 教学单例与依赖共享() {
    var tiny = new Lab.Tiny();
    var orders = tiny.get(Lab.Orders.class);
    assertThat(orders).isSameAs(tiny.get(Lab.Orders.class));
    assertThat(orders.clock).isSameAs(tiny.get(Lab.Clock.class));
  }

  @Test
  void 循环明确失败而不是栈溢出() {
    assertThatThrownBy(() -> new Lab.Tiny().get(A.class))
        .isInstanceOf(IllegalStateException.class)
        .hasMessageContaining("循环");
  }

  @Test
  void 构造失败清理标记() {
    var t = new Lab.Tiny();
    assertThatThrownBy(() -> t.get(Bad.class)).hasMessageContaining("构造失败");
    assertThatThrownBy(() -> t.get(Bad.class))
        .hasMessageContaining("构造失败")
        .hasMessageNotContaining("循环");
  }

  @org.springframework.context.annotation.Configuration
  static class Choices {
    @org.springframework.context.annotation.Bean
    Lab.Clock first() {
      return new Lab.Clock();
    }

    @org.springframework.context.annotation.Bean
    @org.springframework.context.annotation.Primary
    Lab.Clock preferred() {
      return new Lab.Clock();
    }

    @org.springframework.context.annotation.Bean
    Lab.Orders orders(Lab.Clock c) {
      return new Lab.Orders(c);
    }
  }

  @Test
  void 多候选使用显式优先级() {
    try (var c = new AnnotationConfigApplicationContext(Choices.class)) {
      assertThat(c.getBean(Lab.Orders.class).clock).isSameAs(c.getBean("preferred"));
    }
  }

  @Test
  void 真实Spring同样完成构造注入() {
    try (var c = new AnnotationConfigApplicationContext(Lab.class)) {
      assertThat(c.getBean(Lab.Orders.class).clock).isSameAs(c.getBean(Lab.Clock.class));
    }
  }
}
