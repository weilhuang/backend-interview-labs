// 标准实现位于作者占位区；学员填写同一公开接口，题面末尾提供完整答案与解析。
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
