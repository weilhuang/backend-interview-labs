package labs.frameworks;

import java.net.*;
import java.net.http.*;
import java.util.Map;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.web.servlet.context.ServletWebServerApplicationContext;

public class Usage {
  public static void main(String[] args) throws Exception {
    SpringApplication app = new SpringApplication(Lab.class);
    app.setDefaultProperties(Map.of("server.port", "0", "server.address", "127.0.0.1"));
    try (var context = (ServletWebServerApplicationContext) app.run()) {
      int port = context.getWebServer().getPort();
      var client = HttpClient.newHttpClient();
      var request =
          HttpRequest.newBuilder(URI.create("http://127.0.0.1:" + port + "/api/orders"))
              .header("Content-Type", "application/json")
              .POST(
                  HttpRequest.BodyPublishers.ofString(
                      "{\"requestId\":\"演示请求\",\"sku\":\"书\",\"quantity\":2,\"unitPriceFen\":150}"))
              .build();
      var response = client.send(request, HttpResponse.BodyHandlers.ofString());
      if (response.statusCode() != 201) throw new AssertionError("真实HTTP创建失败：" + response.body());
      System.out.println("真实HTTP创建成功：" + response.body());
    }
  }
}
