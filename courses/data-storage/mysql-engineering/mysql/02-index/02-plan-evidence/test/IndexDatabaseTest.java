import static org.junit.jupiter.api.Assertions.*;

import labs.*;

import org.junit.jupiter.api.*;

import java.sql.*;
import java.util.*;

@Tag("integration")
class IndexDatabaseTest {
    @BeforeEach
    void reset() throws Exception {
        MySqlFixture.reset();
        try (Connection c = MySqlFixture.open()) {
            if (Db.scalar(
                            c,
                            "SELECT COUNT(*) FROM information_schema.statistics WHERE"
                                + " table_schema=DATABASE() AND table_name='c06_orders' AND"
                                + " index_name='idx_c06_feed'")
                    > 0) Db.update(c, "DROP INDEX idx_c06_feed ON c06_orders");
        }
    }

    @Test
    void indexPreservesResultAndHasRequiredColumns() throws Exception {
        try (Connection c = MySqlFixture.open()) {
            IndexLab.seedDistribution(c, 2000);
            List<Long> before = IndexLab.result(c);
            String beforePlan = IndexLab.explain(c, false);
            IndexLab.addIndex(c);
            IndexLab.addIndex(c);
            assertEquals(before, IndexLab.result(c));
            assertEquals(
                    "tenant_id,status,created_at,id",
                    Db.text(
                                    c,
                                    "SELECT GROUP_CONCAT(column_name ORDER BY seq_in_index) FROM"
                                        + " information_schema.statistics WHERE"
                                        + " table_schema=DATABASE() AND table_name='c06_orders' AND"
                                        + " index_name='idx_c06_feed'")
                            .trim());
            String afterPlan = IndexLab.explain(c, true);
            assertFalse(beforePlan.isBlank());
            assertTrue(afterPlan.contains("actual time"));
            System.out.println("索引前计划：" + beforePlan + "\n索引后实际计划：" + afterPlan);
        }
    }
}
