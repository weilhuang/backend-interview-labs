package labs.frameworks;

import java.util.*;
import org.springframework.boot.*;
import org.springframework.boot.autoconfigure.*;
import org.springframework.boot.autoconfigure.jdbc.DataSourceAutoConfiguration;
import org.springframework.context.annotation.*;
import org.springframework.core.MethodParameter;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;
import org.springframework.web.bind.support.WebDataBinderFactory;
import org.springframework.web.context.request.NativeWebRequest;
import org.springframework.web.method.support.*;
import org.springframework.web.servlet.config.annotation.*;

@SpringBootConfiguration
@EnableAutoConfiguration(exclude = DataSourceAutoConfiguration.class)
@Import({Lab.Api.class, Lab.Errors.class, Lab.Mvc.class})
public class Lab {
  public record Tenant(String id) {}

  public static class TenantResolver implements HandlerMethodArgumentResolver {
    public boolean supportsParameter(MethodParameter p) {
      return p.getParameterType() == Tenant.class;
    }

    public Object resolveArgument(
        MethodParameter p,
        ModelAndViewContainer m,
        NativeWebRequest request,
        WebDataBinderFactory b) {
      // 练习区开始
      String tenant = request.getHeader("X-Lab-Tenant");
      if (tenant == null || !tenant.matches("[a-z]{2,12}"))
        throw new IllegalArgumentException("教学租户头不合法");
      return new Tenant(tenant);
      // 练习区结束
    }
  }

  @Configuration
  public static class Mvc implements WebMvcConfigurer {
    public void addArgumentResolvers(List<HandlerMethodArgumentResolver> resolvers) {
      resolvers.add(new TenantResolver());
    }

    public void addInterceptors(InterceptorRegistry registry) {
      registry.addInterceptor(
          new org.springframework.web.servlet.HandlerInterceptor() {
            public boolean preHandle(
                jakarta.servlet.http.HttpServletRequest request,
                jakarta.servlet.http.HttpServletResponse response,
                Object handler) {
              response.setHeader("X-Lab-Stage", "mvc-interceptor");
              return true;
            }
          });
    }
  }

  @RestController
  public static class Api {
    @GetMapping("/orders/{id}")
    public Map<String, Object> get(@PathVariable long id, Tenant tenant) {
      if (id < 1) throw new IllegalArgumentException("订单号必须正数");
      return Map.of("tenant", tenant.id(), "orderId", id);
    }
  }

  @RestControllerAdvice
  public static class Errors {
    @ExceptionHandler(IllegalArgumentException.class)
    ResponseEntity<String> invalid() {
      return ResponseEntity.badRequest().body("请求参数不合法");
    }
  }

  public static void main(String[] args) {
    var app = new SpringApplication(Lab.class);
    app.setDefaultProperties(
        java.util.Map.of("server.address", "127.0.0.1", "server.port", "18084"));
    app.run(args);
  }
}
