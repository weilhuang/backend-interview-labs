import static org.junit.jupiter.api.Assertions.*;

import labs.foundation.*;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.Timeout;

import java.util.*;
import java.util.concurrent.*;

@Timeout(5)
class OrderParserTest {
    @Test
    void trimAndEmptyBatch() {
        assertEquals(
                new Order("A", "张三", 0, Order.Status.PAID),
                OrderParser.parse(" A | 张三 | 0 | PAID ", 7));
        assertEquals(List.of(), OrderParser.parseBatch(List.of()));
    }

    @Test
    void preciseErrors() {
        var e = assertThrows(ParseFailure.class, () -> OrderParser.parse("A|甲|x|PAID", 12));
        assertEquals(12, e.line());
        assertEquals("cents", e.field());
        assertTrue(e.getMessage().contains("第12行"));
        assertEquals(
                "status",
                assertThrows(ParseFailure.class, () -> OrderParser.parse("A|甲|1|", 1)).field());
        assertThrows(ParseFailure.class, () -> OrderParser.parse("A|甲|1|PAID|", 1));
        assertThrows(ParseFailure.class, () -> OrderParser.parse("A||1|PAID", 1));
        assertThrows(ParseFailure.class, () -> OrderParser.parse("A|甲|-1|PAID", 1));
        assertThrows(
                ParseFailure.class, () -> OrderParser.parse("A|甲|9223372036854775808|PAID", 1));
    }

    @Test
    void duplicateAndImmutable() {
        var e =
                assertThrows(
                        ParseFailure.class,
                        () -> OrderParser.parseBatch(List.of("A|甲|1|PAID", "A|乙|2|PAID")));
        assertEquals(2, e.line());
        var list = OrderParser.parseBatch(List.of("A|甲|1|PAID"));
        assertThrows(UnsupportedOperationException.class, () -> list.clear());
    }
}
