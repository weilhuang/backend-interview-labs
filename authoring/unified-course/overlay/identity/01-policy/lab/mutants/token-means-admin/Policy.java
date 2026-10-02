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
        return new Decision(true, "ALLOW");
        // END ANSWER
    }
    private static boolean blank(String x) { return x == null || x.isBlank(); }
    private static Decision deny(String reason) { return new Decision(false, reason); }
}
