package labs.frameworks;

import static org.assertj.core.api.Assertions.*;

import org.junit.jupiter.api.*;
import org.springframework.beans.factory.BeanCreationException;

class LabTest {
  @Test
  void 允许属性循环时身份一致() {
    var f = Lab.factory(true);
    var a = f.getBean(Lab.A.class);
    assertThat(a.b).isSameAs(f.getBean(Lab.B.class));
    assertThat(a.b.a).isSameAs(a);
    f.destroySingletons();
  }

  @Test
  void 拒绝循环时真实容器失败() {
    assertThatThrownBy(() -> Lab.factory(false).getBean(Lab.A.class))
        .isInstanceOf(BeanCreationException.class);
  }

  @Test
  void 构造循环仍失败() {
    assertThatThrownBy(Lab::constructorCycle).isInstanceOf(BeanCreationException.class);
  }
}
