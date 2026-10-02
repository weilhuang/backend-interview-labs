package labs.identity;
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;
import org.springframework.http.HttpStatus;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.web.bind.annotation.*;
import org.springframework.web.server.ResponseStatusException;
@RestController
@RequestMapping("/api/orders")
class OrderController {
    // 完整小项目的合成仓库。tenant 从这里查，不能从 path/header 的租户主张取。
    private final Map<String, Policy.Resource> orders = Map.of(
        "order-a", new Policy.Resource("order-a", "tenant-a"),
        "order-b", new Policy.Resource("order-b", "tenant-b"));
    private final Map<String, Integer> approvals = new ConcurrentHashMap<>();
    @GetMapping("/{id}") Map<String, Object> read(@PathVariable String id, @AuthenticationPrincipal Jwt jwt) {
        var resource = authorize(jwt, id, "order:read");
        return Map.of("id", id, "tenant", resource.tenant(), "approvals", approvals.getOrDefault(id, 0));
    }
    @PostMapping("/{id}/approve") Map<String, Object> approve(@PathVariable String id, @AuthenticationPrincipal Jwt jwt) {
        authorize(jwt, id, "order:approve"); // 在状态改变之前强制检查
        int count = approvals.merge(id, 1, Integer::sum);
        return Map.of("id", id, "approvals", count);
    }
    private Policy.Resource authorize(Jwt jwt, String id, String action) {
        var resource = orders.get(id);
        if (resource == null) throw new ResponseStatusException(HttpStatus.NOT_FOUND, "ORDER_NOT_FOUND");
        var decision = Policy.authorize(TrustedSubject.from(jwt), action, resource);
        if (!decision.allowed()) throw new ResponseStatusException(HttpStatus.FORBIDDEN, "ACCESS_DENIED");
        return resource;
    }
}
