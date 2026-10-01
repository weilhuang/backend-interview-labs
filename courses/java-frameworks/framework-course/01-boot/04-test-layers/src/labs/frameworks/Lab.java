package labs.frameworks;

import org.springframework.boot.*;
import org.springframework.boot.autoconfigure.*;
import org.springframework.boot.autoconfigure.jdbc.DataSourceAutoConfiguration;
import org.springframework.context.annotation.*;
import org.springframework.http.*;
import org.springframework.web.bind.annotation.*;

@SpringBootConfiguration
@EnableAutoConfiguration(exclude = DataSourceAutoConfiguration.class)
@Import({Lab.Api.class, Lab.Errors.class})
public class Lab {
  public interface Prices {
    long unitPrice();
  }

  public static class Quotes {
    final Prices prices;

    public Quotes(Prices prices) {
      this.prices = prices;
    }

    public long total(int quantity) {
      // 练习区开始
      if (quantity < 1 || quantity > 100) throw new IllegalArgumentException("数量不合法");
      long price = prices.unitPrice();
      if (price < 1) throw new IllegalStateException("价格服务返回错误数据");
      return Math.multiplyExact(price, quantity);
      // 练习区结束
    }
  }

  @Bean
  Prices prices() {
    return () -> 150;
  }

  @Bean
  Quotes quotes(Prices p) {
    return new Quotes(p);
  }

  @RestController
  public static class Api {
    final Quotes quotes;

    public Api(Quotes q) {
      quotes = q;
    }

    @GetMapping("/quote")
    public long quote(@RequestParam int quantity) {
      return quotes.total(quantity);
    }
  }

  @RestControllerAdvice
  public static class Errors {
    @ExceptionHandler({IllegalArgumentException.class, ArithmeticException.class})
    ResponseEntity<String> invalid() {
      return ResponseEntity.badRequest().body("报价参数不合法");
    }

    @ExceptionHandler(IllegalStateException.class)
    ResponseEntity<String> unavailable() {
      return ResponseEntity.status(503).body("报价暂不可用");
    }
  }

  public static void main(String[] args) {
    var app = new SpringApplication(Lab.class);
    app.setDefaultProperties(
        java.util.Map.of("server.address", "127.0.0.1", "server.port", "18084"));
    app.run(args);
  }
}
