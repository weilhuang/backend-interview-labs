import static org.junit.jupiter.api.Assertions.*;

import labs.foundation.*;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.Timeout;

import java.util.*;
import java.util.concurrent.*;

@Timeout(5)
class CollectionViewsTest {
    @Test
    void businessCollections() {
        var a = new Order("A", "甲", 1, Order.Status.PAID);
        var b = new Order("B", "乙", 2, Order.Status.PAID);
        var values = List.of(b, a, b);
        assertEquals(List.of("B", "A"), CollectionViews.stableIds(values));
        assertEquals(List.of("B", "A", "B"), CollectionViews.dispatch(values));
        assertEquals(2, CollectionViews.firstById(values).size());
    }

    @Test
    void snapshotAndNull() {
        var values = new ArrayList<>(Arrays.asList("a", null, "c"));
        var snap = CollectionViews.snapshot(values, 0, 2);
        values.clear();
        assertEquals(Arrays.asList("a", null), snap);
        assertThrows(UnsupportedOperationException.class, () -> snap.add("x"));
        assertEquals(List.of(), CollectionViews.snapshot(List.of(1), 1, 1));
        assertThrows(
                IndexOutOfBoundsException.class, () -> CollectionViews.snapshot(List.of(), 0, 1));
    }

    @Test
    void viewMutabilityAndShallowMeaning() {
        String[] array = {"a", "b"};
        List<String> fixed = Arrays.asList(array);
        fixed.set(0, "x");
        assertEquals("x", array[0]);
        assertThrows(UnsupportedOperationException.class, () -> fixed.add("c"));
        assertThrows(NullPointerException.class, () -> List.of("x", null));
        var source = new ArrayList<>(List.of("a", "b"));
        var view = Collections.unmodifiableList(source);
        source.set(0, "新");
        assertEquals("新", view.get(0));
        source.subList(0, 1).clear();
        assertEquals(List.of("b"), source);
        var mutable = new StringBuilder("a");
        var shallow = CollectionViews.snapshot(List.of(mutable), 0, 1);
        mutable.append('b');
        assertEquals("ab", shallow.getFirst().toString());
    }
}
