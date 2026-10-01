package labs.frameworks;

import org.springframework.beans.factory.support.*;

public class Lab {
  public static class A {
    B b;

    public void setB(B b) {
      this.b = b;
    }
  }

  public static class B {
    A a;

    public void setA(A a) {
      this.a = a;
    }
  }

  public static class ConstructorA {
    public ConstructorA(ConstructorB b) {}
  }

  public static class ConstructorB {
    public ConstructorB(ConstructorA a) {}
  }

  public static DefaultListableBeanFactory factory(boolean allow) {
    // 练习区开始
    var f = new DefaultListableBeanFactory();
    f.setAllowCircularReferences(allow);
    var a = new RootBeanDefinition(A.class);
    a.getPropertyValues()
        .add("b", new org.springframework.beans.factory.config.RuntimeBeanReference("b"));
    var b = new RootBeanDefinition(B.class);
    b.getPropertyValues()
        .add("a", new org.springframework.beans.factory.config.RuntimeBeanReference("a"));
    f.registerBeanDefinition("a", a);
    f.registerBeanDefinition("b", b);
    return f;
    // 练习区结束
  }

  public static void constructorCycle() {
    var f = new DefaultListableBeanFactory();
    f.setAllowCircularReferences(true);
    var a = new RootBeanDefinition(ConstructorA.class);
    a.setAutowireMode(AbstractBeanDefinition.AUTOWIRE_CONSTRUCTOR);
    var b = new RootBeanDefinition(ConstructorB.class);
    b.setAutowireMode(AbstractBeanDefinition.AUTOWIRE_CONSTRUCTOR);
    f.registerBeanDefinition("a", a);
    f.registerBeanDefinition("b", b);
    f.getBean("a");
  }

  public static void main(String[] args) {
    var f = factory(true);
    var a = f.getBean(A.class);
    System.out.println("早期引用保持身份：" + (a.b.a == a));
    f.destroySingletons();
  }
}
