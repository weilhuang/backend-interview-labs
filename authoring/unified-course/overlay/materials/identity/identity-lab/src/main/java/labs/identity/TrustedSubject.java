package labs.identity;
import java.util.Collection;
import java.util.Map;
import java.util.Set;
import java.util.stream.Collectors;
import org.springframework.security.oauth2.jwt.Jwt;
/** 只读已由 Resource Server 验签的 Jwt；不读 X-Tenant/X-Role 等客户端自报头。 */
final class TrustedSubject {
    static Policy.Subject from(Jwt jwt) {
        String tenant = jwt.getClaimAsString("tenant_id");
        Object all = jwt.getClaim("tenant_roles");
        Object selected = all instanceof Map<?, ?> m ? m.get(tenant) : null;
        Set<String> roles = selected instanceof Collection<?> c
            ? c.stream().filter(String.class::isInstance).map(String.class::cast).collect(Collectors.toUnmodifiableSet())
            : Set.of();
        return new Policy.Subject(jwt.getSubject(), tenant, roles, true);
    }
}
