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
    public static Decision authorize(Subject s, String action, Resource r) {
        if (s == null || !s.authenticated() || blank(s.id())) return deny("UNAUTHENTICATED");
        if (r == null || blank(r.id()) || blank(r.tenant()) || blank(s.tenant())) return deny("MISSING_ATTRIBUTE");
        if (!s.tenant().equals(r.tenant())) return deny("TENANT_MISMATCH");
        boolean read = "order:read".equals(action), write = "order:approve".equals(action);
        if (!read && !write) return deny("UNKNOWN_ACTION");
        boolean allowed = (read && s.roles().contains("reader")) || s.roles().contains("editor") || s.roles().contains("admin");
        return allowed ? new Decision(true, "ALLOW") : deny("ROLE_DENIED");
    }
    private static boolean blank(String x) { return x == null || x.isBlank(); }
    private static Decision deny(String reason) { return new Decision(false, reason); }
}
