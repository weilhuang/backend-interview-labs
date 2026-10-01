import static org.junit.jupiter.api.Assertions.*;

import labs.*;

import org.junit.jupiter.api.*;

import java.sql.*;
import java.util.*;

class QueryContractTest {
    @Test
    void limitsAreBounded() {
        assertThrows(IllegalArgumentException.class, () -> QueryLab.validateLimit(0));
        assertThrows(IllegalArgumentException.class, () -> QueryLab.validateLimit(101));
        QueryLab.validateLimit(100);
    }

    @Test
    void cursorNeedsTimestamp() {
        assertThrows(NullPointerException.class, () -> new QueryLab.Cursor(null, 1));
    }

    @Test
    void dayBoundaryMustBeUtcMidnight() {
        assertThrows(
                IllegalArgumentException.class,
                () -> QueryLab.onUtcDay(null, 7, java.time.Instant.parse("2025-01-01T12:00:00Z")));
        assertThrows(IllegalArgumentException.class, () -> QueryLab.onUtcDay(null, 7, null));
    }
}
