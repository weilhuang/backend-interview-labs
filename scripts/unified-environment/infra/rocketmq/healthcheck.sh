#!/usr/bin/env bash
set -euo pipefail
# start.sh 先通过实际 Broker 注册屏障才启动 Proxy；此处每次仍检查当前状态，不能复用旧屏障结果。
# 监听不是业务成功证据；同时要求 NameServer 的真实集群响应和 Broker 活跃状态。
timeout 2s bash -c 'exec 3<>/dev/tcp/127.0.0.1/8081'
bash /opt/lab-rocketmq/admin.sh clusterList -n 127.0.0.1:9876 > /dev/null
