#!/usr/bin/env bash
# 官方Academy导出可能不含Wrapper；此入口不搜索浮动PATH里的Gradle。
set -eu
HERE="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
command -v python3 >/dev/null 2>&1 || { printf '%s\n' '需要Python3.9+；请阅读docs/统一环境.md' >&2; exit 2; }
exec python3 "$HERE/gradle_launcher.py" "$@"
