package labs.messaging;

import java.util.ArrayList;
import java.util.Arrays;

/** 固定5.3.2发行包的启动入口与资源预算；不改写镜像中的官方脚本。 */
public final class RocketRuntime {
    private RocketRuntime() {}

    public static String startupScript() {
        return """
               set -u
               cat > /tmp/lab-broker.conf <<'BROKER'
               brokerClusterName=LabCluster
               brokerName=broker-a
               brokerId=0
               namesrvAddr=127.0.0.1:9876
               brokerIP1=127.0.0.1
               listenPort=10911
               autoCreateTopicEnable=false
               autoCreateSubscriptionGroup=false
               flushDiskType=SYNC_FLUSH
               transactionCheckInterval=1000
               transactionTimeOut=1000
               transactionCheckMax=120
               timerWheelEnable=true
               BROKER
               cat > /tmp/lab-proxy.json <<'PROXY'
               {"rocketMQClusterName":"LabCluster","useEndpointPortFromRequest":true}
               PROXY
               JAVA_OPT_EXT='-Xms64m -Xmx128m -Xmn32m -XX:MaxDirectMemorySize=32m' sh mqnamesrv &
               namesrv_pid=$!
               sh mqbroker --enable-proxy -c /tmp/lab-broker.conf -pc /tmp/lab-proxy.json &
               broker_pid=$!
               trap 'kill "$broker_pid" "$namesrv_pid" 2>/dev/null || true' TERM INT
               wait "$broker_pid"
               status=$?
               printf '\\nROCKETMQ_BROKER_EXIT=%s\\n' "$status"
               for file in /home/rocketmq/logs/rocketmqlogs/*.log; do
                 [ -f "$file" ] || continue
                 printf '\\n=== %s (last 40 lines) ===\\n' "$file"
                 tail -n 40 "$file"
               done
               kill "$namesrv_pid" 2>/dev/null || true
               exit "$status"
               """;
    }

    public static String[] adminCommand(String... arguments) {
        // tools.sh硬编码-Xms1g/-Xmx1g且不读取JAVA_OPT_EXT，不能在同一小容器里再启动1GiB工具JVM。
        String script =
                """
                exec "${JAVA_HOME}/bin/java" -Xms32m -Xmx128m -Xmn32m \
                  -XX:MaxMetaspaceSize=128m -XX:MaxDirectMemorySize=32m \
                  "-Drmq.logback.configurationFile=${ROCKETMQ_HOME}/conf/rmq.tools.logback.xml" \
                  -cp ".:${ROCKETMQ_HOME}/conf:${ROCKETMQ_HOME}/lib/*" \
                  org.apache.rocketmq.tools.command.MQAdminStartup "$@"
                """;
        ArrayList<String> command =
                new ArrayList<>(Arrays.asList("sh", "-c", script, "lab-mqadmin"));
        command.addAll(Arrays.asList(arguments));
        return command.toArray(String[]::new);
    }

    public static String tail(String value, int maximum) {
        if (value.length() <= maximum) return value;
        return "[earlier output omitted]\n" + value.substring(value.length() - maximum);
    }
}
