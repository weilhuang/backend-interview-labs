import static org.junit.jupiter.api.Assertions.*;

import labs.foundation.*;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.Timeout;

import java.util.*;
import java.util.concurrent.*;

@Timeout(5)
class MiniArrayListTest {
    @Test
    void genericMutationAndReferences() {
        var list = new MiniArrayList<String>();
        list.add("a");
        list.add(null);
        list.add("c");
        assertEquals(null, list.set(1, "b"));
        assertEquals("b", list.remove(1));
        assertEquals(List.of("a", "c"), list.snapshot());
        assertTrue(list.unusedSlotsCleared(), "删除后闲置槽必须清除过期引用");
        assertEquals("c", list.remove(1));
        assertEquals("a", list.remove(0));
        assertEquals(0, list.size());
        assertTrue(list.unusedSlotsCleared());
    }

    @Test
    void boundsAndGrowth() {
        var list = new MiniArrayList<Integer>();
        assertThrows(IndexOutOfBoundsException.class, () -> list.get(0));
        for (int i = 0; i < 4096; i++) list.add(i);
        assertEquals(4096, list.size());
        assertThrows(IllegalStateException.class, () -> list.add(7));
        assertThrows(IndexOutOfBoundsException.class, () -> list.set(-1, 0));
    }

    @Test
    void fixedSeedDifferential() {
        var actual = new MiniArrayList<Integer>();
        var expected = new ArrayList<Integer>();
        var random = new Random(102);
        for (int step = 0; step < 1000; step++) {
            if (expected.isEmpty() || random.nextBoolean()) {
                Integer value = random.nextInt(8) == 0 ? null : random.nextInt(100);
                expected.add(value);
                actual.add(value);
            } else {
                int index = random.nextInt(expected.size());
                if (random.nextBoolean())
                    assertEquals(expected.remove(index), actual.remove(index));
                else {
                    int value = random.nextInt(100);
                    assertEquals(expected.set(index, value), actual.set(index, value));
                }
            }
            assertEquals(expected, actual.snapshot());
            assertTrue(actual.unusedSlotsCleared());
        }
    }
}
