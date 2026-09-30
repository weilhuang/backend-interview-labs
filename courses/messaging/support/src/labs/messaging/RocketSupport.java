package labs.messaging;

import apache.rocketmq.v2.Code;
import apache.rocketmq.v2.MessagingServiceGrpc;
import apache.rocketmq.v2.QueryRouteRequest;
import apache.rocketmq.v2.QueryRouteResponse;
import apache.rocketmq.v2.Resource;

import com.github.dockerjava.api.async.ResultCallback;
import com.github.dockerjava.api.command.InspectContainerResponse;
import com.github.dockerjava.api.model.ExposedPort;
import com.github.dockerjava.api.model.Frame;
import com.github.dockerjava.api.model.Ports;

import org.apache.rocketmq.client.apis.ClientConfiguration;
import org.apache.rocketmq.client.apis.consumer.FilterExpression;
import org.apache.rocketmq.client.apis.consumer.SimpleConsumer;
import org.apache.rocketmq.client.apis.producer.Producer;
import org.apache.rocketmq.client.java.misc.ClientId;
import org.apache.rocketmq.client.java.route.Endpoints;
import org.apache.rocketmq.client.java.rpc.Signature;
import org.apache.rocketmq.shaded.io.grpc.ManagedChannelBuilder;
import org.apache.rocketmq.shaded.io.grpc.StatusRuntimeException;
import org.apache.rocketmq.shaded.io.grpc.stub.MetadataUtils;
import org.testcontainers.containers.GenericContainer;
import org.testcontainers.containers.wait.strategy.AbstractWaitStrategy;
import org.testcontainers.utility.DockerImageName;

import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.util.Map;
import java.util.Set;
import java.util.UUID;
import java.util.concurrent.TimeUnit;
import java.util.stream.Collectors;

/** Broker 与 Proxy 同容器；客户端只连接随机映射的 gRPC 端口。 */
public final class RocketSupport extends GenericContainer<RocketSupport> {
    private boolean diagnosticsPrinted;

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

    /** 只有真实gRPC路由及当前映射地址都正确，才算初始启动或重启就绪。 */
    public void awaitReady(Duration timeout) {
        long deadline = System.nanoTime() + timeout.toNanos();
        String readyTopic = unique("readiness");
        boolean topicCreated = false;
        String last = "尚未收到Proxy协议响应";
        Throwable lastFailure = null;
        try {
            while (System.nanoTime() < deadline) {
                if (!Boolean.TRUE.equals(freshInfo().getState().getRunning()))
                    throw new IllegalStateException("就绪前容器已停止");
                if (!topicCreated) {
                    var result = readinessAdmin(deadline, "clusterList", "-n", "127.0.0.1:9876");
                    last = result.stdout() + result.stderr();
                    if (RocketAdminResult.succeeded(
                            "clusterList", result.exitCode(), result.stdout(), result.stderr())) {
                        var created =
                                readinessAdmin(
                                        deadline,
                                        "updateTopic",
                                        "-n",
                                        "127.0.0.1:9876",
                                        "-b",
                                        "127.0.0.1:10911",
                                        "-t",
                                        readyTopic,
                                        "-r",
                                        "1",
                                        "-w",
                                        "1",
                                        "-a",
                                        "+message.type=NORMAL");
                        if (!RocketAdminResult.succeeded(
                                "updateTopic",
                                created.exitCode(),
                                created.stdout(),
                                created.stderr()))
                            throw new IllegalStateException(
                                    "创建隔离就绪主题失败：" + created.stdout() + created.stderr());
                        topicCreated = true;
                    }
                }
                if (topicCreated && System.nanoTime() < deadline) {
                    try {
                        var response =
                                queryRouteOnce(
                                        readyTopic,
                                        Math.min(
                                                TimeUnit.SECONDS.toNanos(2),
                                                deadline - System.nanoTime()));
                        Set<String> returned = routeAddresses(response);
                        lastFailure = null;
                        last = response.getStatus() + ", returned=" + returned;
                        if (RocketRuntime.protocolReady(
                                response.getStatus().getCode(), returned, endpoint())) {
                            if (!Boolean.TRUE.equals(freshInfo().getState().getRunning()))
                                throw new IllegalStateException("协议就绪后容器立即停止");
                            System.err.println("RocketMQ协议就绪：" + last);
                            return;
                        }
                    } catch (StatusRuntimeException transientFailure) {
                        if (!RocketRuntime.transientReadinessFailure(
                                transientFailure.getStatus().getCode())) throw transientFailure;
                        lastFailure = transientFailure;
                        last = transientFailure.toString();
                    }
                }
                long remaining = deadline - System.nanoTime();
                if (remaining > 0)
                    TimeUnit.NANOSECONDS.sleep(
                            Math.min(remaining, TimeUnit.MILLISECONDS.toNanos(250)));
            }
            throw new IllegalStateException(
                    "等待真实Proxy协议就绪超时：" + RocketRuntime.tail(last, 2000), lastFailure);
        } catch (InterruptedException interrupted) {
            Thread.currentThread().interrupt();
            throw diagnosed("等待就绪被中断", interrupted);
        } catch (Exception failure) {
            throw diagnosed("启动/重启未就绪", failure);
        }
    }

    private AdminExec readinessAdmin(long deadline, String... arguments) throws Exception {
        long remaining = deadline - System.nanoTime();
        if (remaining <= 0) throw new IllegalStateException("就绪预算已耗尽");
        int seconds = (int) Math.min(15, Math.max(1, (remaining + 999_999_999L) / 1_000_000_000L));
        return execCommand(seconds, 20000, RocketRuntime.adminCommand(arguments));
    }

    public ClientConfiguration configuration() {
        return ClientConfiguration.newBuilder()
                .setEndpoints(endpoint())
                .enableSsl(false)
                .setRequestTimeout(Duration.ofSeconds(10))
                .build();
    }

    /** 业务主题单次真实查询；失败不重试，保留清理前诊断。 */
    public Set<String> routeEndpoints(String topic) throws Exception {
        try {
            var response = queryRouteOnce(topic, TimeUnit.SECONDS.toNanos(10));
            if (response.getStatus().getCode() != Code.OK)
                throw new IllegalStateException("QueryRoute失败：" + response.getStatus());
            Set<String> endpoints = routeAddresses(response);
            System.err.println(
                    "RocketMQ QueryRoute：requested=" + endpoint() + ", returned=" + endpoints);
            return endpoints;
        } catch (Exception failure) {
            throw diagnosed("QueryRoute topic=" + topic, failure);
        }
    }

    private QueryRouteResponse queryRouteOnce(String topic, long timeoutNanos) throws Exception {
        ClientConfiguration configuration = configuration();
        Endpoints requested = new Endpoints(configuration.getEndpoints());
        var channel =
                ManagedChannelBuilder.forTarget(requested.getGrpcTarget()).usePlaintext().build();
        try {
            return MessagingServiceGrpc.newBlockingStub(channel)
                    .withInterceptors(
                            MetadataUtils.newAttachHeadersInterceptor(
                                    Signature.sign(configuration, new ClientId())))
                    .withDeadlineAfter(Math.max(1, timeoutNanos), TimeUnit.NANOSECONDS)
                    .queryRoute(
                            QueryRouteRequest.newBuilder()
                                    .setTopic(Resource.newBuilder().setName(topic))
                                    .setEndpoints(requested.toProtobuf())
                                    .build());
        } finally {
            channel.shutdownNow().awaitTermination(1, TimeUnit.SECONDS);
        }
    }

    private static Set<String> routeAddresses(QueryRouteResponse response) {
        return response.getMessageQueuesList().stream()
                .flatMap(queue -> queue.getBroker().getEndpoints().getAddressesList().stream())
                .map(address -> address.getHost() + ":" + address.getPort())
                .collect(Collectors.toSet());
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
        return execCommand(15, 20000, RocketRuntime.adminCommand(arguments));
    }

    private AdminExec execCommand(int seconds, int outputLimit, String... command)
            throws Exception {
        String id =
                getDockerClient()
                        .execCreateCmd(getContainerId())
                        .withAttachStdout(true)
                        .withAttachStderr(true)
                        .withCmd(command)
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
                            appendBounded(stderr, value, outputLimit);
                        else appendBounded(stdout, value, outputLimit);
                    }
                }) {
            getDockerClient().execStartCmd(id).exec(callback);
            if (!callback.awaitCompletion(seconds, TimeUnit.SECONDS))
                throw new IllegalStateException("容器命令超过" + seconds + "秒，停止重试以免堆积进程");
        }
        Long exit = getDockerClient().inspectExecCmd(id).exec().getExitCodeLong();
        return new AdminExec(
                exit == null ? -1 : exit.intValue(), stdout.toString(), stderr.toString());
    }

    private static void appendBounded(StringBuffer target, String value, int maximum) {
        synchronized (target) {
            target.append(value);
            if (target.length() > maximum) target.delete(0, target.length() - maximum);
        }
    }

    private ContainerExecException diagnosed(String operation, Throwable cause) {
        String diagnostics = diagnostics(operation);
        System.err.println(diagnostics);
        diagnosticsPrinted = true;
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
        result.append("\n--- Docker日志末尾（最多12000字符）---\n").append(logs);
        try {
            if (Boolean.TRUE.equals(freshInfo().getState().getRunning())) {
                AdminExec files = execCommand(5, 40000, RocketRuntime.fileLogsCommand());
                result.append("\n--- RocketMQ文件日志（最多40000字符）---\n")
                        .append(files.stdout())
                        .append(files.stderr());
            } else {
                result.append("\n容器已退出，无法exec读取文件；检查启动监督脚本输出的文件日志尾部");
            }
        } catch (Exception unavailable) {
            if (unavailable instanceof InterruptedException) Thread.currentThread().interrupt();
            result.append("\n文件日志读取失败：").append(unavailable);
        }
        return result.toString();
    }

    @Override
    protected void containerIsStopping(InspectContainerResponse ignoredCachedInfo) {
        // 测试业务异常时容器可能仍在运行；不依赖running=false才留证。
        try {
            if (!diagnosticsPrinted) System.err.println(diagnostics("清理前快照"));
        } catch (Exception failure) {
            System.err.println("RocketMQ清理前状态检查失败：" + failure);
        }
    }

    public Producer producer(String topic) throws Exception {
        try {
            return RocketClient.PROVIDER
                    .newProducerBuilder()
                    .setClientConfiguration(configuration())
                    .setTopics(topic)
                    .build();
        } catch (Exception failure) {
            throw diagnosed("创建Producer topic=" + topic, failure);
        }
    }

    public SimpleConsumer consumer(String group, String topic) throws Exception {
        try {
            return RocketClient.PROVIDER
                    .newSimpleConsumerBuilder()
                    .setClientConfiguration(configuration())
                    .setConsumerGroup(group)
                    .setAwaitDuration(Duration.ofSeconds(5))
                    .setSubscriptionExpressions(Map.of(topic, FilterExpression.SUB_ALL))
                    .build();
        } catch (Exception failure) {
            throw diagnosed("创建SimpleConsumer group=" + group + ", topic=" + topic, failure);
        }
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
