import static org.junit.jupiter.api.Assertions.*;

import labs.*;

import org.junit.jupiter.api.*;
import org.testcontainers.containers.MySQLContainer;
import org.testcontainers.containers.Network;
import org.testcontainers.utility.DockerImageName;

import java.sql.*;
import java.time.Duration;

/** 真实双节点异步复制；主动暂停SQL线程形成确定陈旧读，不用睡眠猜复制延迟。 */
@Tag("integration")
class ReplicaDatabaseTest {
    private MySQLContainer<?> node(Network network, String alias, int serverId) {
        return new MySQLContainer<>(DockerImageName.parse(Images.mysql()))
                .withDatabaseName("c06_replica_lab")
                .withUsername("root")
                .withPassword("synthetic_replica_lab")
                .withNetwork(network)
                .withNetworkAliases(alias)
                .withCommand(
                        "--server-id=" + serverId,
                        "--log-bin=mysql-bin",
                        "--gtid-mode=ON",
                        "--enforce-gtid-consistency=ON")
                .withStartupTimeout(Duration.ofMinutes(3));
    }

    private Connection connect(MySQLContainer<?> c) throws SQLException {
        return DriverManager.getConnection(c.getJdbcUrl(), c.getUsername(), c.getPassword());
    }

    @Test
    void confirmedPrimaryWriteCanBeStaleOnReplicaThenCatchUp() throws Exception {
        try (Network network = Network.newNetwork();
                var source = node(network, "source", 11);
                var replica = node(network, "replica", 12)) {
            source.start();
            replica.start();
            try (Connection a = connect(source);
                    Connection b = connect(replica)) {
                Db.update(
                        a, "CREATE USER 'c06_repl'@'%' IDENTIFIED BY 'synthetic_replication_only'");
                Db.update(a, "GRANT REPLICATION SLAVE ON *.* TO 'c06_repl'@'%'");
                Db.update(
                        a,
                        "CREATE TABLE c06_replica_stock(sku INT PRIMARY KEY, quantity INT NOT"
                            + " NULL)");
                Db.update(a, "INSERT INTO c06_replica_stock VALUES(101,10)");
                Db.update(
                        b,
                        "CHANGE REPLICATION SOURCE TO"
                            + " SOURCE_HOST='source',SOURCE_PORT=3306,SOURCE_USER='c06_repl',SOURCE_PASSWORD='synthetic_replication_only',SOURCE_AUTO_POSITION=1,GET_SOURCE_PUBLIC_KEY=1");
                Db.update(b, "START REPLICA");
                await(a, b);
                assertEquals(
                        10, Db.scalar(b, "SELECT quantity FROM c06_replica_stock WHERE sku=101"));
                Db.update(b, "STOP REPLICA SQL_THREAD");
                Db.update(a, "UPDATE c06_replica_stock SET quantity=8 WHERE sku=101");
                assertEquals(
                        8, Db.scalar(a, "SELECT quantity FROM c06_replica_stock WHERE sku=101"));
                assertEquals(
                        10, Db.scalar(b, "SELECT quantity FROM c06_replica_stock WHERE sku=101"));
                Db.update(b, "START REPLICA SQL_THREAD");
                await(a, b);
                assertEquals(
                        8, Db.scalar(b, "SELECT quantity FROM c06_replica_stock WHERE sku=101"));
            }
        }
    }

    private void await(Connection source, Connection replica) throws SQLException {
        String gtid = Db.text(source, "SELECT @@GLOBAL.gtid_executed").trim();
        // WAIT函数有自己的30秒预算，不能被Db.prepare的5秒查询超时提前打断。
        try (PreparedStatement p =
                replica.prepareStatement("SELECT WAIT_FOR_EXECUTED_GTID_SET(?,30)")) {
            p.setString(1, gtid);
            p.setQueryTimeout(35);
            try (ResultSet r = p.executeQuery()) {
                assertTrue(r.next());
                assertEquals(0, r.getInt(1), "副本应在预算内应用指定GTID");
                assertFalse(r.wasNull());
            }
        }
    }
}
