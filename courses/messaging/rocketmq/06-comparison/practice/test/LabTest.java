import static org.junit.jupiter.api.Assertions.*;

import labs.messaging.*;

import org.junit.jupiter.api.Test;

class LabTest {
    @Test
    void 相同业务契约重复与溢出边界() {
        Lab model = new Lab();
        Event e = new Event("e1", "o1", 1, 100);
        assertTrue(model.accept(e));
        assertFalse(model.accept(e));
        assertEquals(100, model.total());
        Lab large = new Lab();
        large.accept(new Event("max", "o1", 1, Long.MAX_VALUE));
        assertThrows(ArithmeticException.class, () -> large.accept(new Event("over", "o2", 1, 1)));
        assertEquals(Long.MAX_VALUE, large.total());
    }
}
