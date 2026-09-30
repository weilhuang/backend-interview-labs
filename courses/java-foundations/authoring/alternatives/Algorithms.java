package labs.foundation;

import java.util.*;

public final class Algorithms {
    private Algorithms() {}

    public static Map<String, Integer> count(List<String> words) {
        Map<String, Integer> result = new TreeMap<>();
        for (String word : words)
            result.merge(Objects.requireNonNull(word).toLowerCase(Locale.ROOT), 1, Math::addExact);
        return result;
    }

    public static boolean twoSumSorted(int[] a, long target) {
        // 作答开始
        int left = 0, right = a.length - 1;
        while (left < right) {
            long sum = (long) a[left] + a[right];
            if (sum == target) return true;
            if (sum < target) left++;
            else right--;
        }
        return false;
        // 作答结束
    }

    public static int longestAtMostTwo(String text) {
        // 作答开始
        int[] points = text.codePoints().toArray();
        Map<Integer, Integer> counts = new HashMap<>();
        int left = 0, best = 0;
        for (int right = 0; right < points.length; right++) {
            counts.merge(points[right], 1, Integer::sum);
            while (counts.size() > 2) {
                int p = points[left++];
                int remaining = counts.get(p) - 1;
                if (remaining == 0) counts.remove(p);
                else counts.put(p, remaining);
            }
            best = Math.max(best, right - left + 1);
        }
        return best;
        // 作答结束
    }

    public static int lowerBound(int[] sorted, int key) {
        // 作答开始
        int left = 0, right = sorted.length;
        while (left < right) {
            int mid = (left + right) >>> 1;
            if (sorted[mid] < key) left = mid + 1;
            else right = mid;
        }
        return left;
        // 作答结束
    }

    public static boolean balanced(String text) {
        Deque<Character> stack = new ArrayDeque<>();
        for (char c : text.toCharArray()) {
            if (c == '(') stack.push(c);
            else if (c == ')') {
                if (stack.isEmpty()) return false;
                stack.pop();
            } else throw new IllegalArgumentException("仅允许圆括号");
        }
        return stack.isEmpty();
    }

    public record Node(int value, Node left, Node right) {}

    public static List<Integer> breadthFirst(Node root) {
        if (root == null) return List.of();
        List<Integer> result = new ArrayList<>();
        Deque<Node> queue = new ArrayDeque<>();
        queue.add(root);
        while (!queue.isEmpty()) {
            Node node = queue.remove();
            result.add(node.value());
            if (result.size() > 10000) throw new IllegalArgumentException("树超过10000节点");
            if (node.left() != null) queue.add(node.left());
            if (node.right() != null) queue.add(node.right());
        }
        return List.copyOf(result);
    }

    public static int minimumCoins(int amount, int[] coins) {
        // 作答开始
        if (amount < 0 || amount > 10000) throw new IllegalArgumentException("金额须为0至10000");
        for (int coin : coins) if (coin <= 0) throw new IllegalArgumentException("币值必须为正");
        int[] dp = new int[amount + 1];
        Arrays.fill(dp, amount + 1);
        dp[0] = 0;
        for (int value = 1; value <= amount; value++)
            for (int coin : coins)
                if (coin <= value) dp[value] = Math.min(dp[value], dp[value - coin] + 1);
        return dp[amount] > amount ? -1 : dp[amount];
        // 作答结束
    }
}
