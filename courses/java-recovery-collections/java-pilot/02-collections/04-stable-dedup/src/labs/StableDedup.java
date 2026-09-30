package labs;
import java.util.*;
public final class StableDedup {
    private StableDedup() {}
    public static <T> List<T> distinct(List<T> input) {
        Objects.requireNonNull(input, "input");
        return new ArrayList<>(new LinkedHashSet<>(input));
    }
}
