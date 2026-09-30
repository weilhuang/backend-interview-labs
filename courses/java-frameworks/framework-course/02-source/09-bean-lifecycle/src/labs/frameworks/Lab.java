package labs.frameworks;

import java.util.*;
import org.springframework.beans.factory.*;
import org.springframework.beans.factory.config.*;
import org.springframework.context.annotation.*;

@Configuration
public class Lab {
  public static class Account implements InitializingBean, DisposableBean {
    final List<String> events = new ArrayList<>();
    String label;

    public Account() {
      events.add("构造");
    }

    public void setLabel(String s) {
      label = s;
      events.add("属性");
    }

    public void afterPropertiesSet() {
      events.add("初始化");
    }

    public void destroy() {
      events.add("销毁");
    }

    public List<String> events() {
      return List.copyOf(events);
    }
  }

  @Bean
  Account account() {
    return new Account();
  }

  @Bean
  static BeanFactoryPostProcessor definition() {
    // 练习区开始
    return factory -> factory.getBeanDefinition("account").getPropertyValues().add("label", "企业订单");
    // 练习区结束
  }

  @Bean
  static BeanPostProcessor instance() {
    // 练习区开始
    return new BeanPostProcessor() {
      public Object postProcessBeforeInitialization(Object bean, String name) {
        if (bean instanceof Account a) a.events.add("初始化前");
        return bean;
      }

      public Object postProcessAfterInitialization(Object bean, String name) {
        if (bean instanceof Account a) a.events.add("初始化后");
        return bean;
      }
    };
    // 练习区结束
  }

  public static void main(String[] args) {
    Account a;
    try (var c = new AnnotationConfigApplicationContext(Lab.class)) {
      a = c.getBean(Account.class);
      System.out.println("配置名称：" + a.label);
    }
    System.out.println(a.events());
  }
}
