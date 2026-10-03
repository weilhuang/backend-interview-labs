#!/bin/sh
set -eu
# exec 用Java替换shell，而不是让shell成为不转发TERM的父进程。
exec java -XX:MaxRAMPercentage=65.0 -cp /opt/app/classes labs.CloudNativeApp "$@"
