#!/usr/bin/env bash
set -euo pipefail
ROOT="$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)"
: "${JAVA_HOME:?请指向已安装的JDK21}"
: "${GRADLE_HOME:?请指向已安装的Gradle8.10.2}"
exec "$GRADLE_HOME/bin/gradle" --no-daemon --max-workers=1 '-Dorg.gradle.jvmargs=-Xmx384m -XX:ActiveProcessorCount=2' -p "$ROOT/validation" "$@"
