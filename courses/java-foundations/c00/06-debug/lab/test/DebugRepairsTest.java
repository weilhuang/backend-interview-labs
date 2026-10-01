import static org.junit.jupiter.api.Assertions.*;

import labs.foundation.*;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.Timeout;

import java.util.*;
import java.util.concurrent.*;

@Timeout(5)
class DebugRepairsTest {
    @Test
    void halfOpenBoundary() {
        assertEquals(List.of("b"), DebugRepairs.slice(List.of("a", "b"), 1, 2));
        assertEquals(List.of(), DebugRepairs.slice(List.of("a"), 1, 1));
        assertThrows(IndexOutOfBoundsException.class, () -> DebugRepairs.slice(List.of(1), 0, 2));
    }

    @Test
    void nestedAlias() {
        var inner = new ArrayList<>(List.of("旧"));
        var outer = new ArrayList<List<String>>(List.of(inner));
        var result = DebugRepairs.snapshot(outer);
        inner.set(0, "新");
        outer.clear();
        assertEquals(List.of(List.of("旧")), result);
        assertThrows(UnsupportedOperationException.class, () -> result.getFirst().add("漏写"));
    }

    @Test
    void primaryAndSuppressed() {
        var primary = new IllegalArgumentException("业务错误");
        var closing = new IllegalStateException("关闭错误");
        var e =
                assertThrows(
                        IllegalArgumentException.class,
                        () ->
                                DebugRepairs.withResource(
                                        () -> {
                                            throw closing;
                                        },
                                        () -> {
                                            throw primary;
                                        }));
        assertSame(primary, e);
        assertSame(closing, e.getSuppressed()[0]);
    }
}
