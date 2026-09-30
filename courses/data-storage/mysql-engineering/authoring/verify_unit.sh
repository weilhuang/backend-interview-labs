#!/usr/bin/env bash
# 无网络模式只编译生产代码与纯逻辑测试，绝不把结果标成MySQL集成通过。
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
: "${JAVA_HOME:?请设置完整JDK21目录}"
: "${JUNIT_CONSOLE_JAR:?请设置JUnit Platform1.11.4 standalone jar路径}"
CLASSPATH="$JUNIT_CONSOLE_JAR:$ROOT/build/deps/*"
"$JAVA_HOME/bin/javac" -version
for task in "$ROOT"/mysql/*/*; do
  [[ -f "$task/task-info.yaml" ]] || continue
  out="$ROOT/build/manual/$(basename "$task")"; mkdir -p "$out"
  "$JAVA_HOME/bin/javac" --release 21 -encoding UTF-8 -cp "$CLASSPATH" -d "$out" "$ROOT"/support/src/labs/*.java "$ROOT"/shared/src/labs/environment/*.java "$task"/src/labs/*.java "$task"/test/*ContractTest.java
  "$JAVA_HOME/bin/java" -jar "$JUNIT_CONSOLE_JAR" execute --class-path "$out" --scan-class-path --fail-if-no-tests --disable-banner
 done
