// 标准实现位于作者占位区；学员填写同一公开接口，题面末尾提供完整答案与解析。
package labs;
import java.util.*;
public final class RecentIds {
    private final int capacity;
    private final Deque<String> order = new ArrayDeque<>();
    private final Set<String> seen = new HashSet<>();
    public RecentIds(int capacity) {
        if (capacity <= 0) throw new IllegalArgumentException("capacity");
        this.capacity = capacity;
    }
    public boolean offer(String id) {
        Objects.requireNonNull(id, "id");
        if (id.isBlank()) throw new IllegalArgumentException("blank id");
        if (seen.contains(id)) return false;
        if (order.size() == capacity) seen.remove(order.removeFirst());
        order.addLast(id);
        seen.add(id);
        return true;
    }
    public List<String> snapshot() {
        return List.copyOf(order);
    }
}
