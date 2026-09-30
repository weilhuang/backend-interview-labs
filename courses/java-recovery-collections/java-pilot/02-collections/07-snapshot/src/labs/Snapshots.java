package labs;
import java.util.*;
public final class Snapshots {
    private Snapshots() {}
    public static <T> List<T> range(List<T> input, int from, int to) {
        Objects.requireNonNull(input, "input");
        Objects.checkFromToIndex(from, to, input.size());
        return List.copyOf(input.subList(from, to));
    }
}
