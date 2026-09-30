#!/usr/bin/env bash
# 课程自身的开发/演示入口；外部服务仍使用仓库共享环境脚本。
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
STATE="$ROOT/build/server"
umask 077
mkdir -p "$STATE"
export GRADLE_USER_HOME="${GRADLE_USER_HOME:-$ROOT/build/gradle-home}"
cd "$ROOT"
JAVA_BIN="${JAVA_HOME:+$JAVA_HOME/bin/}java"
JAVAC_BIN="${JAVA_HOME:+$JAVA_HOME/bin/}javac"
gradle_command() {
  local command="${LAB_GRADLE_BIN:-$ROOT/gradlew}"
  if [[ "${LAB_OFFLINE:-0}" == 1 ]]; then "$command" --offline "$@"; else "$command" "$@"; fi
}
valid_pid() { [[ "$1" =~ ^[1-9][0-9]*$ ]]; }
# Linux和macOS都提供ps；不依赖/proc，也不把僵尸当运行中服务。
alive() {
  valid_pid "$1" || return 1
  local status
  status="$(LC_ALL=C ps -p "$1" -o stat= 2>/dev/null)" || return 1
  [[ -n "$status" && "$status" != *Z* ]]
}
owned() {
  valid_pid "$1" && [[ -r "$STATE/token" ]] || return 1
  local token command
  token="$(cat "$STATE/token")"
  [[ "$token" =~ ^[0-9a-f]{32}$ ]] || return 1
  command="$(LC_ALL=C ps -ww -p "$1" -o command= 2>/dev/null)" || return 1
  # 每次启动独有的随机token，不能仅凭项目路径认领后来复用同一PID的进程。
  [[ " $command " == *" -Dframework.lab.token=$token "* && " $command " == *" labs.frameworks.Lab "* ]]
}
clear_state() { rm -f "$STATE/pid" "$STATE/token" "$STATE/module"; }
action="${1:-doctor}"
case "$action" in
 doctor)
  command -v "$JAVA_BIN" >/dev/null; command -v "$JAVAC_BIN" >/dev/null
  "$JAVA_BIN" -version; "$JAVAC_BIN" -version
  "$JAVA_BIN" -version 2>&1 | grep -E 'version "21\.' >/dev/null || { echo '请使用完整JDK21'; exit 1; }
  echo 'JDK检查通过。Docker仅真实MySQL集成需要；前端无Node依赖。'
  ;;
 test) gradle_command test ;;
 start)
  module="${2:-02-http-contract}"
  case "$module" in 02-http-contract|07-integrated-service) ;; *) echo '交互前端只支持02或07阶段';exit 2;; esac
  if [[ -f "$STATE/pid" ]] && alive "$(cat "$STATE/pid")"; then echo '本课程服务已运行，请先check或stop';exit 1;fi
  gradle_command ":$module:verificationClasspath"
  cp_file="framework-course/01-boot/$module/build/verification-classpath.txt"
  [[ -s "$cp_file" ]] || { echo '未找到已验证运行类路径';exit 1; }
  token="$(od -An -N16 -tx1 /dev/urandom | tr -d ' \n')"
  [[ "$token" =~ ^[0-9a-f]{32}$ ]] || { echo '未能生成安全的实例标记';exit 1; }
  printf '%s\n' "$token" > "$STATE/token"
  nohup "$JAVA_BIN" "-Dframework.lab.token=$token" "-Dframework.lab.instance=$ROOT" -cp "$(cat "$cp_file")" labs.frameworks.Lab > "$STATE/application.log" 2>&1 &
  echo $! > "$STATE/pid"; echo "$module" > "$STATE/module"
  echo '启动中；执行scripts/course.sh check验证就绪，再打开http://127.0.0.1:18084'
  ;;
 check)
  [[ -f "$STATE/pid" ]] || { echo '没有本课程服务PID，请先start';exit 1; }
  pid="$(cat "$STATE/pid")"
  alive "$pid" && owned "$pid" || { echo '服务未运行或实例身份不匹配，拒绝把其他HTTP服务当作本课程';exit 1; }
  for ((attempt=0; attempt<30; attempt++)); do
   if curl --noproxy '*' --fail --silent http://127.0.0.1:18084/api/orders > "$STATE/health-response.json"; then echo '真实HTTP就绪，返回订单列表';exit 0;fi
   sleep 1
  done
  echo '尚未就绪，请查看build/server/application.log';exit 1
  ;;
 stop)
  [[ -f "$STATE/pid" ]] || { echo '没有本课程服务PID';exit 0; }
  pid="$(cat "$STATE/pid")"
  valid_pid "$pid" || { echo 'PID记录格式无效，拒绝发送信号';exit 1; }
  if ! alive "$pid"; then clear_state;echo '服务已停止';exit 0;fi
  owned "$pid" || { echo 'PID或随机实例标记归属不匹配，拒绝停止其他进程';exit 1; }
  if ! kill -TERM "$pid"; then
    if ! alive "$pid"; then clear_state;echo '服务已停止';exit 0;fi
    echo '未能向本实例发送停止信号';exit 1
  fi
  for ((attempt=0; attempt<100; attempt++)); do
    if ! alive "$pid" || ! owned "$pid"; then clear_state;echo '本课程服务已停止';exit 0;fi
    sleep 0.1
  done
  echo '停止等待超时，保留PID供排查；没有强杀其他进程';exit 1
  ;;
 *) echo '用法：scripts/course.sh {doctor|test|start [02-http-contract或07-integrated-service]|check|stop}';exit 2;;
esac
