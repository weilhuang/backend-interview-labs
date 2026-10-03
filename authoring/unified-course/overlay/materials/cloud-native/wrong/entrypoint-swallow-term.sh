#!/bin/sh
# 只由测试器启动的错误对照；不得部署。shell成为PID1并忽略TERM。
trap '' TERM
java -cp /opt/app/classes labs.CloudNativeApp "$@" &
wait
