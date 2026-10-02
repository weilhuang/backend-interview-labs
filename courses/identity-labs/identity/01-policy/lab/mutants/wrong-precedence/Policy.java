package labs.identity;
import java.util.Map;
import java.util.Set;

/** C15-01：输入必须来自认证适配层和服务端仓库，不能从请求自报身份构造。 */
public final class Policy {
    public record Subject(String id, String tenant, Set<String> roles, boolean authenticated) {
        public Subject { roles = roles == null ? Set.of() : Set.copyOf(roles); }
    }
    public record Resource(String id, String tenant) { }
    public record Decision(boolean allowed, String reason) { }
    private static final Map<String, Set<String>> PERMISSIONS = Map.of(
        "reader", Set.of("order:read"),
        "editor", Set.of("order:read", "order:approve"),
        "admin", Set.of("order:read", "order:approve"));
    public static Decision authorize(Subject s, String action, Resource r) {
        // BEGIN ANSWER: 默认拒绝、租户隔离、动作白名单，顺序也是错误契约的一部分。
        if (s == null || !s.authenticated() || blank(s.id())) return deny("UNAUTHENTICATED");
        if (r == null || blank(r.id()) || blank(r.tenant()) || blank(s.tenant())) return deny("MISSING_ATTRIBUTE");
        if (!Set.of("order:read", "order:approve").contains(action == null ? "" : action)) return deny("UNKNOWN_ACTION");
        if (!s.tenant().equals(r.tenant())) return deny("TENANT_MISMATCH");
        boolean allowed = s.roles().stream().anyMatch(role -> PERMISSIONS.getOrDefault(role, Set.of()).contains(action));
        return allowed ? new Decision(true, "ALLOW") : deny("ROLE_DENIED");
        // END ANSWER
    }
    private static boolean blank(String x) { return x == null || x.isBlank(); }
    private static Decision deny(String reason) { return new Decision(false, reason); }
}
