package labs.frameworks;

import java.net.*;
import java.net.http.*;
import java.util.Map;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.web.servlet.context.ServletWebServerApplicationContext;

public class Usage {
  public static void main(String[] args) throws Exception {
    var app = new SpringApplication(Lab.class);
    app.setDefaultProperties(Map.of("server.port", "0", "server.address", "127.0.0.1"));
    try (var c = (ServletWebServerApplicationContext) app.run()) {
      var request =
          HttpRequest.newBuilder(
                  URI.create("http://127.0.0.1:" + c.getWebServer().getPort() + "/orders/7"))
              .header("X-Lab-Tenant", "acme")
              .build();
      var r = HttpClient.newHttpClient().send(request, HttpResponse.BodyHandlers.ofString());
      if (r.statusCode() != 200) throw new AssertionError("调用失败");
      System.out.println(r.body());
    }
  }
}
