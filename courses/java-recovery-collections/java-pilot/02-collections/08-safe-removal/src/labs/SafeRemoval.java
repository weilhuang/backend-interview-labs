package labs;
import java.util.*;
public final class SafeRemoval {
    private SafeRemoval() {}
    public static int removeNegative(List<Integer> values) {
        Objects.requireNonNull(values, "values");
        for (Integer value : values) Objects.requireNonNull(value, "element");
        int removed = 0;
        Iterator<Integer> it = values.iterator();
        while (it.hasNext()) {
            if (it.next() < 0) {
                it.remove();
                removed++;
            }
        }
        return removed;
    }
}
