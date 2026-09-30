package labs.frameworks;

import static org.assertj.core.api.Assertions.*;

import java.util.*;
import java.util.concurrent.*;
import org.junit.jupiter.api.*;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.client.TestRestTemplate;
import org.springframework.boot.test.web.server.LocalServerPort;
import org.springframework.http.*;

@SpringBootTest(classes = Lab.class, webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class LabTest {
  @Autowired TestRestTemplate http;
  @LocalServerPort int port;

  ResponseEntity<Lab.Order> post(Lab.Request r) {
    return http.postForEntity("/api/orders", r, Lab.Order.class);
  }

  @Test
  void 真实HTTP创建重试与冲突() {
    String k = UUID.randomUUID().toString();
    var r = new Lab.Request(k, "书", 2, 150);
    var first = post(r);
    assertThat(first.getStatusCode().value()).isEqualTo(201);
    assertThat(first.getBody().totalFen()).isEqualTo(300);
    assertThat(first.getHeaders().getLocation().toString())
        .isEqualTo("/api/orders/" + first.getBody().id());
    var again = post(r);
    assertThat(again.getStatusCode().value()).isEqualTo(200);
    assertThat(again.getBody().id()).isEqualTo(first.getBody().id());
    var conflict =
        http.postForEntity("/api/orders", new Lab.Request(k, "另一商品", 2, 150), Lab.ErrorBody.class);
    assertThat(conflict.getStatusCode().value()).isEqualTo(409);
  }

  @Test
  void 校验错误格式和不存在() {
    for (var r :
        List.of(
            new Lab.Request("a", "", 1, 1),
            new Lab.Request("a", "书", 0, 1),
            new Lab.Request("a", "书", 101, 1),
            new Lab.Request("a", "书", 2, Long.MAX_VALUE))) {
      var response = http.postForEntity("/api/orders", r, Lab.ErrorBody.class);
      assertThat(response.getStatusCode().value()).isEqualTo(400);
      assertThat(response.getBody().code()).isEqualTo("INVALID_INPUT");
    }
    assertThat(
            http.getForEntity("/api/orders/99999999", Lab.ErrorBody.class).getStatusCode().value())
        .isEqualTo(404);
  }

  @Test
  void 同进程并发同键只创建一次() throws Exception {
    var store = new Lab.Store();
    try (var pool = Executors.newFixedThreadPool(4)) {
      var calls = new ArrayList<Callable<Lab.Creation>>();
      for (int i = 0; i < 20; i++)
        calls.add(() -> store.create(new Lab.Request("same", "商品", 1, 100)));
      var results = pool.invokeAll(calls);
      long created = 0;
      for (var f : results) if (f.get().created()) created++;
      assertThat(created).isEqualTo(1);
      assertThat(store.list()).hasSize(1);
    }
  }

  @Test
  void 中文前端从真实服务返回() {
    var page = http.getForEntity("/", String.class);
    assertThat(page.getStatusCode().value()).isEqualTo(200);
    assertThat(page.getBody()).contains("订单实验室", "/api/orders", "requestId");
  }

  @Test
  void 分页边界由后端校验() {
    assertThat(
            http.getForEntity("/api/orders?offset=-1", Lab.ErrorBody.class).getStatusCode().value())
        .isEqualTo(400);
    assertThat(
            http.getForEntity("/api/orders?limit=101", Lab.ErrorBody.class).getStatusCode().value())
        .isEqualTo(400);
    assertThat(http.getForEntity("/api/orders?limit=2", Lab.Order[].class).getBody().length)
        .isLessThanOrEqualTo(2);
  }

  @Test
  void 非法JSON不会泄漏堆栈() {
    HttpHeaders h = new HttpHeaders();
    h.setContentType(MediaType.APPLICATION_JSON);
    var response = http.postForEntity("/api/orders", new HttpEntity<>("{坏JSON", h), String.class);
    assertThat(response.getStatusCode().value()).isEqualTo(400);
    assertThat(response.getBody()).doesNotContain("stackTrace", "java.lang");
  }
}
