package labs.identity;
import java.time.Clock;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.oauth2.jwt.JwtDecoder;
import org.springframework.security.web.SecurityFilterChain;
@Configuration
class SecurityConfig {
    @Bean JwtDecoder jwtDecoder(@Value("${identity.issuer}") String issuer,
            @Value("${identity.jwks}") String jwks, @Value("${identity.audience}") String audience,
            @Value("${identity.allow-loopback-http:false}") boolean local) {
        return IdentityTokenDecoder.create(issuer, jwks, audience, local, Clock.systemUTC());
    }
    @Bean SecurityFilterChain security(HttpSecurity http) throws Exception {
        return http.sessionManagement(s -> s.sessionCreationPolicy(SessionCreationPolicy.STATELESS))
            // 本 API 只接受显式 Bearer header，不启用 cookie/session/basic 登录；BFF 必须另启 CSRF。
            .csrf(csrf -> csrf.ignoringRequestMatchers("/api/**"))
            .authorizeHttpRequests(a -> a.requestMatchers("/", "/index.html", "/app.js", "/style.css").permitAll()
                .requestMatchers("/api/**").authenticated().anyRequest().denyAll())
            .oauth2ResourceServer(o -> o.jwt(j -> {})).build();
    }
}
