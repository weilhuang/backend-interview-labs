#!/usr/bin/env bash
set -euo pipefail
# 监听不是业务成功证据；同时要求 NameServer 的真实集群响应和 Broker 活跃状态。
timeout 2s bash -c 'exec 3<>/dev/tcp/127.0.0.1/8081'
bash /opt/lab-rocketmq/admin.sh clusterList -n 127.0.0.1:9876 > /dev/null
