// 标准实现位于作者占位区；学员填写同一公开接口，题面末尾提供完整答案与解析。
package labs;
import java.util.*;
public final class BoundedStack<T> {
    private final int capacity;
    private final Deque<T> values = new ArrayDeque<>();
    public BoundedStack(int capacity) {
        if (capacity <= 0) throw new IllegalArgumentException("capacity");
        this.capacity = capacity;
    }
    public void push(T value) {
        Objects.requireNonNull(value, "value");
        if (values.size() == capacity) throw new IllegalStateException("full");
        values.push(value);
    }
    public Optional<T> pop() {
        return Optional.ofNullable(values.pollFirst());
    }
    public Optional<T> peek() {
        return Optional.ofNullable(values.peekFirst());
    }
    public int size() { return values.size(); }
}
