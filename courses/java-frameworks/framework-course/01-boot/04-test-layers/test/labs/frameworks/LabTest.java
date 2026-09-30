package labs.frameworks;

import static org.assertj.core.api.Assertions.*;
import static org.mockito.Mockito.*;

import org.junit.jupiter.api.*;

class LabTest {
  @Test
  void 单元测试隔离价格端口() {
    Lab.Prices p = mock(Lab.Prices.class);
    when(p.unitPrice()).thenReturn(150L);
    assertThat(new Lab.Quotes(p).total(2)).isEqualTo(300);
    verify(p, times(1)).unitPrice();
  }

  @Test
  void 非法请求不触碰下游() {
    Lab.Prices p = mock(Lab.Prices.class);
    assertThatThrownBy(() -> new Lab.Quotes(p).total(0))
        .isInstanceOf(IllegalArgumentException.class);
    verifyNoInteractions(p);
  }

  @Test
  void 边界与异常() {
    assertThatThrownBy(() -> new Lab.Quotes(() -> 0).total(2))
        .isInstanceOf(IllegalStateException.class);
    assertThatThrownBy(() -> new Lab.Quotes(() -> Long.MAX_VALUE).total(2))
        .isInstanceOf(ArithmeticException.class);
    assertThat(new Lab.Quotes(() -> 1).total(100)).isEqualTo(100);
    assertThatThrownBy(() -> new Lab.Quotes(() -> 1).total(101))
        .isInstanceOf(IllegalArgumentException.class);
  }
}
