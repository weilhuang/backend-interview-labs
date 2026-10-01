package labs.jvm;

import java.util.*;

public final class BoundedStore implements AutoCloseable {
    private final int limit;
    private final Map<String, byte[]> entries = new HashMap<>();
    private int used;
    private boolean closed;

    public BoundedStore(int limit) {
        if (limit < 1 || limit > 1024 * 1024) throw new IllegalArgumentException("容量须为1至1048576字节");
        this.limit = limit;
    }

    public void put(String key, byte[] value) {
        // 作答开始
        ensureOpen();
        Objects.requireNonNull(key, "键不能为空");
        Objects.requireNonNull(value, "值不能为空");
        if (key.length() > 128) throw new IllegalArgumentException("键最多128个UTF-16单元");
        if (!entries.containsKey(key) && entries.size() >= 256)
            throw new IllegalStateException("条目数上限256");
        int old = entries.containsKey(key) ? entries.get(key).length : 0;
        long next = (long) used - old + value.length;
        if (next > limit) throw new IllegalStateException("超出业务保留预算");
        entries.put(key, value.clone());
        used = (int) next;
        // 作答结束
    }

    public byte[] get(String key) {
        ensureOpen();
        byte[] value = entries.get(Objects.requireNonNull(key));
        return value == null ? null : value.clone();
    }

    public int retainedBytes() {
        return used;
    }

    public void remove(String key) {
        ensureOpen();
        byte[] old = entries.remove(Objects.requireNonNull(key));
        if (old != null) used -= old.length;
    }

    @Override
    public void close() {
        // 作答开始
        entries.clear();
        used = 0;
        closed = true;
        // 作答结束
    }

    private void ensureOpen() {
        if (closed) throw new IllegalStateException("存储已关闭");
    }
}
