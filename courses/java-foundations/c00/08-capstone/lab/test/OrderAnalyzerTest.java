import static org.junit.jupiter.api.Assertions.*;

import labs.foundation.*;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.Timeout;

import java.util.*;
import java.util.concurrent.*;

@Timeout(5)
class OrderAnalyzerTest {
    @org.junit.jupiter.api.io.TempDir java.nio.file.Path directory;

    @Test
    void dedupBeforeFilterAndStableReport() {
        var lines = List.of("B|乙|7|PAID", "A|甲|2|PENDING", "A|甲|99|PAID", "C|乙|3|PAID");
        assertEquals("客户|总分|笔数\n乙|10|2\n", OrderAnalyzer.analyze(lines, Order.Status.PAID));
        assertEquals("客户|总分|笔数\n甲|2|1\n", OrderAnalyzer.analyze(lines, Order.Status.PENDING));
        assertEquals("客户|总分|笔数\n", OrderAnalyzer.analyze(List.of(), Order.Status.PAID));
    }

    @Test
    void overflowIsNotSilentlyWrapped() {
        assertThrows(
                ArithmeticException.class,
                () ->
                        OrderAnalyzer.analyze(
                                List.of("A|甲|9223372036854775807|PAID", "B|甲|1|PAID"),
                                Order.Status.PAID));
    }

    @Test
    void invalidDuplicateStillRejected() {
        assertThrows(
                ParseFailure.class,
                () ->
                        OrderAnalyzer.analyze(
                                List.of("A|甲|1|PAID", "A|甲|bad|PAID"), Order.Status.PAID));
    }

    @Test
    void cliExitAndUtf8() throws Exception {
        var input = directory.resolve("orders.txt");
        java.nio.file.Files.writeString(input, "A|张三|5|PAID\n");
        var bytes = new java.io.ByteArrayOutputStream();
        var errors = new java.io.ByteArrayOutputStream();
        try (var out =
                        new java.io.PrintStream(
                                bytes, true, java.nio.charset.StandardCharsets.UTF_8);
                var err =
                        new java.io.PrintStream(
                                errors, true, java.nio.charset.StandardCharsets.UTF_8)) {
            assertEquals(0, OrderAnalyzer.run(new String[] {input.toString(), "PAID"}, out, err));
            assertEquals(
                    "客户|总分|笔数\n张三|5|1\n", bytes.toString(java.nio.charset.StandardCharsets.UTF_8));
            assertEquals(2, OrderAnalyzer.run(new String[] {}, out, err));
            assertEquals(
                    3,
                    OrderAnalyzer.run(
                            new String[] {directory.resolve("missing").toString(), "PAID"},
                            out,
                            err));
            assertEquals(
                    4, OrderAnalyzer.run(new String[] {input.toString(), "UNKNOWN"}, out, err));
        }
    }
}
