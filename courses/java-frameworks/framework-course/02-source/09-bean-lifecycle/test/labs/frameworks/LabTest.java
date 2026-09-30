package labs.frameworks;

import static org.assertj.core.api.Assertions.*;

import org.junit.jupiter.api.*;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;

class LabTest {
  @Test
  void 真实容器驱动完整生命周期() {
    var c = new AnnotationConfigApplicationContext(Lab.class);
    var a = c.getBean(Lab.Account.class);
    assertThat(a.label).isEqualTo("企业订单");
    assertThat(a.events()).containsExactly("构造", "属性", "初始化前", "初始化", "初始化后");
    c.close();
    assertThat(a.events()).containsExactly("构造", "属性", "初始化前", "初始化", "初始化后", "销毁");
    c.close();
    assertThat(a.events().stream().filter("销毁"::equals).count()).isEqualTo(1);
  }

  @Test
  void 每个上下文状态独立() {
    try (var a = new AnnotationConfigApplicationContext(Lab.class);
        var b = new AnnotationConfigApplicationContext(Lab.class)) {
      assertThat(a.getBean(Lab.Account.class)).isNotSameAs(b.getBean(Lab.Account.class));
    }
  }
}
