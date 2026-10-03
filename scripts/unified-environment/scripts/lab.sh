#!/usr/bin/env bash
# 兼容 macOS Bash 3.2；始终从脚本位置定位统一课程根目录。
set -eu
SCRIPT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
command -v python3 >/dev/null 2>&1 || { printf '%s\n' '需要 Python 3.9+，请阅读 docs/统一环境.md；不会自动安装软件。' >&2; exit 2; }
exec python3 "$SCRIPT_DIR/lab.py" "$@"
