// 标准实现位于作者占位区；学员填写同一公开接口，题面末尾提供完整答案与解析。
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
