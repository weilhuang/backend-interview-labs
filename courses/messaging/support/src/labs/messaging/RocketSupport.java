package labs.messaging;

import com.github.dockerjava.api.async.ResultCallback;
import com.github.dockerjava.api.command.InspectContainerResponse;
import com.github.dockerjava.api.model.ExposedPort;
import com.github.dockerjava.api.model.Frame;
import com.github.dockerjava.api.model.Ports;

import org.apache.rocketmq.client.apis.ClientConfiguration;
import org.apache.rocketmq.client.apis.consumer.FilterExpression;
import org.apache.rocketmq.client.apis.consumer.SimpleConsumer;
import org.apache.rocketmq.client.apis.producer.Producer;
import org.testcontainers.containers.GenericContainer;
import org.testcontainers.containers.wait.strategy.AbstractWaitStrategy;
import org.testcontainers.utility.DockerImageName;

import java.net.InetSocketAddress;
import java.net.Socket;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.util.Map;
import java.util.UUID;
import java.util.concurrent.TimeUnit;

/** Broker 与 Proxy 同容器；客户端只连接随机映射的 gRPC 端口。 */
public final class RocketSupport extends GenericContainer<RocketSupport> {

    public RocketSupport() {
        super(DockerImageName.parse(Images.get("ROCKETMQ_IMAGE")));
        withExposedPorts(8081);
        withCreateContainerCmdModifier(
                command ->
                        command.getHostConfig().withMemory(1610612736L).withNanoCPUs(2000000000L));
        // 官方runbroker.sh默认MaxDirectMemorySize=15g，课堂容器必须有自己的直接内存上界。
        withEnv("JAVA_OPT_EXT", "-Xms256m -Xmx512m -Xmn128m -XX:MaxDirectMemorySize=128m");
        withCommand("sh", "-c", RocketRuntime.startupScript());
        // 1.20.6内部shell端口探测在容器退出137时出现过假成功，不能把它当服务就绪证据。
        waitingFor(
                new AbstractWaitStrategy() {
                    @Override
                    protected void waitUntilReady() {
                        RocketSupport.this.awaitReady(startupTimeout);
                    }
                });
        withStartupTimeout(Duration.ofMinutes(3));
    }

    public String endpoint() {
        return getHost() + ":" + currentGrpcPort(freshInfo());
    }

    private InspectContainerResponse freshInfo() {
        return getDockerClient().inspectContainerCmd(getContainerId()).exec();
    }

    private int currentGrpcPort(InspectContainerResponse info) {
        Ports.Binding[] bindings =
                info.getNetworkSettings().getPorts().getBindings().get(ExposedPort.tcp(8081));
        if (bindings == null || bindings.length == 0)
            throw new IllegalStateException("当前inspect没有Proxy端口绑定");
        return Integer.parseInt(bindings[0].getHostPortSpec());
    }

    /** 同时用于初始启动和原容器重启；每轮读取当前状态、端口以及真实NameServer/Broker响应。 */
    public void awaitReady(Duration timeout) {
        long deadline = System.nanoTime() + timeout.toNanos();
        String last = "尚未连接Proxy";
        try {
            while (System.nanoTime() < deadline) {
                var info = freshInfo();
                if (!Boolean.TRUE.equals(info.getState().getRunning()))
                    throw new IllegalStateException("就绪前容器已停止");
                boolean listening;
                try (Socket socket = new Socket()) {
                    socket.connect(new InetSocketAddress(getHost(), currentGrpcPort(info)), 500);
                    listening = true;
                } catch (java.io.IOException refused) {
                    listening = false;
                    last = refused.toString();
                }
                if (listening) {
                    var result = execAdmin("clusterList", "-n", "127.0.0.1:9876");
                    last = result.stdout() + result.stderr();
                    if (RocketAdminResult.succeeded(
                            "clusterList", result.exitCode(), result.stdout(), result.stderr())) {
                        if (Boolean.TRUE.equals(freshInfo().getState().getRunning())) return;
                        throw new IllegalStateException("管理RPC成功后容器立即停止");
                    }
                }
                Thread.sleep(250);
            }
            throw new IllegalStateException(
                    "等待真实Proxy及Broker就绪超时：" + RocketRuntime.tail(last, 2000));
        } catch (InterruptedException interrupted) {
            Thread.currentThread().interrupt();
            throw diagnosed("等待就绪被中断", interrupted);
        } catch (Exception failure) {
            throw diagnosed("启动/重启未就绪", failure);
        }
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
        long deadline = System.nanoTime() + Duration.ofSeconds(45).toNanos();
        ContainerExecException last = null;
        do {
            final AdminExec result;
            try {
                if (!Boolean.TRUE.equals(freshInfo().getState().getRunning()))
                    throw new IllegalStateException("执行管理命令前容器已停止");
                result = execAdmin(arguments);
            } catch (Exception failure) {
                if (failure instanceof InterruptedException) Thread.currentThread().interrupt();
                throw diagnosed("管理命令=" + arguments[0], failure);
            }
            if (RocketAdminResult.succeeded(
                    arguments[0], result.exitCode(), result.stdout(), result.stderr()))
                return result.stdout();
            last =
                    new ContainerExecException(
                            "命令="
                                    + arguments[0]
                                    + "，退出码="
                                    + result.exitCode()
                                    + "\n"
                                    + result.stdout()
                                    + result.stderr());
            Thread.sleep(200);
        } while (System.nanoTime() < deadline);
        throw diagnosed("管理命令重试耗尽=" + arguments[0], last);
    }

    private record AdminExec(int exitCode, String stdout, String stderr) {}

    private AdminExec execAdmin(String... arguments) throws Exception {
        String id =
                getDockerClient()
                        .execCreateCmd(getContainerId())
                        .withAttachStdout(true)
                        .withAttachStderr(true)
                        .withCmd(RocketRuntime.adminCommand(arguments))
                        .exec()
                        .getId();
        StringBuffer stdout = new StringBuffer();
        StringBuffer stderr = new StringBuffer();
        try (var callback =
                new ResultCallback.Adapter<Frame>() {
                    @Override
                    public void onNext(Frame frame) {
                        String value = new String(frame.getPayload(), StandardCharsets.UTF_8);
                        if (frame.getStreamType()
                                == com.github.dockerjava.api.model.StreamType.STDERR)
                            stderr.append(value);
                        else stdout.append(value);
                    }
                }) {
            getDockerClient().execStartCmd(id).exec(callback);
            if (!callback.awaitCompletion(15, TimeUnit.SECONDS))
                throw new IllegalStateException("单次管理RPC超过15秒，停止重试以免堆积工具JVM");
        }
        Long exit = getDockerClient().inspectExecCmd(id).exec().getExitCodeLong();
        return new AdminExec(
                exit == null ? -1 : exit.intValue(), stdout.toString(), stderr.toString());
    }

    private ContainerExecException diagnosed(String operation, Throwable cause) {
        String diagnostics = diagnostics(operation);
        System.err.println(diagnostics);
        return new ContainerExecException(diagnostics, cause);
    }

    /** 清理前保留真实exit/OOM状态与限量日志；诊断失败本身不能覆盖原始失败。 */
    private String diagnostics(String operation) {
        StringBuilder result =
                new StringBuilder("RocketMQ夹具失败：")
                        .append(operation)
                        .append("\ncontainer=")
                        .append(getContainerId());
        try {
            var state = freshInfo().getState();
            result.append("\nstatus=")
                    .append(state.getStatus())
                    .append(", running=")
                    .append(state.getRunning())
                    .append(", exitCode=")
                    .append(state.getExitCodeLong())
                    .append(", oomKilled=")
                    .append(state.getOOMKilled())
                    .append(", error=")
                    .append(state.getError())
                    .append(", startedAt=")
                    .append(state.getStartedAt())
                    .append(", finishedAt=")
                    .append(state.getFinishedAt());
        } catch (Exception unavailable) {
            result.append("\ninspect失败：").append(unavailable);
        }
        StringBuffer logs = new StringBuffer();
        try (var callback =
                new ResultCallback.Adapter<Frame>() {
                    @Override
                    public void onNext(Frame frame) {
                        synchronized (logs) {
                            logs.append(new String(frame.getPayload(), StandardCharsets.UTF_8));
                            if (logs.length() > 12000) logs.delete(0, logs.length() - 12000);
                        }
                    }
                }) {
            getDockerClient()
                    .logContainerCmd(getContainerId())
                    .withStdOut(true)
                    .withStdErr(true)
                    .withFollowStream(false)
                    .withTail(200)
                    .exec(callback);
            if (!callback.awaitCompletion(5, TimeUnit.SECONDS))
                result.append("\nDocker日志读取超过5秒，以下为已收到的尾部");
        } catch (Exception unavailable) {
            if (unavailable instanceof InterruptedException) Thread.currentThread().interrupt();
            result.append("\n日志读取失败：").append(unavailable);
        }
        return result.append("\n--- Docker日志末尾（最多12000字符）---\n").append(logs).toString();
    }

    @Override
    protected void containerIsStopping(InspectContainerResponse ignoredCachedInfo) {
        // 包括测试业务步骤意外遇到进程退出，必须在try-with-resources删除容器前重新inspect。
        try {
            if (!Boolean.TRUE.equals(freshInfo().getState().getRunning()))
                System.err.println(diagnostics("清理前发现容器已停止"));
        } catch (Exception failure) {
            System.err.println("RocketMQ清理前状态检查失败：" + failure);
        }
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

        public ContainerExecException(String detail, Throwable cause) {
            super("容器管理命令失败：" + detail, cause);
        }
    }
}
