// 标准实现位于作者占位区；学员填写同一公开接口，题面末尾提供完整答案与解析。
package labs;
import java.util.*;
public final class IdParser {
    private IdParser() {}
    public static List<Integer> parse(String input) {
        Objects.requireNonNull(input, "input");
        if (input.isBlank()) return new ArrayList<>();
        Set<Integer> seen = new LinkedHashSet<>();
        for (String token : input.split(",", -1)) {
            String value = token.trim();
            if (value.isEmpty() || !value.chars().allMatch(c -> c >= '0' && c <= '9'))
                throw new IllegalArgumentException("expected decimal ID");
            int id = Integer.parseInt(value);
            if (id <= 0) throw new IllegalArgumentException("ID must be positive");
            seen.add(id);
        }
        return new ArrayList<>(seen);
    }
}
