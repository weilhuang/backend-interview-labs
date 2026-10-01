package labs;
import java.util.*;
public final class Snapshots {
    private Snapshots() {}
    public static <T> List<T> range(List<T> input, int from, int to) {
        Objects.requireNonNull(input, "input");
        Objects.checkFromToIndex(from, to, input.size());
        List<T> copy = new ArrayList<>();
        for (T value : input.subList(from, to)) copy.add(Objects.requireNonNull(value));
        return Collections.unmodifiableList(copy);
    }
}
