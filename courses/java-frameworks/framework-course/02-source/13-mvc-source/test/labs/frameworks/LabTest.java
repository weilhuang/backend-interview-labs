package labs.frameworks;

import static org.assertj.core.api.Assertions.*;

import org.junit.jupiter.api.*;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.client.TestRestTemplate;
import org.springframework.http.*;

@SpringBootTest(classes = Lab.class, webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class LabTest {
  @Autowired TestRestTemplate http;

  ResponseEntity<String> get(String tenant, String path) {
    var h = new HttpHeaders();
    if (tenant != null) h.set("X-Lab-Tenant", tenant);
    return http.exchange(path, HttpMethod.GET, new HttpEntity<>(h), String.class);
  }

  @Test
  void 真实参数解析和拦截器() {
    var r = get("acme", "/orders/7");
    assertThat(r.getStatusCode().value()).isEqualTo(200);
    assertThat(r.getBody()).contains("acme", "7");
    assertThat(r.getHeaders().getFirst("X-Lab-Stage")).isEqualTo("mvc-interceptor");
  }

  @Test
  void 缺失和非法头返回400() {
    for (String tenant : new String[] {null, "A", "acme/../../x", "toolongtenantname"})
      assertThat(get(tenant, "/orders/7").getStatusCode().value()).isEqualTo(400);
  }

  @Test
  void 业务和转换错误同样拒绝() {
    assertThat(get("acme", "/orders/0").getStatusCode().value()).isEqualTo(400);
    assertThat(get("acme", "/orders/not-number").getStatusCode().value()).isEqualTo(400);
  }
}
