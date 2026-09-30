package labs.messaging;

import apache.rocketmq.v2.Code;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;
import java.util.Set;
import org.apache.rocketmq.shaded.io.grpc.Status;

/** 固定5.3.2发行包的启动入口与资源预算；不改写镜像中的官方脚本。 */
public final class RocketRuntime {
  private RocketRuntime() {}

  /** 20位文件名是段起始物理位点；预分配下一段有文件长度，但尚未写入消息。 */
  public static List<String> writtenCommitLogFiles(String listing, long maxOffset) {
    if (maxOffset <= 0) throw new IllegalArgumentException("已确认发送后写入上界必须大于零");
    var written = new ArrayList<String>();
    for (String path : listing.lines().toList()) {
      if (!path.matches("/home/rocketmq/store/commitlog/[0-9]{20}"))
        throw new IllegalArgumentException("不是直接CommitLog数据文件：" + path);
      long start = Long.parseLong(path.substring(path.lastIndexOf('/') + 1));
      if (start < maxOffset) written.add(path);
    }
    if (written.isEmpty()) throw new IllegalArgumentException("没有包含已写记录的CommitLog段");
    return written.stream().sorted().toList();
  }

  /** 只有启动期可等待这些传输暂态，业务操作与认证错误不重试。 */
  public static boolean transientReadinessFailure(Status.Code code) {
    return code == Status.Code.UNAVAILABLE || code == Status.Code.DEADLINE_EXCEEDED;
  }

  /** 新探针主题传播可等待；内部固定端口和认证失败必须明确失败。 */
  public static boolean protocolReady(Code code, Set<String> returned, String requested) {
    if (code == Code.TOPIC_NOT_FOUND) return false;
    if (code != Code.OK) throw new IllegalStateException("就绪协议拒绝：" + code);
    if (returned.isEmpty()) return false;
    if (!returned.equals(Set.of(requested)))
      throw new IllegalStateException(
          "Proxy返回不可达路由：requested=" + requested + ", returned=" + returned);
    return true;
  }

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
storePathRootDir=/home/rocketmq/store
storePathCommitLog=/home/rocketmq/store/commitlog
autoCreateTopicEnable=false
autoCreateSubscriptionGroup=false
flushDiskType=SYNC_FLUSH
transactionCheckInterval=1000
transactionTimeOut=1000
transactionCheckMax=120
timerWheelEnable=true
BROKER
cat > /tmp/lab-proxy.json <<'PROXY'
{"rocketMQClusterName":"LabCluster","namesrvAddr":"127.0.0.1:9876","proxyMode":"CLUSTER","useEndpointPortFromRequest":true}
PROXY
cat > /tmp/lab-admin.sh <<'ADMIN'
@@ADMIN_SCRIPT@@
ADMIN
JAVA_OPT_EXT='-Xms64m -Xmx128m -Xmn32m -XX:MaxDirectMemorySize=32m' sh mqnamesrv &
namesrv_pid=$!
sh mqbroker -c /tmp/lab-broker.conf &
broker_pid=$!
proxy_pid=
cleanup() {
  [ -z "$proxy_pid" ] || kill "$proxy_pid" 2>/dev/null || true
  kill "$broker_pid" "$namesrv_pid" 2>/dev/null || true
}
trap 'cleanup; exit 143' TERM INT
check_process() {
  kill -0 "$2" 2>/dev/null && return
  wait "$2"
  status=$?
  printf '\\nROCKETMQ_%s_EXIT=%s\\n' "$1" "$status"
  for file in /home/rocketmq/logs/rocketmqlogs/*.log; do
    [ -f "$file" ] || continue
    printf '\\n=== %s (last 40 lines) ===\\n' "$file"
    tail -n 40 "$file"
  done
  cleanup
  [ "$status" -ne 0 ] || status=1
  exit "$status"
}
# CLUSTER Proxy启动即创建系统主题，必须先看到NameServer内的Broker注册。
registration_deadline=$(( $(date +%s) + 120 ))
while :; do
  check_process NAMESRV "$namesrv_pid"
  check_process BROKER "$broker_pid"
  remaining=$(( registration_deadline - $(date +%s) ))
  if [ "$remaining" -le 0 ]; then
    printf '\\nROCKETMQ_BROKER_REGISTRATION_TIMEOUT\\n'
    tail -c 6000 /tmp/lab-registration.log
    cleanup
    exit 1
  fi
  [ "$remaining" -le 15 ] || remaining=15
  if timeout -k 2 "$remaining" sh /tmp/lab-admin.sh clusterList -n 127.0.0.1:9876 > /tmp/lab-registration.log 2>&1 &&
     grep -Eq '^[[:space:]]*LabCluster[[:space:]]+broker-a[[:space:]]+0[[:space:]]+127[.]0[.]0[.]1:10911([[:space:]]|$)' /tmp/lab-registration.log &&
     ! grep -Eq 'Exception|Caused by:|Error:' /tmp/lab-registration.log; then
    printf '\\nROCKETMQ_BROKER_REGISTERED\\n'
    cat /tmp/lab-registration.log
    break
  fi
  sleep 1
done
# 禁止业务自动建组时，CLUSTER Proxy的系统广播组也要显式预建。
if ! timeout -k 2 15 sh /tmp/lab-admin.sh updateSubGroup -n 127.0.0.1:9876 -b 127.0.0.1:10911 -g CID_DefaultHeartBeatSyncerTopic -d true > /tmp/lab-system-group.log 2>&1 ||
   ! grep -Eq 'create subscription group to .* success' /tmp/lab-system-group.log ||
   grep -Eq 'Exception|Caused by:|Error:' /tmp/lab-system-group.log; then
  printf '\\nROCKETMQ_SYSTEM_GROUP_CREATE_FAILED\\n'
  tail -c 6000 /tmp/lab-system-group.log
  cleanup
  exit 1
fi
# LOCAL模式忽略请求端点并返回brokerIP1:8081；随机宿主映射必须使用CLUSTER路由。
JAVA_OPT_EXT='-Xms128m -Xmx256m -Xmn64m -XX:MaxDirectMemorySize=64m' sh mqproxy -pm cluster -pc /tmp/lab-proxy.json &
proxy_pid=$!
while :; do
  check_process NAMESRV "$namesrv_pid"
  check_process BROKER "$broker_pid"
  check_process PROXY "$proxy_pid"
  sleep 1
done
"""
        .replace("@@ADMIN_SCRIPT@@", adminCommand()[2]);
  }

  /** Proxy日志默认写文件，容器仍运行时也必须在删除前读取。 */
  public static String[] fileLogsCommand() {
    return new String[] {
      "sh",
      "-c",
      """
      for file in /home/rocketmq/logs/rocketmqlogs/proxy.log \
                  /home/rocketmq/logs/rocketmqlogs/broker.log \
                  /home/rocketmq/logs/rocketmqlogs/broker_default.log \
                  /home/rocketmq/logs/rocketmqlogs/transaction.log \
                  /home/rocketmq/logs/rocketmqlogs/store.log \
                  /home/rocketmq/logs/rocketmqlogs/namesrv.log; do
        [ -f "$file" ] || continue
        printf '\\n=== %s (last 6000 bytes) ===\\n' "$file"
        tail -c 6000 "$file"
      done
      """
    };
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
    ArrayList<String> command = new ArrayList<>(Arrays.asList("sh", "-c", script, "lab-mqadmin"));
    command.addAll(Arrays.asList(arguments));
    return command.toArray(String[]::new);
  }

  public static String tail(String value, int maximum) {
    if (value.length() <= maximum) return value;
    return "[earlier output omitted]\n" + value.substring(value.length() - maximum);
  }
}
