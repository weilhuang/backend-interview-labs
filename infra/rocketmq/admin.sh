#!/usr/bin/env bash
# tools.sh 默认创建 1GiB 工具 JVM，故用原发行包同一主类并明确限制工具预算。
set -euo pipefail
case "${1:-}" in
  clusterList|updateTopic|updateSubGroup|topicStatus) command=$1 ;;
  *) printf '%s\n' '仅允许 clusterList/updateTopic/updateSubGroup/topicStatus' >&2; exit 2 ;;
esac
rpc_timeout=${LAB_ADMIN_TIMEOUT_SECONDS:-15}
if ! [[ "$rpc_timeout" =~ ^([1-9]|1[0-5])$ ]]; then
  printf '%s\n' '管理 RPC 超时必须为 1–15 秒' >&2
  exit 2
fi
output=$(mktemp)
trap 'rm -f "$output"' EXIT
# 超时在容器内结束 Java；foreground 保持监督脚本进程组，TERM 可同时覆盖工具子进程。
if ! timeout --foreground --kill-after=1s "${rpc_timeout}s" "${JAVA_HOME}/bin/java" -Xms32m -Xmx128m -Xmn32m \
  -XX:MaxMetaspaceSize=128m -XX:MaxDirectMemorySize=32m \
  "-Drmq.logback.configurationFile=${ROCKETMQ_HOME}/conf/rmq.tools.logback.xml" \
  -cp ".:${ROCKETMQ_HOME}/conf:${ROCKETMQ_HOME}/lib/*" \
  org.apache.rocketmq.tools.command.MQAdminStartup "$@" > "$output" 2>&1; then
  cat "$output" >&2
  exit 1
fi
cat "$output"
# mqadmin 可能打印异常却退出 0，不能只判断退出码或表头。
if grep -Eq '(^|[[:space:]])([[:alnum:]_$]+\.)*[[:alnum:]_$]*(Exception|Error)(:|[[:space:]]|$)|command failed|Caused by:' "$output"; then
  exit 1
fi
case "$command" in
  clusterList) grep -Eq '^LabCluster[[:space:]]+broker-a[[:space:]]+0[[:space:]]+127\.0\.0\.1:10911[[:space:]]+V[0-9_]+[[:space:]].*[[:space:]]true[[:space:]]*$' "$output" ;;
  updateTopic) grep -Eq 'create topic to .* success\.' "$output" ;;
  updateSubGroup) grep -Eq 'create subscription group to .* success\.' "$output" ;;
  topicStatus) grep -Eq '^broker-a[[:space:]]+[0-9]+[[:space:]]+[0-9]+[[:space:]]+[0-9]+' "$output" ;;
esac
