package labs.identity;
import java.util.Set;
public final class Usage {
    public static void main(String[] args) {
        var reader = new Policy.Subject("fixture-alice", "tenant-a", Set.of("reader"), true);
        System.out.println(Policy.authorize(reader, "order:read", new Policy.Resource("order-a", "tenant-a")));
        System.out.println(Policy.authorize(reader, "order:approve", new Policy.Resource("order-a", "tenant-a")));
        System.out.println(Policy.authorize(reader, "order:read", new Policy.Resource("order-b", "tenant-b")));
    }
}
