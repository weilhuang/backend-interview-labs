package labs.frameworks;

import org.springframework.boot.*;
import org.springframework.boot.autoconfigure.*;
import org.springframework.boot.autoconfigure.condition.*;
import org.springframework.boot.autoconfigure.jdbc.DataSourceAutoConfiguration;
import org.springframework.context.annotation.*;
import org.springframework.core.env.Environment;

@SpringBootConfiguration
@EnableAutoConfiguration(exclude = DataSourceAutoConfiguration.class)
public class Lab {
  public interface Greeting {
    String greet(String name);
  }

  @AutoConfiguration
  // 练习区开始
  @ConditionalOnClass(name = "labs.frameworks.Transport")
  @ConditionalOnProperty(
      prefix = "greeting",
      name = "enabled",
      havingValue = "true",
      matchIfMissing = true)
  // 练习区结束
  public static class GreetingAutoConfiguration {
    @Bean
    // 练习区开始
    @ConditionalOnMissingBean(Greeting.class)
    // 练习区结束
    Greeting greeting(Environment environment) {
      // 练习区开始
      String prefix = environment.getProperty("greeting.prefix", "你好");
      return name -> prefix + "，" + name;
      // 练习区结束
    }
  }

  public static void main(String[] args) {
    var app = new SpringApplication(Lab.class);
    app.setWebApplicationType(WebApplicationType.NONE);
    try (var c = app.run(args)) {
      System.out.println(c.getBean(Greeting.class).greet("学习者"));
    }
  }
}
