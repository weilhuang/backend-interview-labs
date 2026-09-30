package labs.frameworks;

import static org.assertj.core.api.Assertions.*;

import java.util.*;
import org.junit.jupiter.api.*;
import org.springframework.aop.support.AopUtils;

class LabTest {
  @Test
  void 两类真实代理都校验并透传() {
    for (boolean mode : List.of(false, true)) {
      var events = new ArrayList<String>();
      var p = Lab.proxy(mode, events);
      assertThat(AopUtils.isAopProxy(p)).isTrue();
      assertThat(p.charge(5)).isEqualTo(5);
      assertThat(events).containsExactly("进入:charge", "退出:charge");
      assertThatThrownBy(() -> p.charge(0)).isInstanceOf(IllegalArgumentException.class);
    }
  }

  @Test
  void 原异常不吞且退出仍记录() {
    var events = new ArrayList<String>();
    var p = Lab.proxy(false, events);
    assertThatThrownBy(() -> p.charge(13))
        .isInstanceOf(IllegalStateException.class)
        .hasMessage("模拟支付失败");
    assertThat(events).containsExactly("进入:charge", "退出:charge");
  }

  @Test
  void 自调用明确绕过内部方法拦截() {
    var events = new ArrayList<String>();
    assertThat(Lab.proxy(false, events).batch(-5)).isEqualTo(-5);
    assertThat(events).containsExactly("进入:batch", "退出:batch");
  }
}
