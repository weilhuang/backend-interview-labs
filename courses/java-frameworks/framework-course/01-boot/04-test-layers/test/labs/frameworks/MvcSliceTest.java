package labs.frameworks;

import static org.mockito.Mockito.*;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.*;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

import org.junit.jupiter.api.*;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.context.annotation.Import;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.test.web.servlet.MockMvc;

@WebMvcTest(Lab.Api.class)
@Import(Lab.Errors.class)
class MvcSliceTest {
  @Autowired MockMvc mvc;
  @MockitoBean Lab.Quotes quotes;

  @Test
  void 切片检查映射与参数() throws Exception {
    when(quotes.total(2)).thenReturn(300L);
    mvc.perform(get("/quote").param("quantity", "2"))
        .andExpect(status().isOk())
        .andExpect(content().string("300"));
    verify(quotes).total(2);
  }

  @Test
  void 切片检查失败映射() throws Exception {
    when(quotes.total(2)).thenThrow(new IllegalStateException());
    mvc.perform(get("/quote").param("quantity", "2")).andExpect(status().isServiceUnavailable());
    mvc.perform(get("/quote").param("quantity", "坏参数")).andExpect(status().isBadRequest());
  }
}
