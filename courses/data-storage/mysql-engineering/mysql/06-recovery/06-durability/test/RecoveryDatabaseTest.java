import static org.junit.jupiter.api.Assertions.*;

import labs.*;

import org.junit.jupiter.api.*;

import java.sql.*;
import java.util.*;

@Tag("integration")
class RecoveryDatabaseTest {
    @BeforeEach
    void reset() throws Exception {
        MySqlFixture.reset();
    }

    @Test
    void killedServerRecoversCommittedAndDiscardsPending() throws Exception {
        try (Connection c = MySqlFixture.open()) {
            assertTrue(RecoveryLab.inspect(c).strictLocalCommit());
            RecoveryLab.confirmed(c, 1);
        }
        Connection pending = MySqlFixture.open();
        RecoveryLab.pending(pending, 2);
        var mysql = MySqlFixture.MYSQL;
        String id = mysql.getContainerId();
        try {
            mysql.getDockerClient().killContainerCmd(id).withSignal("KILL").exec();
            mysql.getDockerClient().startContainerCmd(id).exec();
            long deadline = System.nanoTime() + java.time.Duration.ofSeconds(90).toNanos();
            SQLException last = null;
            boolean ready = false;
            while (System.nanoTime() < deadline) {
                try (Connection c = MySqlFixture.open()) {
                    Db.scalar(c, "SELECT 1");
                    ready = true;
                    break;
                } catch (SQLException e) {
                    last = e;
                    Thread.sleep(250);
                }
            }
            assertTrue(ready, "同一隔离容器必须恢复就绪，最后错误=" + last);
            try (Connection c = MySqlFixture.open()) {
                assertEquals(List.of(1L), Db.ids(c, "SELECT id FROM c06_recovery ORDER BY id"));
            }
        } finally {
            try {
                pending.close();
            } catch (SQLException ignored) {
                /* 服务被终止后关闭可能失败，不能覆盖主要断言。 */
            }
        }
    }
}
