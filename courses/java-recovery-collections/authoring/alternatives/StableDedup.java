package labs;
import java.util.*;
public final class StableDedup {
    private StableDedup() {}
    public static <T> List<T> distinct(List<T> input) {
        Objects.requireNonNull(input, "input");
        Set<T> seen = new HashSet<>();
        List<T> result = new ArrayList<>();
        for (T value : input) if (seen.add(value)) result.add(value);
        return result;
    }
}
