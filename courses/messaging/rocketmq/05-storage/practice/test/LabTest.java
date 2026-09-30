import static org.junit.jupiter.api.Assertions.*;

import labs.messaging.*;

import org.junit.jupiter.api.Test;

import java.util.List;
import java.util.Set;

class LabTest {
    @Test
    void 模型不能混淆刷盘和复制() {
        assertTrue(Lab.risk(new Lab.Durability(false, 2)).contains("未刷盘"));
        assertTrue(Lab.risk(new Lab.Durability(true, 1)).contains("单机"));
        assertTrue(Lab.risk(new Lab.Durability(true, 2)).contains("故障域"));
        assertThrows(IllegalArgumentException.class, () -> Lab.risk(new Lab.Durability(true, 0)));
    }

    @Test
    void 重复恢复记录不能掩盖缺失消息() {
        Event e1 = new Event("e1", "o1", 1, 100);
        assertEquals(List.of("e2"), Lab.missing(Set.of("e1", "e2"), List.of(e1, e1)));
        assertTrue(Lab.missing(Set.of("e1"), List.of(e1)).isEmpty());
        assertEquals(List.of("a", "b"), Lab.missing(Set.of("b", "a"), List.of()));
    }
}
