import static org.junit.jupiter.api.Assertions.*;

import labs.*;

import org.junit.jupiter.api.*;

import java.sql.*;
import java.util.*;

@Tag("integration")
class QueryDatabaseTest {
    @BeforeEach
    void reset() throws Exception {
        MySqlFixture.reset();
    }

    @Test
    void equalTimestampUsesTieBreaker() throws Exception {
        try (Connection c = MySqlFixture.open()) {
            var cursor = new QueryLab.Cursor(java.time.Instant.parse("2025-01-01T00:00:00Z"), 1);
            assertEquals(List.of(2L), QueryLab.after(c, 7, cursor, 1));
            assertEquals(List.of(2L, 3L), QueryLab.after(c, 7, cursor, 100));
            assertEquals(
                    List.of(),
                    QueryLab.after(
                            c,
                            7,
                            new QueryLab.Cursor(
                                    java.time.Instant.parse("2026-01-01T00:00:00Z"), 100),
                            10));
        }
    }

    @Test
    void halfOpenDayEqualsFunctionWithoutCrossTenantRows() throws Exception {
        try (Connection c = MySqlFixture.open()) {
            var fast = QueryLab.onUtcDay(c, 7, java.time.Instant.parse("2025-01-01T00:00:00Z"));
            assertEquals(List.of(1L, 2L), fast);
            assertEquals(QueryLab.slowDay(c, 7, "2025-01-01"), fast);
            System.out.println(
                    QueryLab.plan(
                            c,
                            "SELECT id FROM c06_orders WHERE created_at>=? AND created_at<?",
                            java.time.Instant.parse("2025-01-01T00:00:00Z"),
                            java.time.Instant.parse("2025-01-02T00:00:00Z")));
        }
    }
}
