package labs;
import java.util.*;
public final class SafeRemoval {
    private SafeRemoval() {}
    public static int removeNegative(List<Integer> values) {
        Objects.requireNonNull(values, "values");
        for (Integer value : values) Objects.requireNonNull(value, "element");
        int removed = 0;
        ListIterator<Integer> it = values.listIterator();
        while (it.hasNext()) {
            if (it.next() < 0) {
                it.remove();
                removed++;
            }
        }
        return removed;
    }
}
