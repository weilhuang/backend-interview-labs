#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
case "${1:-doctor}" in
  doctor)
    command -v java >/dev/null || { echo '请先安装课程规定的JDK21'; exit 1; }
    java -version
    major="$(java -XshowSettings:properties -version 2>&1 | awk -F= '/java.specification.version/{gsub(/[[:space:]]/, "", $2); print $2}')"
    test "$major" = 21 || { echo '当前java不为21，请同时检查项目SDK、Gradle JVM和测试JVM'; exit 1; }
    if command -v docker >/dev/null && docker info >/dev/null 2>&1; then
      echo 'Docker守护进程可用，可执行真实服务集成'
    else
      echo 'Docker不可用：可以运行单元和本机RPC，MySQL/Kafka/Redis集成不能视为通过'
    fi
    test -f ../../infra/versions.env || test -f shared/versions.env || { echo '缺少共享镜像版本台账'; exit 1; }
    ;;
  test) exec ./gradlew test ;;
  integration) exec ./gradlew integrationTest ;;
  run)
    module="${2:-02-grpc}"
    case "$module" in
      01-failure-model|02-grpc|03-dubbo|04-resilience|05-idempotency|06-transactions|07-outbox-cache|08-capacity) ;;
      *) echo '未知模块，请查看课程首页'; exit 2 ;;
    esac
    exec ./gradlew ":${module}:run"
    ;;
  *) echo '用法：scripts/course.sh doctor|test|integration|run 模块名'; exit 2 ;;
esac
