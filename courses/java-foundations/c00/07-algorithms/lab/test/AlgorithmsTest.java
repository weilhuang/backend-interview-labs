import static org.junit.jupiter.api.Assertions.*;

import labs.foundation.*;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.Timeout;

import java.util.*;
import java.util.concurrent.*;

@Timeout(5)
class AlgorithmsTest {
    @Test
    void countsStackAndTree() {
        assertEquals(Map.of("a", 2, "b", 1), Algorithms.count(List.of("A", "a", "B")));
        assertTrue(Algorithms.balanced("(())()"));
        assertFalse(Algorithms.balanced(")("));
        assertFalse(Algorithms.balanced("("));
        assertThrows(IllegalArgumentException.class, () -> Algorithms.balanced("x"));
        assertEquals(
                List.of(1, 2, 3),
                Algorithms.breadthFirst(
                        new Algorithms.Node(
                                1,
                                new Algorithms.Node(2, null, null),
                                new Algorithms.Node(3, null, null))));
        assertEquals(List.of(), Algorithms.breadthFirst(null));
    }

    @Test
    void fixedBoundaryCases() {
        assertTrue(
                Algorithms.twoSumSorted(
                        new int[] {Integer.MAX_VALUE, Integer.MAX_VALUE}, 4294967294L));
        assertFalse(Algorithms.twoSumSorted(new int[] {1}, 2));
        assertEquals(3, Algorithms.longestAtMostTwo("eceba"));
        assertEquals(4, Algorithms.longestAtMostTwo("😀😀甲甲乙"));
        assertEquals(0, Algorithms.longestAtMostTwo(""));
        assertEquals(1, Algorithms.lowerBound(new int[] {1, 2, 2, 3}, 2));
        assertEquals(4, Algorithms.lowerBound(new int[] {1, 2, 2, 3}, 4));
        assertEquals(0, Algorithms.lowerBound(new int[0], 7));
        assertEquals(2, Algorithms.minimumCoins(6, new int[] {1, 3, 4}));
        assertEquals(-1, Algorithms.minimumCoins(3, new int[] {2}));
        assertEquals(0, Algorithms.minimumCoins(0, new int[] {}));
        assertThrows(
                IllegalArgumentException.class, () -> Algorithms.minimumCoins(1, new int[] {0}));
    }

    @Test
    void fixedSeedAgainstBruteForce() {
        Random random = new Random(700);
        for (int sample = 0; sample < 100; sample++) {
            int[] a = random.ints(random.nextInt(15), -8, 9).sorted().toArray();
            int target = random.nextInt(20) - 10;
            boolean found = false;
            for (int i = 0; i < a.length; i++)
                for (int j = i + 1; j < a.length; j++) found |= (long) a[i] + a[j] == target;
            assertEquals(found, Algorithms.twoSumSorted(a, target));
            int index = 0;
            while (index < a.length && a[index] < target) index++;
            assertEquals(index, Algorithms.lowerBound(a, target));
            String text =
                    random.ints(10, 0, 4)
                            .collect(
                                    StringBuilder::new,
                                    (b, n) -> b.append((char) ('a' + n)),
                                    StringBuilder::append)
                            .toString();
            int best = 0;
            for (int i = 0; i < text.length(); i++)
                for (int j = i; j < text.length(); j++)
                    if (text.substring(i, j + 1).chars().distinct().count() <= 2)
                        best = Math.max(best, j - i + 1);
            assertEquals(best, Algorithms.longestAtMostTwo(text));
        }
    }

    @Test
    void coinsAgainstBfsOracle() {
        for (int amount = 0; amount < 35; amount++) {
            int[] coins = {2, 5, 7};
            int[] distance = new int[amount + 1];
            Arrays.fill(distance, -1);
            distance[0] = 0;
            Deque<Integer> queue = new ArrayDeque<>();
            queue.add(0);
            while (!queue.isEmpty()) {
                int value = queue.remove();
                for (int coin : coins)
                    if (value + coin <= amount && distance[value + coin] < 0) {
                        distance[value + coin] = distance[value] + 1;
                        queue.add(value + coin);
                    }
            }
            assertEquals(distance[amount], Algorithms.minimumCoins(amount, coins));
        }
    }
}
