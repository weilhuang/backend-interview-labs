package labs.frameworks;

import jakarta.validation.Valid;
import jakarta.validation.constraints.*;
import java.net.URI;
import java.util.*;
import org.springframework.boot.*;
import org.springframework.boot.autoconfigure.*;
import org.springframework.context.annotation.*;
import org.springframework.http.*;
import org.springframework.http.converter.HttpMessageNotReadableException;
import org.springframework.web.bind.MethodArgumentNotValidException;
import org.springframework.web.bind.annotation.*;

@SpringBootConfiguration
@EnableAutoConfiguration
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
    private final org.springframework.jdbc.core.JdbcTemplate jdbc;
    private final org.springframework.transaction.support.TransactionTemplate tx;

    public Store(
        org.springframework.jdbc.core.JdbcTemplate jdbc,
        org.springframework.transaction.support.TransactionTemplate tx) {
      this.jdbc = jdbc;
      this.tx = tx;
    }

    private Order row(java.sql.ResultSet rs, int n) throws java.sql.SQLException {
      return new Order(
          rs.getLong("id"),
          rs.getString("request_id"),
          rs.getString("sku"),
          rs.getInt("quantity"),
          rs.getLong("unit_price"),
          rs.getLong("total"));
    }

    public Creation create(Request r) {
      // 练习区开始
      if (r.quantity() < 1 || r.quantity() > 100 || r.unitPriceFen() < 1)
        throw new IllegalArgumentException("数量或金额不合法");
      long total = Math.multiplyExact(r.quantity(), r.unitPriceFen());
      return tx.execute(
          status -> {
            var old =
                jdbc.query("select * from orders where request_id=?", this::row, r.requestId());
            if (!old.isEmpty()) {
              Order x = old.get(0);
              if (!x.sku().equals(r.sku())
                  || x.quantity() != r.quantity()
                  || x.unitPriceFen() != r.unitPriceFen()) throw new Conflict();
              return new Creation(x, false);
            }
            var key = new org.springframework.jdbc.support.GeneratedKeyHolder();
            jdbc.update(
                connection -> {
                  var statement =
                      connection.prepareStatement(
                          "insert into orders(request_id,sku,quantity,unit_price,total)"
                              + " values(?,?,?,?,?)",
                          java.sql.Statement.RETURN_GENERATED_KEYS);
                  statement.setString(1, r.requestId());
                  statement.setString(2, r.sku());
                  statement.setInt(3, r.quantity());
                  statement.setLong(4, r.unitPriceFen());
                  statement.setLong(5, total);
                  return statement;
                },
                key);
            return new Creation(
                new Order(
                    java.util.Objects.requireNonNull(key.getKey()).longValue(),
                    r.requestId(),
                    r.sku(),
                    r.quantity(),
                    r.unitPriceFen(),
                    total),
                true);
          });
      // 练习区结束
    }

    public List<Order> list() {
      return jdbc.query("select * from orders order by id", this::row);
    }

    public Order get(long id) {
      return jdbc.query("select * from orders where id=?", this::row, id).stream()
          .findFirst()
          .orElseThrow(Missing::new);
    }
  }

  @Bean
  Store store(
      org.springframework.jdbc.core.JdbcTemplate jdbc,
      org.springframework.transaction.PlatformTransactionManager tm) {
    return new Store(jdbc, new org.springframework.transaction.support.TransactionTemplate(tm));
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

    @ExceptionHandler(org.springframework.dao.DuplicateKeyException.class)
    ResponseEntity<ErrorBody> duplicate() {
      return ResponseEntity.status(409)
          .body(new ErrorBody("CONCURRENT_RETRY", "并发同键请求，请使用相同参数重试确认结果"));
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

  public static void main(String[] args) {
    SpringApplication app = new SpringApplication(Lab.class);
    app.setDefaultProperties(Map.of("server.address", "127.0.0.1", "server.port", "18084"));
    app.run(args);
  }
}
