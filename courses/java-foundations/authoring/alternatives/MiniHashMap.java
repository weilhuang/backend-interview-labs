package labs.foundation;

import java.util.*;

/** 教学拉链哈希表；没有树化、迭代器、并发或序列化。 */
public final class MiniHashMap<K, V> {
    private static final class Entry<K, V> {
        final int hash;
        final K key;
        V value;
        Entry<K, V> next;

        Entry(int hash, K key, V value, Entry<K, V> next) {
            this.hash = hash;
            this.key = key;
            this.value = value;
            this.next = next;
        }
    }

    @SuppressWarnings("unchecked")
    private Entry<K, V>[] table = (Entry<K, V>[]) new Entry[4];

    private int size;

    private static int hash(Object key) {
        int h = Objects.hashCode(key);
        return h ^ (h >>> 16);
    }

    private Entry<K, V> find(Object key) {
        int h = hash(key);
        for (Entry<K, V> e = table[h & (table.length - 1)]; e != null; e = e.next)
            if (e.hash == h && Objects.equals(e.key, key)) return e;
        return null;
    }

    public int size() {
        return size;
    }

    public int capacity() {
        return table.length;
    }

    public V get(Object key) {
        Entry<K, V> e = find(key);
        return e == null ? null : e.value;
    }

    public boolean containsKey(Object key) {
        return find(key) != null;
    }

    public V put(K key, V value) {
        // 作答开始
        Entry<K, V> existing = find(key);
        if (existing != null) {
            V old = existing.value;
            existing.value = value;
            return old;
        }
        if (size == 4096) throw new IllegalStateException("最多4096条目");
        if (size + 1 > table.length * 3 / 4) resize();
        int h = hash(key), bucket = h & (table.length - 1);
        Entry<K, V> node = new Entry<>(h, key, value, null);
        if (table[bucket] == null) table[bucket] = node;
        else {
            Entry<K, V> tail = table[bucket];
            while (tail.next != null) tail = tail.next;
            tail.next = node;
        }
        size++;
        return null;
        // 作答结束
    }

    @SuppressWarnings("unchecked")
    private void resize() {
        Entry<K, V>[] next = (Entry<K, V>[]) new Entry[table.length * 2];
        for (Entry<K, V> head : table)
            for (Entry<K, V> e = head; e != null; ) {
                Entry<K, V> after = e.next;
                int index = e.hash & (next.length - 1);
                e.next = next[index];
                next[index] = e;
                e = after;
            }
        table = next;
    }

    public V remove(Object key) {
        // 作答开始
        int h = hash(key), bucket = h & (table.length - 1);
        Entry<K, V> previous = null;
        for (Entry<K, V> e = table[bucket]; e != null; e = e.next) {
            if (e.hash == h && Objects.equals(e.key, key)) {
                if (previous == null) table[bucket] = e.next;
                else previous.next = e.next;
                e.next = null;
                size--;
                return e.value;
            }
            previous = e;
        }
        return null;
        // 作答结束
    }

    public record TenantKey(String tenant, String id) {
        public TenantKey {
            Objects.requireNonNull(tenant);
            Objects.requireNonNull(id);
        }
    }
}
