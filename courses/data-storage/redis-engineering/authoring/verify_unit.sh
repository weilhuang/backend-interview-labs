#!/usr/bin/env bash
# 使用已下载的官方依赖编译完整源码，再运行纯Java契约；绝不将其报告为真实服务测试。
set -euo pipefail
cd "$(dirname "$0")/.."
: "${JAVA_HOME:?请设置为JDK21}"
: "${JUNIT_CONSOLE:?请设置为JUnit Platform 1.11.4独立控制台JAR}"
: "${VALIDATION_DEPS:?请设置为包含Jedis/Testcontainers/JDBC等实际依赖JAR的目录}"
mkdir -p build/manual
find support/src shared/src redis -name '*.java' > build/sources.txt
"$JAVA_HOME/bin/javac" --release 21 -encoding UTF-8 -cp "$VALIDATION_DEPS/*:$JUNIT_CONSOLE" -d build/manual @build/sources.txt
classpath="build/manual"
for jar in "$VALIDATION_DEPS"/*.jar; do classpath="$classpath:$jar"; done
"$JAVA_HOME/bin/java" -jar "$JUNIT_CONSOLE" execute --class-path "$classpath" --scan-class-path=build/manual --include-engine junit-jupiter --exclude-tag integration --details summary --fail-if-no-tests
