package labs.frameworks;

import static org.assertj.core.api.Assertions.*;

import org.junit.jupiter.api.*;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.client.TestRestTemplate;

@SpringBootTest(classes = Lab.class, webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class HttpIntegrationTest {
  @Autowired TestRestTemplate http;

  @Test
  void 真实HTTP与应用装配() {
    var r = http.getForEntity("/quote?quantity=2", Long.class);
    assertThat(r.getStatusCode().value()).isEqualTo(200);
    assertThat(r.getBody()).isEqualTo(300L);
    assertThat(http.getForEntity("/quote?quantity=0", String.class).getStatusCode().value())
        .isEqualTo(400);
  }
}
