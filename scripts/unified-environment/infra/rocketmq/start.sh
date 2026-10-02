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
LAB_SCRIPT_DIR="$(CDPATH= cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REGISTER_WAIT_SECONDS=120
children=()
probe_pid=''
shutdown() {
  trap '' TERM INT
  stopping=("${children[@]}")
  if [ -n "$probe_pid" ]; then stopping+=("$probe_pid"); fi
  for pid in "${stopping[@]}"; do
    kill -TERM -- "-$pid" 2>/dev/null || true
  done
  # 官方 shell 可能先于 Java 退出；必须等待整个进程组，给 Broker 关闭钩子完成持久化的机会。
  stop_deadline=$((SECONDS + 25))
  while [ "$SECONDS" -lt "$stop_deadline" ]; do
    groups_running=false
    for pid in "${stopping[@]}"; do
      if kill -0 -- "-$pid" 2>/dev/null; then groups_running=true; fi
    done
    if [ "$groups_running" = false ]; then break; fi
    sleep 0.1
  done
  for pid in "${stopping[@]}"; do
    if kill -0 -- "-$pid" 2>/dev/null; then
      printf '停止等待25秒后仍有进程组%s；强制终止，不能宣称本次为优雅关闭。\n' "$pid" >&2
      kill -KILL -- "-$pid" 2>/dev/null || true
    fi
    wait "$pid" 2>/dev/null || true
  done
}
# 从首个服务启动起始终有清理保障；注册等待期间收到 TERM 也不能漏掉 Java 子进程。
trap shutdown EXIT
trap 'exit 0' TERM INT
cd "${ROCKETMQ_HOME}/bin"
JAVA_OPT_EXT='-Xms64m -Xmx128m -Xmn32m -XX:MaxDirectMemorySize=32m' sh mqnamesrv &
namesrv_pid=$!
children+=("$namesrv_pid")
JAVA_OPT_EXT='-Xms256m -Xmx512m -Xmn128m -XX:MaxDirectMemorySize=128m' sh mqbroker -c "$LAB_DATA/broker.conf" &
broker_pid=$!
children+=("$broker_pid")
# CLUSTER Proxy 启动即创建内部心跳主题，必须先有真实 Broker 注册路由；TCP/sleep 都不能代替。
deadline=$((SECONDS + REGISTER_WAIT_SECONDS))
registered=false
registration_log="$LAB_DATA/registration-check.log"
while [ "$SECONDS" -lt "$deadline" ]; do
  if ! kill -0 "$namesrv_pid" 2>/dev/null || ! kill -0 "$broker_pid" 2>/dev/null; then
    printf '%s\n' '注册屏障失败：NameServer/Broker 在可用路由出现前退出；不启动 Proxy。' >&2
    break
  fi
  remaining=$((deadline - SECONDS))
  if [ "$remaining" -le 0 ]; then break; fi
  rpc_timeout=$remaining
  if [ "$rpc_timeout" -gt 15 ]; then rpc_timeout=15; fi
  LAB_ADMIN_TIMEOUT_SECONDS="$rpc_timeout" bash "$LAB_SCRIPT_DIR/admin.sh" clusterList -n 127.0.0.1:9876 > "$registration_log" 2>&1 &
  probe_pid=$!
  if wait "$probe_pid"; then
    if kill -0 "$namesrv_pid" 2>/dev/null && kill -0 "$broker_pid" 2>/dev/null && [ "$SECONDS" -lt "$deadline" ]; then
      registered=true
    fi
  fi
  probe_pid=''
  if [ "$registered" = true ]; then break; fi
  if [ "$SECONDS" -lt "$deadline" ]; then sleep 1; fi
done
if [ "$registered" != true ]; then
  printf 'Broker 注册屏障未通过（最多%s秒）；不会盲重启或删除数据。最近一次实际 RPC 输出：\n' "$REGISTER_WAIT_SECONDS" >&2
  if [ -f "$registration_log" ]; then tail -n 80 "$registration_log" >&2; fi
  bash "$LAB_SCRIPT_DIR/logs.sh" >&2 || true
  exit 1
fi
printf '%s\n' 'Broker 注册屏障通过：NameServer 已返回 LabCluster/broker-a 活跃路由。'
# 保持自动创建任意消费组关闭，但显式初始化 Proxy 自身依赖的系统组。
bash "$LAB_SCRIPT_DIR/admin.sh" updateSubGroup -n 127.0.0.1:9876 -b 127.0.0.1:10911 -g CID_DefaultHeartBeatSyncerTopic -d true > "$LAB_DATA/proxy-group-init.log" 2>&1 &
probe_pid=$!
if ! wait "$probe_pid"; then
  probe_pid=''
  printf '%s\n' 'Proxy 系统消费组初始化失败；不启动 Proxy，不删除数据。' >&2
  tail -n 80 "$LAB_DATA/proxy-group-init.log" >&2
  exit 1
fi
probe_pid=''
printf '%s\n' 'Proxy 系统消费组初始化通过，现在启动 CLUSTER Proxy。'
# 5.3.2 LOCAL Proxy 忽略映射端口；独立 CLUSTER Proxy 才保留客户端请求端点。
JAVA_OPT_EXT='-Xms128m -Xmx256m -Xmn64m -XX:MaxDirectMemorySize=64m' sh mqproxy -pm cluster -pc "$LAB_DATA/proxy.json" &
proxy_pid=$!
children+=("$proxy_pid")
# 任意关键进程退出均使容器失败，不能只剩 NameServer 却仍显示 Running。
set +e
wait -n "$namesrv_pid" "$broker_pid" "$proxy_pid"
status=$?
set -e
printf '\nRocketMQ 关键进程退出，status=%s\n' "$status" >&2
bash "$LAB_SCRIPT_DIR/logs.sh" >&2 || true
# 长期服务即便意外零退出，也应报告失败。
test "$status" -ne 0 || status=1
exit "$status"
