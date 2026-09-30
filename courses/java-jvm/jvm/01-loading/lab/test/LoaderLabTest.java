import static org.junit.jupiter.api.Assertions.*;

import labs.jvm.*;

import org.junit.jupiter.api.*;

@Timeout(5)
class LoaderLabTest {
    private byte[] bytes() throws Exception {
        try (var in = LoaderLab.class.getResourceAsStream("/labs/jvm/LoadTarget.class")) {
            return in.readAllBytes();
        }
    }

    @Test
    void namespacesAndDelegation() throws Exception {
        var parent = LoaderLab.class.getClassLoader();
        var first = LoaderLab.isolated("labs.jvm.LoadTarget", bytes(), parent);
        var second = LoaderLab.isolated("labs.jvm.LoadTarget", bytes(), parent);
        var a = first.loadClass("labs.jvm.LoadTarget");
        assertSame(a, first.loadClass("labs.jvm.LoadTarget"), "同一加载器必须复用已定义类");
        assertNotSame(a, second.loadClass("labs.jvm.LoadTarget"), "同名类在不同定义加载器中不同");
        assertNotSame(a, LoadTarget.class, "指定目标须在子命名空间定义");
        assertSame(String.class, first.loadClass("java.lang.String"), "平台类必须委派");
        Object value = a.getConstructor().newInstance();
        assertFalse(LoadTarget.class.isInstance(value), "同名字不意味着赋值兼容");
    }

    @Test
    void defensiveCopyAndInvalidInput() throws Exception {
        byte[] data = bytes();
        var loader = LoaderLab.isolated("labs.jvm.LoadTarget", data, getClass().getClassLoader());
        java.util.Arrays.fill(data, (byte) 0);
        assertEquals("labs.jvm.LoadTarget", loader.loadClass("labs.jvm.LoadTarget").getName());
        assertThrows(
                IllegalArgumentException.class,
                () -> LoaderLab.isolated("java.lang.String", new byte[0], null));
        assertThrows(NullPointerException.class, () -> LoaderLab.isolated(null, new byte[0], null));
    }

    @Test
    void bytecodeBehavior() {
        assertEquals(6, LoaderLab.twice(3));
        assertEquals(-4, LoaderLab.twice(-2));
    }

    @Test
    void initializationIsSeparate() throws Exception {
        InitTrace.events.clear();
        assertEquals(7, InitChild.CONSTANT, "编译期常量不触发初始化");
        Class.forName("labs.jvm.InitChild", false, getClass().getClassLoader());
        assertTrue(InitTrace.events.isEmpty(), "装入但不初始化");
        Class.forName("labs.jvm.InitChild", true, getClass().getClassLoader());
        assertEquals(java.util.List.of("父类", "子类"), InitTrace.events);
        Class.forName("labs.jvm.InitChild", true, getClass().getClassLoader());
        assertEquals(2, InitTrace.events.size(), "初始化只执行一次");
    }
}
