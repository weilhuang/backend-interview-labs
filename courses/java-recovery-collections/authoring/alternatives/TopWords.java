package labs;
import java.util.*;
public final class TopWords {
    public record Count(String word, long count) {}
    private TopWords() {}
    public static List<Count> top(List<String> tokens, int k) {
        Objects.requireNonNull(tokens, "tokens");
        if (k < 0) throw new IllegalArgumentException("negative k");
        Map<String, Long> counts = new TreeMap<>();
        for (String token : tokens) {
            String word = Objects.requireNonNull(token, "token").trim().toLowerCase(Locale.ROOT);
            if (!word.isEmpty()) counts.merge(word, 1L, Long::sum);
        }
        List<Count> result = new ArrayList<>();
        counts.forEach((word, count) -> result.add(new Count(word, count)));
        result.sort(Comparator.comparingLong(Count::count).reversed());
        return new ArrayList<>(result.subList(0, Math.min(k, result.size())));
    }
}
