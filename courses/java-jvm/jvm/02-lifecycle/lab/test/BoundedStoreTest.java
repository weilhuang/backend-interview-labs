import static org.junit.jupiter.api.Assertions.*;

import labs.jvm.*;

import org.junit.jupiter.api.*;

@Timeout(5)
class BoundedStoreTest {
    @Test
    void budgetReplacementAndFailureAtomicity() {
        try (var store = new BoundedStore(4)) {
            store.put("a", new byte[3]);
            store.put("a", new byte[4]);
            assertEquals(4, store.retainedBytes());
            assertThrows(IllegalStateException.class, () -> store.put("b", new byte[1]));
            assertEquals(4, store.retainedBytes());
            assertNull(store.get("b"));
            store.remove("a");
            assertEquals(0, store.retainedBytes());
            store.put("b", new byte[4]);
        }
    }

    @Test
    void copiesAndClose() {
        var s = new BoundedStore(8);
        byte[] input = {1};
        s.put("a", input);
        input[0] = 9;
        assertArrayEquals(new byte[] {1}, s.get("a"), "不能保留调用方可变数组");
        byte[] output = s.get("a");
        output[0] = 8;
        assertEquals(1, s.get("a")[0]);
        s.close();
        s.close();
        assertEquals(0, s.retainedBytes(), "业务强引用计数清零，不断言GC时点");
        assertThrows(IllegalStateException.class, () -> s.get("a"));
        assertThrows(IllegalStateException.class, () -> s.put("a", new byte[0]));
    }

    @Test
    void invalidAndEmpty() {
        assertThrows(IllegalArgumentException.class, () -> new BoundedStore(0));
        assertThrows(IllegalArgumentException.class, () -> new BoundedStore(1048577));
        try (var s = new BoundedStore(1)) {
            assertThrows(NullPointerException.class, () -> s.put("a", null));
            s.remove("不存在");
            s.put("空", new byte[0]);
            assertEquals(0, s.retainedBytes());
        }
    }

    @Test
    void emptyValuesCannotBypassEntryBudget() {
        try (var s = new BoundedStore(1)) {
            for (int i = 0; i < 256; i++) s.put("键" + i, new byte[0]);
            assertThrows(IllegalStateException.class, () -> s.put("多一个", new byte[0]));
            s.put("键0", new byte[1]);
            assertEquals(1, s.retainedBytes());
            assertThrows(IllegalArgumentException.class, () -> s.put("a".repeat(129), new byte[0]));
        }
    }

    @Test
    void referenceQueueDoesNotNeedGc() {
        var queue = new java.lang.ref.ReferenceQueue<Object>();
        Object strong = new Object();
        var weak = new java.lang.ref.WeakReference<>(strong, queue);
        var soft = new java.lang.ref.SoftReference<>(strong);
        var phantom = new java.lang.ref.PhantomReference<>(strong, queue);
        assertSame(strong, weak.get());
        assertSame(strong, soft.get());
        assertNull(phantom.get());
        assertTrue(weak.enqueue(), "显式入队验证API，不能冒充GC回收证据");
        assertSame(weak, queue.poll());
        java.lang.ref.Reference.reachabilityFence(strong);
    }

    @Test
    void primaryExceptionAndSuppressedClose() {
        class Resource implements AutoCloseable {
            public void close() {
                throw new IllegalStateException("关闭失败");
            }
        }
        var e =
                assertThrows(
                        IllegalArgumentException.class,
                        () -> {
                            try (var r = new Resource()) {
                                throw new IllegalArgumentException("业务失败");
                            }
                        });
        assertEquals("业务失败", e.getMessage());
        assertEquals("关闭失败", e.getSuppressed()[0].getMessage());
    }
}
