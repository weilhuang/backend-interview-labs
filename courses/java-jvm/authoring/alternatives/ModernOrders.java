package labs.jvm;

import java.util.*;
import java.util.concurrent.*;

public final class ModernOrders {
    public record Money(long cents) {
        public Money {
            if (cents < 0) throw new IllegalArgumentException("金额非负");
        }
    }

    public sealed interface Event permits Paid, Refund, Cancelled {}

    public record Paid(String id, Money amount) implements Event {
        public Paid {
            Objects.requireNonNull(id);
            Objects.requireNonNull(amount);
        }
    }

    public record Refund(String id, Money amount) implements Event {
        public Refund {
            Objects.requireNonNull(id);
            Objects.requireNonNull(amount);
        }
    }

    public record Cancelled(String id) implements Event {
        public Cancelled {
            Objects.requireNonNull(id);
        }
    }

    private ModernOrders() {}

    public static long delta(Event event) {
        // 作答开始
        return switch (Objects.requireNonNull(event)) {
            case Paid(var id, Money(var cents)) -> cents;
            case Refund(var id, Money(var cents)) -> -cents;
            case Cancelled(var id) -> 0L;
        };
        // 作答结束
    }

    public static <T> List<T> newest(SequencedCollection<T> input, int count) {
        // 作答开始
        Objects.requireNonNull(input);
        if (count < 0) throw new IllegalArgumentException("数量不能为负");
        List<T> result = new ArrayList<>();
        for (T value : input.reversed()) {
            if (result.size() == count) break;
            result.add(value);
        }
        return Collections.unmodifiableList(result);
        // 作答结束
    }

    public static List<Integer> boundedSquares(List<Integer> input, int maximum) throws Exception {
        return boundedMap(input, maximum, n -> Math.multiplyExact(n, n));
    }

    public static List<Integer> boundedMap(
            List<Integer> input, int maximum, java.util.function.IntUnaryOperator operation)
            throws Exception {
        // 作答开始
        Objects.requireNonNull(operation);
        Objects.requireNonNull(input);
        if (input.size() > 64 || maximum < 1 || maximum > 8)
            throw new IllegalArgumentException("超出任务预算");
        for (Integer n : input) Objects.requireNonNull(n);
        Semaphore permits = new Semaphore(maximum);
        try (var executor = Executors.newVirtualThreadPerTaskExecutor()) {
            List<Future<Integer>> futures = new ArrayList<>();
            for (int n : input)
                futures.add(
                        executor.submit(
                                () -> {
                                    permits.acquire();
                                    try {
                                        return operation.applyAsInt(n);
                                    } finally {
                                        permits.release();
                                    }
                                }));
            List<Integer> result = new ArrayList<>();
            try {
                for (var f : futures) result.add(f.get(2, TimeUnit.SECONDS));
            } finally {
                for (var f : futures) if (!f.isDone()) f.cancel(true);
            }
            return List.copyOf(result);
        }
        // 作答结束
    }
}
