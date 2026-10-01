import static org.junit.jupiter.api.Assertions.*;

import labs.foundation.*;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.Timeout;

import java.util.*;
import java.util.concurrent.*;

@Timeout(5)
class LinkedAlgorithmsTest {
    @Test
    void endpointsAndNull() {
        var list = new LinkedAlgorithms<String>();
        assertTrue(list.invariants());
        assertThrows(NoSuchElementException.class, list::removeFirst);
        list.addFirst(null);
        assertNull(list.removeFirst());
        assertTrue(list.invariants());
        list.addLast("a");
        list.addFirst("b");
        list.addLast("c");
        assertEquals("a", list.get(1));
        assertEquals("b", list.removeFirst());
        assertTrue(list.invariants());
        assertEquals("c", list.removeLast());
        assertEquals("a", list.removeLast());
        assertTrue(list.invariants());
    }

    @Test
    void dequeDifferential() {
        var a = new LinkedAlgorithms<Integer>();
        var b = new ArrayDeque<Integer>();
        var random = new Random(103);
        for (int i = 0; i < 500; i++) {
            int operation = b.isEmpty() ? 0 : random.nextInt(4);
            switch (operation) {
                case 0 -> {
                    a.addFirst(i);
                    b.addFirst(i);
                }
                case 1 -> {
                    a.addLast(i);
                    b.addLast(i);
                }
                case 2 -> assertEquals(b.removeFirst(), a.removeFirst());
                case 3 -> assertEquals(b.removeLast(), a.removeLast());
            }
            assertEquals(b.size(), a.size());
            assertTrue(a.invariants());
            int j = 0;
            for (int value : b) assertEquals(value, a.get(j++));
        }
    }

    @Test
    void bfsCyclesAndMonotonicQueue() {
        assertEquals(
                List.of(1, 2, 3, 4),
                LinkedAlgorithms.bfs(Map.of(1, List.of(2, 3), 2, List.of(1, 4), 3, List.of(4)), 1));
        assertEquals(
                List.of(3, 3, 5, 5, 6, 7),
                LinkedAlgorithms.windowMaximum(new int[] {1, 3, -1, -3, 5, 3, 6, 7}, 3));
        assertEquals(List.of(), LinkedAlgorithms.windowMaximum(new int[] {}, 0));
        assertThrows(
                IllegalArgumentException.class,
                () -> LinkedAlgorithms.windowMaximum(new int[] {1}, 0));
    }

    @Test
    void windowsAgainstBruteForce() {
        var random = new Random(104);
        for (int sample = 0; sample < 80; sample++) {
            int[] values = random.ints(20, -20, 21).toArray();
            int k = 1 + random.nextInt(20);
            List<Integer> expected = new ArrayList<>();
            for (int i = 0; i + k <= values.length; i++) {
                int maximum = Integer.MIN_VALUE;
                for (int j = i; j < i + k; j++) maximum = Math.max(maximum, values[j]);
                expected.add(maximum);
            }
            assertEquals(expected, LinkedAlgorithms.windowMaximum(values, k));
        }
    }
}
