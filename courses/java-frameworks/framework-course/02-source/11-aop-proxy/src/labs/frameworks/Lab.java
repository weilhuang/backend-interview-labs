package labs.frameworks;

import java.util.*;
import org.aopalliance.intercept.MethodInterceptor;
import org.springframework.aop.framework.ProxyFactory;

public class Lab {
  public interface Payments {
    int charge(int amount);

    int batch(int amount);
  }

  public static class PaymentService implements Payments {
    public int charge(int amount) {
      if (amount == 13) throw new IllegalStateException("模拟支付失败");
      return amount;
    }

    public int batch(int amount) {
      return charge(amount);
    }
  }

  public static Payments proxy(boolean classProxy, List<String> events) {
    // 练习区开始
    ProxyFactory factory = new ProxyFactory(new PaymentService());
    factory.setProxyTargetClass(classProxy);
    factory.addAdvice(
        (MethodInterceptor)
            invocation -> {
              if (invocation.getMethod().getName().equals("charge")
                  && (int) invocation.getArguments()[0] < 1)
                throw new IllegalArgumentException("金额必须为正");
              events.add("进入:" + invocation.getMethod().getName());
              try {
                return invocation.proceed();
              } finally {
                events.add("退出:" + invocation.getMethod().getName());
              }
            });
    return (Payments) factory.getProxy();
    // 练习区结束
  }

  public static void main(String[] args) {
    var events = new ArrayList<String>();
    System.out.println("代理结果：" + proxy(false, events).charge(5));
    System.out.println(events);
  }
}
