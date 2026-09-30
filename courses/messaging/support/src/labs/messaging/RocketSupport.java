package labs.messaging;

import org.apache.rocketmq.client.apis.ClientConfiguration;
import org.apache.rocketmq.client.apis.consumer.FilterExpression;
import org.apache.rocketmq.client.apis.consumer.SimpleConsumer;
import org.apache.rocketmq.client.apis.producer.Producer;
import org.testcontainers.containers.GenericContainer;
import org.testcontainers.containers.wait.strategy.Wait;
import org.testcontainers.utility.DockerImageName;

import java.time.Duration;
import java.util.Map;
import java.util.UUID;

/** Broker 与 Proxy 同容器；客户端只连接随机映射的 gRPC 端口。 */
public final class RocketSupport extends GenericContainer<RocketSupport> {

    public RocketSupport() {
        super(DockerImageName.parse(Images.get("ROCKETMQ_IMAGE")));
        withExposedPorts(8081);
        withCreateContainerCmdModifier(
                command ->
                        command.getHostConfig().withMemory(1610612736L).withNanoCPUs(2000000000L));
        withEnv("JAVA_OPT_EXT", "-Xms256m -Xmx512m -Xmn128m");
        withCommand(
                "sh",
                "-c",
                "printf 'brokerClusterName=LabCluster\\n"
                    + "brokerName=broker-a\\n"
                    + "brokerId=0\\n"
                    + "namesrvAddr=127.0.0.1:9876\\n"
                    + "brokerIP1=127.0.0.1\\n"
                    + "listenPort=10911\\n"
                    + "autoCreateTopicEnable=false\\n"
                    + "autoCreateSubscriptionGroup=false\\n"
                    + "flushDiskType=SYNC_FLUSH\\n"
                    + "transactionCheckInterval=1000\\n"
                    + "transactionTimeOut=1000\\n"
                    + "transactionCheckMax=120\\n"
                    + "timerWheelEnable=true\\n"
                    + "' > /tmp/lab-broker.conf; printf"
                    + " '{\"rocketMQClusterName\":\"LabCluster\",\"useEndpointPortFromRequest\":true}'"
                    + " > /tmp/lab-proxy.json; sh mqnamesrv & sh mqbroker --enable-proxy -c"
                    + " /tmp/lab-broker.conf -pc /tmp/lab-proxy.json");
        waitingFor(Wait.forListeningPort());
        withStartupTimeout(Duration.ofMinutes(3));
    }

    public String endpoint() {
        return getHost() + ":" + getMappedPort(8081);
    }

    public ClientConfiguration configuration() {
        return ClientConfiguration.newBuilder()
                .setEndpoints(endpoint())
                .enableSsl(false)
                .setRequestTimeout(Duration.ofSeconds(10))
                .build();
    }

    public static String unique(String prefix) {
        return prefix + UUID.randomUUID().toString().replace("-", "");
    }

    public String topic(String type) throws Exception {
        String topic = unique("topic");
        admin(
                "updateTopic",
                "-n",
                "127.0.0.1:9876",
                "-b",
                "127.0.0.1:10911",
                "-t",
                topic,
                "-r",
                "1",
                "-w",
                "1",
                "-a",
                "+message.type=" + type);
        return topic;
    }

    public String group(boolean ordered) throws Exception {
        String group = unique("group");
        admin(
                "updateSubGroup",
                "-n",
                "127.0.0.1:9876",
                "-b",
                "127.0.0.1:10911",
                "-g",
                group,
                "-o",
                Boolean.toString(ordered));
        return group;
    }

    public String admin(String... arguments) throws Exception {
        if (arguments.length == 0) throw new IllegalArgumentException("管理命令不能为空");
        String[] command = new String[arguments.length + 2];
        command[0] = "sh";
        command[1] = "mqadmin";
        System.arraycopy(arguments, 0, command, 2, arguments.length);
        long deadline = System.nanoTime() + Duration.ofSeconds(45).toNanos();
        ContainerExecException last = null;
        do {
            var result = execInContainer(command);
            if (RocketAdminResult.succeeded(
                    arguments[0], result.getExitCode(), result.getStdout(), result.getStderr()))
                return result.getStdout();
            last =
                    new ContainerExecException(
                            "命令="
                                    + arguments[0]
                                    + "，退出码="
                                    + result.getExitCode()
                                    + "\n"
                                    + result.getStdout()
                                    + result.getStderr());
            Thread.sleep(200);
        } while (System.nanoTime() < deadline);
        throw last;
    }

    public Producer producer(String topic) throws Exception {
        return RocketClient.PROVIDER
                .newProducerBuilder()
                .setClientConfiguration(configuration())
                .setTopics(topic)
                .build();
    }

    public SimpleConsumer consumer(String group, String topic) throws Exception {
        return RocketClient.PROVIDER
                .newSimpleConsumerBuilder()
                .setClientConfiguration(configuration())
                .setConsumerGroup(group)
                .setAwaitDuration(Duration.ofSeconds(5))
                .setSubscriptionExpressions(Map.of(topic, FilterExpression.SUB_ALL))
                .build();
    }

    public static final class ContainerExecException extends RuntimeException {
        public ContainerExecException(String detail) {
            super("容器管理命令失败：" + detail);
        }
    }
}
