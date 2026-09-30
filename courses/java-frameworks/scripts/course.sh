#!/usr/bin/env bash
# 课程自身的开发/演示入口；外部服务仍使用仓库共享环境脚本。
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
STATE="$ROOT/build/server"
mkdir -p "$STATE"
export GRADLE_USER_HOME="${GRADLE_USER_HOME:-$ROOT/build/gradle-home}"
cd "$ROOT"
JAVA_BIN="${JAVA_HOME:+$JAVA_HOME/bin/}java"
JAVAC_BIN="${JAVA_HOME:+$JAVA_HOME/bin/}javac"
gradle_command() {
  local command="${LAB_GRADLE_BIN:-$ROOT/gradlew}"
  if [[ "${LAB_OFFLINE:-0}" == 1 ]]; then "$command" --offline "$@"; else "$command" "$@"; fi
}
alive() { kill -0 "$1" 2>/dev/null && [[ "$(awk '{print $3}' "/proc/$1/stat" 2>/dev/null || true)" != Z ]]; }
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
  cp_file="$(find "framework-course/01-boot/$module/build" -name verification-classpath.txt -print -quit)"
  [[ -n "$cp_file" ]] || { echo '未找到已验证运行类路径';exit 1; }
  nohup "$JAVA_BIN" "-Dframework.lab.instance=$ROOT" -cp "$(cat "$cp_file")" labs.frameworks.Lab > "$STATE/application.log" 2>&1 &
  echo $! > "$STATE/pid"; echo "$module" > "$STATE/module"
  echo '启动中；执行scripts/course.sh check验证就绪，再打开http://127.0.0.1:18084'
  ;;
 check)
  for _ in $(seq 1 30); do
   if curl --noproxy '*' --fail --silent http://127.0.0.1:18084/api/orders > "$STATE/health-response.json"; then echo '真实HTTP就绪，返回订单列表';exit 0;fi
   sleep 1
  done
  echo '尚未就绪，请查看build/server/application.log';exit 1
  ;;
 stop)
  [[ -f "$STATE/pid" ]] || { echo '没有本课程服务PID';exit 0; }
  pid="$(cat "$STATE/pid")"
  if ! alive "$pid"; then rm -f "$STATE/pid";echo '服务已停止';exit 0;fi
  [[ -r "/proc/$pid/cmdline" ]] && tr '\0' '\n' < "/proc/$pid/cmdline" | grep -Fx -- "-Dframework.lab.instance=$ROOT" >/dev/null || { echo 'PID归属不匹配，拒绝停止其他进程';exit 1; }
  kill -TERM "$pid"
  for _ in $(seq 1 100); do if ! alive "$pid";then rm -f "$STATE/pid";echo '本课程服务已停止';exit 0;fi;sleep 0.1;done
  echo '停止等待超时，保留PID供排查；没有强杀其他进程';exit 1
  ;;
 *) echo '用法：scripts/course.sh {doctor|test|start [02-http-contract或07-integrated-service]|check|stop}';exit 2;;
esac
