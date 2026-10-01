package labs.frameworks;

import java.util.*;
import org.springframework.context.annotation.*;

@Configuration
public class Lab {
  public static class Clock {
    public Clock() {}

    public String now() {
      return "示例时刻";
    }
  }

  public static class Orders {
    final Clock clock;

    public Orders(Clock c) {
      clock = c;
    }

    public String describe() {
      return "订单创建于" + clock.now();
    }
  }

  @Bean
  Clock clock() {
    return new Clock();
  }

  @Bean
  Orders orders(Clock c) {
    return new Orders(c);
  }

  public static class Tiny {
    final Map<Class<?>, Object> cache = new HashMap<>();
    final Set<Class<?>> constructing = new HashSet<>();

    public synchronized <T> T get(Class<T> type) {
      // 练习区开始
      if (cache.containsKey(type)) return type.cast(cache.get(type));
      if (!constructing.add(type)) throw new IllegalStateException("检测到构造循环：" + type.getName());
      try {
        var constructors = type.getConstructors();
        if (constructors.length != 1) throw new IllegalArgumentException("教学容器只支持一个公开构造器");
        var constructor = constructors[0];
        Object[] args = Arrays.stream(constructor.getParameterTypes()).map(this::get).toArray();
        T result = type.cast(constructor.newInstance(args));
        cache.put(type, result);
        return result;
      } catch (ReflectiveOperationException e) {
        throw new IllegalStateException("构造失败", e);
      } finally {
        constructing.remove(type);
      }
      // 练习区结束
    }
  }

  public static void main(String[] args) {
    try (var c = new AnnotationConfigApplicationContext(Lab.class)) {
      System.out.println(c.getBean(Orders.class).describe());
    }
  }
}
