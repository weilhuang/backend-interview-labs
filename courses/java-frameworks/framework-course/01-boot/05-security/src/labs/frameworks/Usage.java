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
      var client = HttpClient.newHttpClient();
      String base = "http://127.0.0.1:" + c.getWebServer().getPort();
      int publicCode =
          client
              .send(
                  HttpRequest.newBuilder(URI.create(base + "/public/ping")).build(),
                  HttpResponse.BodyHandlers.discarding())
              .statusCode();
      int protectedCode =
          client
              .send(
                  HttpRequest.newBuilder(URI.create(base + "/orders")).build(),
                  HttpResponse.BodyHandlers.discarding())
              .statusCode();
      if (publicCode != 200 || protectedCode != 401) throw new AssertionError("真实HTTP安全合同不满足");
      System.out.println("公开接口200，受保护接口匿名401；角色/CSRF完整测试见公开测试文件");
    }
  }
}
