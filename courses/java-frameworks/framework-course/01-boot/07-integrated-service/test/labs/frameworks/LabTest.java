package labs.frameworks;

import static org.assertj.core.api.Assertions.*;

import org.junit.jupiter.api.*;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.client.TestRestTemplate;
import org.springframework.jdbc.core.JdbcTemplate;

@SpringBootTest(classes = Lab.class, webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class LabTest {
  @Autowired TestRestTemplate http;
  @Autowired JdbcTemplate jdbc;

  @Test
  void 真实HTTP到数据库() {
    String id = java.util.UUID.randomUUID().toString();
    var request = new Lab.Request(id, "BOOK", 2, 150);
    var r = http.postForEntity("/api/orders", request, Lab.Order.class);
    assertThat(r.getStatusCode().value()).isEqualTo(201);
    assertThat(r.getBody().totalFen()).isEqualTo(300);
    assertThat(
            jdbc.queryForObject(
                "select count(*) from orders where request_id=?", Integer.class, id))
        .isEqualTo(1);
    var repeat = http.postForEntity("/api/orders", request, Lab.Order.class);
    assertThat(repeat.getStatusCode().value()).isEqualTo(200);
    assertThat(repeat.getBody().id()).isEqualTo(r.getBody().id());
    assertThat(
            http.getForEntity("/api/orders/" + r.getBody().id(), Lab.Order.class).getBody().sku())
        .isEqualTo("BOOK");
  }

  @Test
  void 错误不会写入() {
    int count = jdbc.queryForObject("select count(*) from orders", Integer.class);
    var r =
        http.postForEntity(
            "/api/orders", new Lab.Request("非法", "BOOK", 101, 100), Lab.ErrorBody.class);
    assertThat(r.getStatusCode().value()).isEqualTo(400);
    assertThat(jdbc.queryForObject("select count(*) from orders", Integer.class)).isEqualTo(count);
  }

  @Test
  void 同键变更拒绝而非覆盖() {
    String id = java.util.UUID.randomUUID().toString();
    http.postForEntity("/api/orders", new Lab.Request(id, "BOOK", 1, 100), Lab.Order.class);
    var bad =
        http.postForEntity(
            "/api/orders", new Lab.Request(id, "OTHER", 1, 100), Lab.ErrorBody.class);
    assertThat(bad.getStatusCode().value()).isEqualTo(409);
    assertThat(jdbc.queryForObject("select sku from orders where request_id=?", String.class, id))
        .isEqualTo("BOOK");
  }

  @Test
  void 中文页面可从真实端口使用() {
    assertThat(http.getForEntity("/", String.class).getBody()).contains("订单实验室");
  }

  @Test
  void 响应实例标记只来自合法启动token() throws Exception {
    String previous = System.getProperty("framework.lab.token");
    try {
      for (String token : java.util.List.of("0123456789abcdef0123456789abcdef", "", "invalid")) {
        System.setProperty("framework.lab.token", token);
        var response = new org.springframework.mock.web.MockHttpServletResponse();
        var chain = new org.springframework.mock.web.MockFilterChain();
        new Lab().labInstanceHeader().doFilter(
            new org.springframework.mock.web.MockHttpServletRequest(), response, chain);
        assertThat(response.getHeader("X-Framework-Lab-Instance"))
            .isEqualTo(token.length() == 32 ? token : null);
        assertThat(chain.getRequest()).isNotNull();
      }
    } finally {
      if (previous == null) System.clearProperty("framework.lab.token");
      else System.setProperty("framework.lab.token", previous);
    }
  }
}
