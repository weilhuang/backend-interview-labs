package labs.frameworks;

import static org.assertj.core.api.Assertions.*;

import org.junit.jupiter.api.*;
import org.springframework.boot.autoconfigure.AutoConfigurations;
import org.springframework.boot.autoconfigure.condition.ConditionEvaluationReport;
import org.springframework.boot.test.context.FilteredClassLoader;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.context.annotation.*;

class LabTest {
  final ApplicationContextRunner runner =
      new ApplicationContextRunner()
          .withConfiguration(AutoConfigurations.of(Lab.GreetingAutoConfiguration.class));

  @Configuration
  static class UserConfig {
    @Bean
    Lab.Greeting custom() {
      return name -> "用户实现:" + name;
    }
  }

  @Test
  void 默认启用且配置可覆盖() {
    runner.run(
        c -> {
          assertThat(c).hasSingleBean(Lab.Greeting.class);
          assertThat(c.getBean(Lab.Greeting.class).greet("甲")).isEqualTo("你好，甲");
          assertThat(
                  ConditionEvaluationReport.get(c.getBeanFactory())
                      .getConditionAndOutcomesBySource())
              .isNotEmpty();
        });
    runner
        .withPropertyValues("greeting.prefix=欢迎")
        .run(c -> assertThat(c.getBean(Lab.Greeting.class).greet("甲")).isEqualTo("欢迎，甲"));
  }

  @Test
  void 关闭时不装配() {
    runner
        .withPropertyValues("greeting.enabled=false")
        .run(c -> assertThat(c).doesNotHaveBean(Lab.Greeting.class));
  }

  @Test
  void 用户Bean优先() {
    runner
        .withUserConfiguration(UserConfig.class)
        .run(
            c -> {
              assertThat(c).hasSingleBean(Lab.Greeting.class);
              assertThat(c.getBean(Lab.Greeting.class).greet("甲")).isEqualTo("用户实现:甲");
            });
  }

  @Test
  void 缺依赖时退让() {
    runner
        .withClassLoader(new FilteredClassLoader(Transport.class))
        .run(c -> assertThat(c).doesNotHaveBean(Lab.Greeting.class));
  }
}
