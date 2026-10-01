package labs.frameworks;

import static org.assertj.core.api.Assertions.*;

import org.junit.jupiter.api.*;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;

class LabTest {
  private final ApplicationContextRunner runner =
      new ApplicationContextRunner().withUserConfiguration(Lab.class);

  @Test
  void 默认配置可绑定() {
    runner.run(
        c -> {
          assertThat(c).hasNotFailed();
          assertThat(c.getBean(Lab.Limits.class).getMaxQuantity()).isEqualTo(100);
        });
  }

  @Test
  void 外部配置覆盖默认并限制业务() {
    runner
        .withPropertyValues("orders.max-quantity=3", "orders.display-name=企业订单")
        .run(
            c -> {
              var x = c.getBean(Lab.Limits.class);
              x.requireAllowed(1);
              x.requireAllowed(3);
              assertThat(x.getDisplayName()).isEqualTo("企业订单");
              assertThatThrownBy(() -> x.requireAllowed(4))
                  .isInstanceOf(IllegalArgumentException.class);
              assertThatThrownBy(() -> x.requireAllowed(0))
                  .isInstanceOf(IllegalArgumentException.class);
            });
  }

  @Test
  void 错误配置导致启动失败() {
    runner.withPropertyValues("orders.max-quantity=0").run(c -> assertThat(c).hasFailed());
    runner.withPropertyValues("orders.display-name=").run(c -> assertThat(c).hasFailed());
  }

  @Test
  void 配置文件与命令行的真实优先级() {
    var app = new org.springframework.boot.SpringApplication(Lab.class);
    app.setWebApplicationType(org.springframework.boot.WebApplicationType.NONE);
    app.setDefaultProperties(java.util.Map.of("orders.max-quantity", "2"));
    try (var context = app.run("--spring.profiles.active=lab")) {
      assertThat(context.getBean(Lab.Limits.class).getMaxQuantity()).isEqualTo(5);
    }
    try (var context = app.run("--spring.profiles.active=lab", "--orders.max-quantity=7")) {
      assertThat(context.getBean(Lab.Limits.class).getMaxQuantity()).isEqualTo(7);
    }
  }

  @Test
  void 默认上界也校验() {
    var x = new Lab.Limits();
    assertThatThrownBy(() -> x.requireAllowed(101)).isInstanceOf(IllegalArgumentException.class);
  }
}
