package labs.capstone;

import static labs.capstone.Model.*;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.autoconfigure.jdbc.DataSourceAutoConfiguration;
import org.springframework.context.annotation.Bean;
import org.springframework.http.*;
import org.springframework.web.bind.annotation.*;

import java.util.*;

@SpringBootApplication(exclude = DataSourceAutoConfiguration.class)
public class BootApp {
    public static void main(String[] args) {
        SpringApplication.run(BootApp.class, args);
    }

    @Bean(destroyMethod = "close")
    Runtime courseRuntime() throws Exception {
        return new Runtime(Config.environment());
    }

    @RestController
    static class Api {
        private final Runtime runtime;

        Api(Runtime runtime) {
            this.runtime = runtime;
        }

        @GetMapping("/api/dashboard")
        Object dashboard() throws Exception {
            return runtime.dashboard();
        }

        @GetMapping("/api/health")
        Object health() {
            return runtime.health();
        }

        @GetMapping("/api/ready")
        Object ready() {
            try {
                long backlog = runtime.backlog();
                return ResponseEntity.status(
                                RecoveryPolicy.decide(true, true, true, true, backlog, 1000).ready()
                                        ? 200
                                        : 503)
                        .body(Map.of("backlog", backlog));
            } catch (Exception e) {
                return ResponseEntity.status(503).body(Map.of("message", "数据库未就绪"));
            }
        }

        @PostMapping("/api/orders")
        Object place(@RequestBody Command command) throws Exception {
            long pending = runtime.backlog();
            if (!RecoveryPolicy.decide(true, true, true, true, pending, 1000).ready())
                return ResponseEntity.status(503).body(Map.of("message", "当前积压超过接单水位，请先重放"));
            return runtime.orders.place(command, Fault.NONE);
        }

        @GetMapping("/api/orders/{id}")
        Object find(@PathVariable String id, @RequestParam(defaultValue = "false") boolean fresh)
                throws Exception {
            Order order = runtime.orders.find(id, fresh);
            return order == null
                    ? ResponseEntity.status(404).body(Map.of("message", "订单不存在"))
                    : order;
        }

        @PostMapping("/api/orders/{id}/cancel")
        Object cancel(@PathVariable String id) throws Exception {
            return runtime.orders.cancel(id);
        }

        @PostMapping("/api/replay")
        Object replay() throws Exception {
            return runtime.replay();
        }
    }

    @RestControllerAdvice
    static class Errors {
        @ExceptionHandler(Conflict.class)
        ResponseEntity<?> conflict(Conflict e) {
            return ResponseEntity.status(409).body(Map.of("message", e.getMessage()));
        }

        @ExceptionHandler({
            IllegalArgumentException.class,
            NullPointerException.class,
            org.springframework.http.converter.HttpMessageNotReadableException.class
        })
        ResponseEntity<?> invalid(Exception e) {
            return ResponseEntity.badRequest()
                    .body(Map.of("message", Objects.toString(e.getMessage(), "请求不合法")));
        }

        @ExceptionHandler(Exception.class)
        ResponseEntity<?> unavailable(Exception e) {
            return ResponseEntity.status(503)
                    .body(
                            Map.of(
                                    "message",
                                    "依赖暂不可用或结果未知；保留原请求号，查询后再重试",
                                    "type",
                                    e.getClass().getSimpleName()));
        }
    }
}
