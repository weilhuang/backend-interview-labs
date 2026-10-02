package labs.identity;
import java.io.IOException;
import java.net.URI;
import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.util.List;
import org.springframework.http.client.SimpleClientHttpRequestFactory;
import org.springframework.security.oauth2.core.OAuth2Error;
import org.springframework.security.oauth2.core.OAuth2TokenValidatorResult;
import org.springframework.security.oauth2.jose.jws.SignatureAlgorithm;
import org.springframework.security.oauth2.jwt.JwtDecoder;
import org.springframework.security.oauth2.jwt.NimbusJwtDecoder;
import org.springframework.web.client.RestTemplate;

/** 由成熟 JOSE 库验签；本类只增加这个 API 的信任与 claims 契约。 */
public final class IdentityTokenDecoder {
    private IdentityTokenDecoder() { }
    public static JwtDecoder create(String issuer, String jwks, String audience, boolean allowLoopbackHttp, Clock clock) {
        trustedEndpoint(issuer, allowLoopbackHttp); trustedEndpoint(jwks, allowLoopbackHttp);
        if (audience == null || audience.isBlank()) throw new IllegalArgumentException("audience required");
        var requestFactory = new SimpleClientHttpRequestFactory();
        requestFactory.setConnectTimeout(Duration.ofSeconds(2));
        requestFactory.setReadTimeout(Duration.ofSeconds(2));
        var rest = new RestTemplate(requestFactory);
        // 单实例对固定 JWKS 源全局节流。攻击者换 kid 也不能绕过一秒一次的预算。
        // 合法轮换恰逢冷却会短暂 401，这是显式可用性取舍，不应改成放行。
        rest.setInterceptors(List.of(new JwksBudget(clock)));
        var decoder = NimbusJwtDecoder.withJwkSetUri(jwks)
            .jwsAlgorithm(SignatureAlgorithm.RS256).restOperations(rest).build();
        decoder.setJwtValidator(jwt -> {
            Instant now = clock.instant();
            boolean valid = issuer.equals(jwt.getClaimAsString("iss"))
                && jwt.getAudience() != null && jwt.getAudience().contains(audience)
                && jwt.getSubject() != null && !jwt.getSubject().isBlank()
                && jwt.getExpiresAt() != null && jwt.getExpiresAt().isAfter(now)
                && (jwt.getNotBefore() == null || !jwt.getNotBefore().isAfter(now))
                && "Bearer".equals(jwt.getClaimAsString("typ"));
            return valid ? OAuth2TokenValidatorResult.success() : OAuth2TokenValidatorResult.failure(
                new OAuth2Error("invalid_token", "access token contract rejected", null));
        });
        return decoder;
    }
    static void trustedEndpoint(String value, boolean allowLoopbackHttp) {
        URI uri = URI.create(value);
        boolean secure = "https".equals(uri.getScheme());
        boolean local = allowLoopbackHttp && "http".equals(uri.getScheme())
            && ("127.0.0.1".equals(uri.getHost()) || "localhost".equals(uri.getHost()));
        if ((!secure && !local) || uri.getHost() == null || uri.getUserInfo() != null
                || uri.getFragment() != null || uri.getQuery() != null)
            throw new IllegalArgumentException("trusted HTTPS endpoint required; local fixture needs explicit profile");
    }
    private static final class JwksBudget implements org.springframework.http.client.ClientHttpRequestInterceptor {
        private final Clock clock; private Instant next = Instant.MIN;
        private JwksBudget(Clock clock) { this.clock = clock; }
        @Override public org.springframework.http.client.ClientHttpResponse intercept(
                org.springframework.http.HttpRequest request, byte[] body,
                org.springframework.http.client.ClientHttpRequestExecution execution) throws IOException {
            synchronized (this) {
                if (clock.instant().isBefore(next)) throw new IOException("JWKS refresh budget exhausted");
                next = clock.instant().plusSeconds(1);
            }
            return execution.execute(request, body);
        }
    }
}
