package labs.frameworks;

import org.springframework.boot.*;
import org.springframework.boot.autoconfigure.*;
import org.springframework.boot.autoconfigure.jdbc.DataSourceAutoConfiguration;
import org.springframework.context.annotation.*;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.web.bind.annotation.*;

@SpringBootConfiguration
@EnableAutoConfiguration(exclude = DataSourceAutoConfiguration.class)
@Import(Lab.Api.class)
public class Lab {
  // 仅隔离教学账户；真实项目不能沿用固定实验口令。
  @Bean
  org.springframework.security.core.userdetails.UserDetailsService users() {
    var encoder =
        org.springframework.security.crypto.factory.PasswordEncoderFactories
            .createDelegatingPasswordEncoder();
    var reader =
        org.springframework.security.core.userdetails.User.withUsername("reader")
            .password(encoder.encode("lab-only"))
            .roles("READER")
            .build();
    var admin =
        org.springframework.security.core.userdetails.User.withUsername("admin")
            .password(encoder.encode("lab-only"))
            .roles("ADMIN")
            .build();
    return new org.springframework.security.provisioning.InMemoryUserDetailsManager(reader, admin);
  }

  @Bean
  org.springframework.web.cors.CorsConfigurationSource corsConfigurationSource() {
    var config = new org.springframework.web.cors.CorsConfiguration();
    config.setAllowedOrigins(java.util.List.of("http://127.0.0.1:18084"));
    config.setAllowedMethods(java.util.List.of("GET", "POST"));
    config.setAllowedHeaders(java.util.List.of("Authorization", "Content-Type", "X-CSRF-TOKEN"));
    config.setAllowCredentials(true);
    var source = new org.springframework.web.cors.UrlBasedCorsConfigurationSource();
    source.registerCorsConfiguration("/**", config);
    return source;
  }

  @Bean
  SecurityFilterChain security(HttpSecurity http) throws Exception {
    // 练习区开始
    return http.cors(Customizer.withDefaults())
        .authorizeHttpRequests(
            auth ->
                auth.requestMatchers("/public/ping")
                    .permitAll()
                    .requestMatchers(HttpMethod.GET, "/orders")
                    .hasAnyRole("READER", "ADMIN")
                    .requestMatchers(HttpMethod.POST, "/orders")
                    .hasRole("ADMIN")
                    .anyRequest()
                    .denyAll())
        .httpBasic(Customizer.withDefaults())
        .build();
    // 练习区结束
  }

  @RestController
  public static class Api {
    @GetMapping("/public/ping")
    String ping() {
      return "可用";
    }

    @GetMapping("/orders")
    String list() {
      return "订单列表";
    }

    @PostMapping("/orders")
    @ResponseStatus(org.springframework.http.HttpStatus.CREATED)
    String create() {
      return "已创建";
    }
  }

  public static void main(String[] args) {
    SpringApplication app = new SpringApplication(Lab.class);
    app.setDefaultProperties(java.util.Map.of("server.address", "127.0.0.1"));
    app.run(args);
  }
}
