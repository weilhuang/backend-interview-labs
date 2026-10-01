import static org.junit.jupiter.api.Assertions.*;

import labs.*;

import org.junit.jupiter.api.*;

import java.sql.*;
import java.util.*;

class IndexContractTest {
    @Test
    void queryUsesExplicitProjectionAndStableOrder() {
        assertTrue(IndexLab.QUERY.startsWith("SELECT id,created_at"));
        assertTrue(IndexLab.QUERY.contains("ORDER BY created_at,id"));
    }

    @Test
    void distributionIsBounded() {
        assertThrows(IllegalArgumentException.class, () -> IndexLab.seedDistribution(null, 0));
        assertThrows(IllegalArgumentException.class, () -> IndexLab.seedDistribution(null, 100001));
    }
}
