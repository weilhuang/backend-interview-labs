import static org.junit.jupiter.api.Assertions.*;

import labs.foundation.*;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.Timeout;

import java.util.*;
import java.util.concurrent.*;

@Timeout(5)
class MiniHashMapTest {
    record Collision(int id) {
        public int hashCode() {
            return 7;
        }
    }

    @Test
    void collisionsReplacementResizeAndRemoval() {
        var map = new MiniHashMap<Collision, String>();
        for (int i = 0; i < 100; i++) map.put(new Collision(i), "v" + i);
        assertTrue(map.capacity() > 4);
        assertEquals(100, map.size());
        for (int i = 0; i < 100; i++) assertEquals("v" + i, map.get(new Collision(i)));
        assertEquals("v50", map.put(new Collision(50), "改"));
        assertEquals(100, map.size());
        for (int i = 0; i < 100; i++) assertNotNull(map.remove(new Collision(i)));
        assertEquals(0, map.size());
    }

    @Test
    void nullAndValueKeys() {
        var map = new MiniHashMap<Object, String>();
        map.put(null, null);
        assertTrue(map.containsKey(null));
        assertNull(map.get(null));
        var a = new MiniHashMap.TenantKey(new String("租户"), "A");
        var b = new MiniHashMap.TenantKey(new String("租户"), "A");
        map.put(a, "值");
        assertEquals("值", map.get(b));
        assertEquals("值", map.remove(b));
    }

    @Test
    void mutableKeyCounterexample() {
        class Mutable {
            int value = 1;

            public int hashCode() {
                return value;
            }

            public boolean equals(Object o) {
                return o instanceof Mutable m && m.value == value;
            }
        }
        var key = new Mutable();
        var map = new MiniHashMap<Mutable, String>();
        map.put(key, "初值");
        key.value = 2;
        assertNull(map.get(key), "改变hash后找不到是错误键使用，不要求容器猜测历史键");
        assertEquals(1, map.size());
    }

    @Test
    void fixedSeedDifferential() {
        var actual = new MiniHashMap<Integer, Integer>();
        var expected = new HashMap<Integer, Integer>();
        var random = new Random(104);
        for (int i = 0; i < 1500; i++) {
            Integer key = random.nextInt(8) == 0 ? null : random.nextInt(80);
            switch (random.nextInt(3)) {
                case 0 -> {
                    int value = random.nextInt();
                    assertEquals(expected.put(key, value), actual.put(key, value));
                }
                case 1 -> assertEquals(expected.remove(key), actual.remove(key));
                case 2 -> {
                    assertEquals(expected.get(key), actual.get(key));
                    assertEquals(expected.containsKey(key), actual.containsKey(key));
                }
            }
            assertEquals(expected.size(), actual.size());
        }
    }
}
