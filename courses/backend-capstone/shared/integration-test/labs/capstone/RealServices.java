package labs.capstone;

import io.grpc.*;

import org.testcontainers.containers.*;
import org.testcontainers.kafka.KafkaContainer;
import org.testcontainers.utility.DockerImageName;

import java.nio.file.*;
import java.time.Duration;
import java.util.*;
import java.util.concurrent.TimeUnit;

/** 每次实验独占新容器；此类不连接学习者Compose数据，关闭只清理自己创建的容器。 */
final class RealServices implements AutoCloseable {
    final MySQLContainer<?> mysql;
    final GenericContainer<?> redis;
    final KafkaContainer kafka;
    Database db;
    OrderCache cache;
    OrderService orders;
    DeliveryRpc rpc;
    ManagedChannel channel;
    DeliveryFlow flow;

    static String image(String key) throws Exception {
        Properties p = new Properties();
        try (var in =
                Files.newInputStream(
                        Path.of(System.getProperty("lab.versions", "../../infra/versions.env")))) {
            p.load(in);
        }
        String v = p.getProperty(key);
        if (v == null || v.endsWith(":latest")) throw new IllegalStateException("缺少固定镜像：" + key);
        return v;
    }

    RealServices() throws Exception {
        mysql =
                new MySQLContainer<>(DockerImageName.parse(image("MYSQL_IMAGE")))
                        .withDatabaseName("capstone")
                        .withUsername("lab")
                        .withPassword("lab_only_password");
        redis =
                new GenericContainer<>(DockerImageName.parse(image("REDIS_IMAGE")))
                        .withExposedPorts(6379);
        kafka = new KafkaContainer(DockerImageName.parse(image("KAFKA_IMAGE")));
        try {
            mysql.start();
            redis.start();
            kafka.start();
            connect();
            Broker.initialize(kafka.getBootstrapServers());
        } catch (Exception | Error failure) {
            close();
            throw failure;
        }
    }

    void connect() throws Exception {
        db = new Database(mysql.getJdbcUrl(), mysql.getUsername(), mysql.getPassword());
        db.initialize();
        cache = new OrderCache(redis.getHost(), redis.getMappedPort(6379));
        orders = new OrderService(db, cache);
        rpc = new DeliveryRpc(db, 0);
        channel = ManagedChannelBuilder.forAddress("127.0.0.1", rpc.port()).usePlaintext().build();
        flow = new DeliveryFlow(db, kafka.getBootstrapServers(), channel);
    }

    void closeClients() throws Exception {
        if (channel != null) {
            channel.shutdownNow();
            channel.awaitTermination(3, TimeUnit.SECONDS);
            channel = null;
        }
        if (rpc != null) {
            rpc.close();
            rpc = null;
        }
        if (db != null) {
            db.close();
            db = null;
        }
    }

    void restartMysql() throws Exception {
        closeClients();
        mysql.getDockerClient().restartContainerCmd(mysql.getContainerId()).exec();
        long end = System.nanoTime() + Duration.ofSeconds(90).toNanos();
        Exception last = null;
        while (System.nanoTime() < end) {
            try {
                var info =
                        mysql.getDockerClient().inspectContainerCmd(mysql.getContainerId()).exec();
                int port =
                        Integer.parseInt(
                                info.getNetworkSettings()
                                        .getPorts()
                                        .getBindings()
                                        .get(new com.github.dockerjava.api.model.ExposedPort(3306))[
                                        0]
                                        .getHostPortSpec());
                try (var probe =
                        new Database(
                                "jdbc:mysql://" + mysql.getHost() + ":" + port + "/capstone",
                                mysql.getUsername(),
                                mysql.getPassword())) {
                    probe.scalar("SELECT 1");
                    db =
                            new Database(
                                    "jdbc:mysql://" + mysql.getHost() + ":" + port + "/capstone",
                                    mysql.getUsername(),
                                    mysql.getPassword());
                    db.initialize();
                    cache = new OrderCache(redis.getHost(), redis.getMappedPort(6379));
                    orders = new OrderService(db, cache);
                    rpc = new DeliveryRpc(db, 0);
                    channel =
                            ManagedChannelBuilder.forAddress("127.0.0.1", rpc.port())
                                    .usePlaintext()
                                    .build();
                    flow = new DeliveryFlow(db, kafka.getBootstrapServers(), channel);
                    return;
                }
            } catch (Exception e) {
                last = e;
            }
            Thread.sleep(200);
        }
        throw new IllegalStateException("MySQL未在恢复预算内就绪", last);
    }

    public void close() {
        try {
            closeClients();
        } catch (Exception ignored) {
        }
        try {
            kafka.close();
        } finally {
            try {
                redis.close();
            } finally {
                mysql.close();
            }
        }
    }
}
