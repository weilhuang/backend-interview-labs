#!/usr/bin/env bash
# 开发专用：同容器 NameServer + Broker + CLUSTER Proxy；不修改官方启动脚本。
set -euo pipefail
# 独立进程组让 TERM 同时到达官方 shell 包装与 Java 子进程。
set -m
LAB_DATA=/tmp/lab-rocketmq
printf 'RocketMQ 开发容器：uid=%s gid=%s，数据目录=%s/store\n' "$(id -u)" "$(id -g)" "$LAB_DATA"
if ! mkdir -p "$LAB_DATA/store" || ! test -w "$LAB_DATA/store"; then
  printf '%s\n' '数据卷不可写：检查当前项目 rocketmq-data 的 UID/挂载来源；不会自动 chmod/chown、改用 root 或删除卷。' >&2
  exit 1
fi
cat > "$LAB_DATA/broker.conf" <<'BROKER'
brokerClusterName=LabCluster
brokerName=broker-a
brokerId=0
namesrvAddr=127.0.0.1:9876
brokerIP1=127.0.0.1
listenPort=10911
autoCreateTopicEnable=false
autoCreateSubscriptionGroup=false
flushDiskType=SYNC_FLUSH
storePathRootDir=/tmp/lab-rocketmq/store
storePathCommitLog=/tmp/lab-rocketmq/store/commitlog
mappedFileSizeCommitLog=67108864
fileReservedTime=24
timerWheelEnable=true
BROKER
cat > "$LAB_DATA/proxy.json" <<'PROXY'
{"rocketMQClusterName":"LabCluster","namesrvAddr":"127.0.0.1:9876","proxyMode":"CLUSTER","useEndpointPortFromRequest":true}
PROXY
# 官方默认按日志类别保留大量文件；只缩小非持久化层中的日志配置，不改官方脚本。
for conf in "${ROCKETMQ_HOME}"/conf/rmq.*.logback.xml; do
  test -f "$conf" || continue
  sed -i -E 's#<maxIndex>[[:space:]]*[0-9]+[[:space:]]*</maxIndex>#<maxIndex>1</maxIndex>#g; s#<maxFileSize>[^<]+</maxFileSize>#<maxFileSize>1MB</maxFileSize>#g' "$conf"
done
cd "${ROCKETMQ_HOME}/bin"
JAVA_OPT_EXT='-Xms64m -Xmx128m -Xmn32m -XX:MaxDirectMemorySize=32m' sh mqnamesrv &
namesrv_pid=$!
JAVA_OPT_EXT='-Xms256m -Xmx512m -Xmn128m -XX:MaxDirectMemorySize=128m' sh mqbroker -c "$LAB_DATA/broker.conf" &
broker_pid=$!
# 5.3.2 LOCAL Proxy 忽略映射端口；独立 CLUSTER Proxy 才保留客户端请求端点。
JAVA_OPT_EXT='-Xms128m -Xmx256m -Xmn64m -XX:MaxDirectMemorySize=64m' sh mqproxy -pm cluster -pc "$LAB_DATA/proxy.json" &
proxy_pid=$!
shutdown() {
  trap '' TERM INT
  kill -TERM -- "-$proxy_pid" "-$broker_pid" "-$namesrv_pid" 2>/dev/null || true
  wait "$proxy_pid" 2>/dev/null || true
  wait "$broker_pid" 2>/dev/null || true
  wait "$namesrv_pid" 2>/dev/null || true
}
trap 'shutdown; exit 0' TERM INT
# 任意关键进程退出均使容器失败，不能只剩 NameServer 却仍显示 Running。
set +e
wait -n "$namesrv_pid" "$broker_pid" "$proxy_pid"
status=$?
set -e
printf '\nRocketMQ 关键进程退出，status=%s\n' "$status" >&2
for file in /home/rocketmq/logs/rocketmqlogs/*.log; do
  test -f "$file" || continue
  printf '\n=== %s (last 30 lines) ===\n' "$file"
  tail -n 30 "$file"
done
shutdown
# 长期服务即便意外零退出，也应报告失败。
test "$status" -ne 0 || status=1
exit "$status"
