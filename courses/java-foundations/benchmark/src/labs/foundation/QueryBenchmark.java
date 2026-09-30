package labs.foundation;

import org.openjdk.jmh.annotations.*;

import java.util.*;
import java.util.concurrent.TimeUnit;

@State(Scope.Thread)
@BenchmarkMode(Mode.AverageTime)
@OutputTimeUnit(TimeUnit.MICROSECONDS)
public class QueryBenchmark {
    @Param({"128", "4096"})
    public int size;

    private List<Order> orders;
    private IndexedOrders index;
    private int cursor;

    @Setup(Level.Trial)
    public void setup() {
        var random = new Random(108);
        var data = new ArrayList<Order>();
        for (int i = 0; i < size; i++) {
            data.add(new Order("id" + i, "客" + (i % 64), random.nextInt(100), Order.Status.PAID));
        }
        orders = List.copyOf(data);
        index = new IndexedOrders(orders, 16);
        index.query("客0", 0);
        cursor = 0;
    }

    @Benchmark
    public List<Order> scanRotating() {
        int key = cursor;
        cursor = (cursor + 1) % 6400;
        String customer = "客" + (key % 64);
        long minimum = key % 100;
        return orders.stream()
                .filter(o -> o.customer().equals(customer) && o.cents() >= minimum)
                .sorted(Comparator.comparing(Order::id))
                .toList();
    }

    @Benchmark
    public List<Order> indexedRotating() {
        int key = cursor;
        cursor = (cursor + 1) % 6400;
        return index.query("客" + (key % 64), key % 100);
    }

    @Benchmark
    public List<Order> cachedHotKey() {
        return index.query("客0", 0);
    }
}
