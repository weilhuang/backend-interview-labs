// 标准实现位于作者占位区；学员填写同一公开接口，题面末尾提供完整答案与解析。
package labs;
import java.util.*;
public final class LruCache<K,V> {
    private final int capacity;
    private final LinkedHashMap<K,V> entries = new LinkedHashMap<>(16,0.75f,true);
    public LruCache(int capacity) {
        if (capacity <= 0) throw new IllegalArgumentException("capacity");
        this.capacity = capacity;
    }
    public Optional<V> get(K key) {
        return Optional.ofNullable(entries.get(Objects.requireNonNull(key, "key")));
    }
    public void put(K key, V value) {
        Objects.requireNonNull(key, "key");
        Objects.requireNonNull(value, "value");
        entries.put(key,value);
        if (entries.size() > capacity) {
            Iterator<K> oldest = entries.keySet().iterator();
            oldest.next();
            oldest.remove();
        }
    }
    public List<K> keysLeastToMostRecent() {
        return List.copyOf(entries.keySet());
    }
    public int size() { return entries.size(); }
}
