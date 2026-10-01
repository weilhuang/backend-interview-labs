package labs.capstone;

import static labs.capstone.Model.*;

import static org.junit.jupiter.api.Assertions.*;

import org.junit.jupiter.api.Test;

class ContractTest {
    @Test
    void 数量和身份边界必须由服务端守住() {
        for (int n : new int[] {0, -1, 101, Integer.MAX_VALUE})
            assertThrows(
                    IllegalArgumentException.class,
                    () -> OrderRules.validate(new Command("x", "book", n)));
        assertDoesNotThrow(() -> OrderRules.validate(new Command("X_1-2", "book", 100)));
    }

    @Test
    void 空白控制字符与过长请求被拒绝() {
        for (String id : new String[] {"", "a ", "a/b", "换行\n", "x".repeat(65)})
            assertThrows(
                    IllegalArgumentException.class,
                    () -> OrderRules.validate(new Command(id, "book", 1)));
        assertThrows(NullPointerException.class, () -> OrderRules.validate(null));
    }

    @Test
    void 重复请求保留已经取消状态() {
        Order cancelled = new Order("A", "book", 2, "CANCELLED", 2);
        assertSame(cancelled, OrderRules.sameRequest(cancelled, new Command("A", "book", 2)));
    }

    @Test
    void 同一身份变更参数是冲突() {
        Order order = new Order("A", "book", 2, "RESERVED", 1);
        assertThrows(
                Conflict.class, () -> OrderRules.sameRequest(order, new Command("A", "pen", 2)));
        assertThrows(
                Conflict.class, () -> OrderRules.sameRequest(order, new Command("A", "book", 3)));
    }

    @Test
    void 取消是单向而且幂等的() {
        assertTrue(OrderRules.mayCancel("RESERVED"));
        assertFalse(OrderRules.mayCancel("CANCELLED"));
        assertThrows(Conflict.class, () -> OrderRules.mayCancel("PAID"));
    }

    @Test
    void 事件的身份状态与版本必须对应() {
        OrderRules.validateEvent(new Event("Case:1", "Case", "book", 1, "RESERVED", 1));
        assertThrows(
                IllegalArgumentException.class,
                () ->
                        OrderRules.validateEvent(
                                new Event("Case:2", "Case", "book", 1, "RESERVED", 2)));
        assertThrows(
                IllegalArgumentException.class,
                () ->
                        OrderRules.validateEvent(
                                new Event("case:1", "Case", "book", 1, "RESERVED", 1)));
    }
}
