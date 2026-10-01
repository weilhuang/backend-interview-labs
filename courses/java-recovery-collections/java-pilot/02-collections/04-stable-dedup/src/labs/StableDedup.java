// 标准实现位于作者占位区；学员填写同一公开接口，题面末尾提供完整答案与解析。
package labs;
import java.util.*;
public final class StableDedup {
    private StableDedup() {}
    public static <T> List<T> distinct(List<T> input) {
        Objects.requireNonNull(input, "input");
        return new ArrayList<>(new LinkedHashSet<>(input));
    }
}
