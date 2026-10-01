package labs.frameworks;

import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.*;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.*;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

import org.junit.jupiter.api.*;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

@SpringBootTest(classes = Lab.class)
@AutoConfigureMockMvc
class LabTest {
  @Autowired MockMvc mvc;

  @Test
  void 实验口令也经真实认证过滤器() throws Exception {
    mvc.perform(get("/orders").with(httpBasic("reader", "lab-only"))).andExpect(status().isOk());
    mvc.perform(get("/orders").with(httpBasic("reader", "wrong")))
        .andExpect(status().isUnauthorized());
  }

  @Test
  void 公开接口与未登录() throws Exception {
    mvc.perform(get("/public/ping")).andExpect(status().isOk());
    mvc.perform(get("/orders")).andExpect(status().isUnauthorized());
  }

  @Test
  void 阅读者不能写() throws Exception {
    mvc.perform(get("/orders").with(user("reader").roles("READER"))).andExpect(status().isOk());
    mvc.perform(post("/orders").with(user("reader").roles("READER")).with(csrf()))
        .andExpect(status().isForbidden());
  }

  @Test
  void 管理员仍需要CSRF() throws Exception {
    mvc.perform(post("/orders").with(user("admin").roles("ADMIN")))
        .andExpect(status().isForbidden());
    mvc.perform(post("/orders").with(user("admin").roles("ADMIN")).with(csrf()))
        .andExpect(status().isCreated());
  }

  @Test
  void CORS不反射任意来源() throws Exception {
    mvc.perform(
            options("/orders")
                .header("Origin", "http://127.0.0.1:18084")
                .header("Access-Control-Request-Method", "GET"))
        .andExpect(status().isOk())
        .andExpect(header().string("Access-Control-Allow-Origin", "http://127.0.0.1:18084"));
    mvc.perform(
            options("/orders")
                .header("Origin", "https://untrusted.invalid")
                .header("Access-Control-Request-Method", "GET"))
        .andExpect(status().isForbidden());
  }

  @Test
  void 其他资源默认拒绝() throws Exception {
    mvc.perform(get("/internal").with(user("admin").roles("ADMIN")))
        .andExpect(status().isForbidden());
  }
}
