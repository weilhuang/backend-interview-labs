package labs.frameworks;

import jakarta.validation.Valid;
import jakarta.validation.constraints.*;
import java.net.URI;
import java.util.*;
import org.springframework.boot.*;
import org.springframework.boot.autoconfigure.*;
import org.springframework.boot.autoconfigure.jdbc.DataSourceAutoConfiguration;
import org.springframework.context.annotation.*;
import org.springframework.http.*;
import org.springframework.http.converter.HttpMessageNotReadableException;
import org.springframework.web.bind.MethodArgumentNotValidException;
import org.springframework.web.bind.annotation.*;

@SpringBootConfiguration
@EnableAutoConfiguration(exclude = DataSourceAutoConfiguration.class)
@Import({Lab.Api.class, Lab.Errors.class})
public class Lab {
  public record Request(
      @NotBlank String requestId,
      @NotBlank String sku,
      @Min(1) int quantity,
      @Min(1) long unitPriceFen) {}

  public record Order(
      long id, String requestId, String sku, int quantity, long unitPriceFen, long totalFen) {}

  public record Creation(Order order, boolean created) {}

  public record ErrorBody(String code, String message) {}

  public static class Conflict extends RuntimeException {}

  public static class Missing extends RuntimeException {}

  public static class Store {
    private long sequence = 0;
    private final Map<String, Order> requests = new HashMap<>();

    public synchronized Creation create(Request r) {
      // 练习区开始
      if (r.quantity() < 1 || r.quantity() > 100 || r.unitPriceFen() < 1)
        throw new IllegalArgumentException("数量或金额不合法");
      long total = Math.multiplyExact(r.quantity(), r.unitPriceFen());
      Order old = requests.get(r.requestId());
      if (old != null) {
        if (!old.sku().equals(r.sku())
            || old.quantity() != r.quantity()
            || old.unitPriceFen() != r.unitPriceFen()) throw new Conflict();
        return new Creation(old, false);
      }
      Order order =
          new Order(++sequence, r.requestId(), r.sku(), r.quantity(), r.unitPriceFen(), total);
      requests.put(r.requestId(), order);
      return new Creation(order, true);
      // 练习区结束
    }

    public synchronized List<Order> list() {
      return requests.values().stream().sorted(Comparator.comparingLong(Order::id)).toList();
    }

    public synchronized Order get(long id) {
      return requests.values().stream()
          .filter(o -> o.id() == id)
          .findFirst()
          .orElseThrow(Missing::new);
    }
  }

  @Bean
  Store store() {
    return new Store();
  }

  @RestController
  @RequestMapping("/api/orders")
  public static class Api {
    private final Store store;

    public Api(Store store) {
      this.store = store;
    }

    @GetMapping
    public List<Order> list(
        @RequestParam(defaultValue = "0") int offset,
        @RequestParam(defaultValue = "20") int limit) {
      if (offset < 0 || limit < 1 || limit > 100) throw new IllegalArgumentException("分页参数不合法");
      return store.list().stream().skip(offset).limit(limit).toList();
    }

    @GetMapping("/{id}")
    public Order get(@PathVariable long id) {
      return store.get(id);
    }

    @PostMapping
    public ResponseEntity<Order> create(@Valid @RequestBody Request request) {
      Creation result = store.create(request);
      return ResponseEntity.status(result.created() ? HttpStatus.CREATED : HttpStatus.OK)
          .location(URI.create("/api/orders/" + result.order().id()))
          .body(result.order());
    }
  }

  @RestControllerAdvice
  public static class Errors {
    @ExceptionHandler(Conflict.class)
    ResponseEntity<ErrorBody> conflict() {
      return ResponseEntity.status(409).body(new ErrorBody("CONFLICT", "请求编号已用于不同订单"));
    }

    @ExceptionHandler(Missing.class)
    ResponseEntity<ErrorBody> missing() {
      return ResponseEntity.status(404).body(new ErrorBody("NOT_FOUND", "订单不存在"));
    }

    @ExceptionHandler({
      MethodArgumentNotValidException.class,
      HttpMessageNotReadableException.class,
      IllegalArgumentException.class,
      ArithmeticException.class
    })
    ResponseEntity<ErrorBody> invalid() {
      return ResponseEntity.badRequest().body(new ErrorBody("INVALID_INPUT", "输入不合法或金额溢出"));
    }
  }

  // 仅供loopback演示启动器关联本地实例，不是生产鉴权凭据。
  // 普通IDE/测试运行未设置token时不添加标记；请求不需要携带token。
  @Bean
  jakarta.servlet.Filter labInstanceHeader() {
    String token = System.getProperty("framework.lab.token", "");
    return (request, response, chain) -> {
      if (token.matches("[0-9a-f]{32}")) {
        ((jakarta.servlet.http.HttpServletResponse) response)
            .setHeader("X-Framework-Lab-Instance", token);
      }
      chain.doFilter(request, response);
    };
  }

  public static void main(String[] args) {
    SpringApplication app = new SpringApplication(Lab.class);
    app.setDefaultProperties(Map.of("server.address", "127.0.0.1", "server.port", "18084"));
    app.run(args);
  }
}
