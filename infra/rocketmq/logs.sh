#!/usr/bin/env bash
# 只读当前容器的有限诊断；不输出环境变量或真实凭据。
set -u
printf 'uid=%s gid=%s\n' "$(id -u)" "$(id -g)"
ls -ld /tmp /tmp/lab-rocketmq /tmp/lab-rocketmq/store 2>/dev/null || true
for file in /home/rocketmq/logs/rocketmqlogs/*.log; do
  test -f "$file" || continue
  printf '\n=== %s (last 30 lines) ===\n' "$file"
  tail -n 30 "$file"
done
