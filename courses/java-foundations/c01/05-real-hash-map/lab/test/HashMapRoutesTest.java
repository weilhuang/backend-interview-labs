import static org.junit.jupiter.api.Assertions.*;

import labs.foundation.*;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.Timeout;

import java.util.*;
import java.util.concurrent.*;

@Timeout(5)
class HashMapRoutesTest {
    @Test
    void collisionsAndResizeKeepPublicContract() {
        var map = HashMapRoutes.collisionMap(12);
        assertEquals(12, map.size());
        assertTrue(HashMapRoutes.verifyLookups(map, 12));
        HashMapRoutes.growForSplit(map);
        assertEquals(60, map.size());
        assertTrue(HashMapRoutes.verifyLookups(map, 12));
        for (int i = 0; i < 12; i++)
            assertEquals(i, map.remove(new HashMapRoutes.Key(i, (i % 2) * 64)));
        assertEquals(48, map.size());
    }

    @Test
    void sameHashDoesNotMeanEqual() {
        var a = new HashMapRoutes.Key(1, 0);
        var b = new HashMapRoutes.Key(2, 0);
        assertEquals(a.hashCode(), b.hashCode());
        assertNotEquals(a, b);
        assertEquals(a, new HashMapRoutes.Key(1, 0));
    }

    @Test
    void emptyAndBounded() {
        assertTrue(HashMapRoutes.collisionMap(0).isEmpty());
        assertThrows(IllegalArgumentException.class, () -> HashMapRoutes.collisionMap(-1));
        assertThrows(IllegalArgumentException.class, () -> HashMapRoutes.collisionMap(257));
    }
}
