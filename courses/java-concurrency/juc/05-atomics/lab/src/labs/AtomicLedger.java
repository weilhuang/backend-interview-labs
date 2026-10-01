package labs;

import java.util.*;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.atomic.*;

public final class AtomicLedger {
    private final AtomicInteger balance;

    public AtomicLedger(int initial) {
        if (initial < 0) throw new IllegalArgumentException("余额不能为负");
        balance = new AtomicInteger(initial);
    }

    public boolean reserve(int amount) {
        // 答案开始：CAS预留
        if (amount <= 0) throw new IllegalArgumentException("预留数量必须为正");
        for (; ; ) {
            int old = balance.get();
            if (old < amount) return false;
            if (balance.compareAndSet(old, old - amount)) return true;
        }
        // 答案结束：CAS预留
    }

    public void add(int amount) {
        if (amount <= 0) throw new IllegalArgumentException("添加数量必须为正");
        for (; ; ) {
            int old = balance.get();
            int next = Math.addExact(old, amount);
            if (balance.compareAndSet(old, next)) return;
        }
    }

    public int balance() {
        return balance.get();
    }

    public static final class VersionedSlot {
        public record Snapshot(String value, int version) {}

        private final AtomicStampedReference<String> value;

        public VersionedSlot(String initial) {
            value = new AtomicStampedReference<>(Objects.requireNonNull(initial), 0);
        }

        public Snapshot snapshot() {
            int[] stamp = {0};
            String ref = value.get(stamp);
            return new Snapshot(ref, stamp[0]);
        }

        public boolean replace(Snapshot expected, String next) {
            // 答案开始：防止ABA
            Objects.requireNonNull(expected);
            Objects.requireNonNull(next);
            return value.compareAndSet(
                    expected.value(),
                    next,
                    expected.version(),
                    Math.incrementExact(expected.version()));
            // 答案结束：防止ABA
        }
    }

    public static final class Counters {
        private final ConcurrentHashMap<String, LongAdder> counts = new ConcurrentHashMap<>();

        public void increment(String key) {
            // 答案开始：并发计数
            counts.computeIfAbsent(Objects.requireNonNull(key), ignored -> new LongAdder())
                    .increment();
            // 答案结束：并发计数
        }

        public long count(String key) {
            var counter = counts.get(Objects.requireNonNull(key));
            return counter == null ? 0 : counter.sum();
        }

        public Map<String, Long> snapshot() {
            var copy = new TreeMap<String, Long>();
            counts.forEach((key, counter) -> copy.put(key, counter.sum()));
            return Collections.unmodifiableMap(copy);
        }
    }
}
