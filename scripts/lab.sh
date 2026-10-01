#!/usr/bin/env bash
# 所有目录均从脚本位置解析；支持 macOS 自带 Bash 3.2，无需 GNU 特有参数。
set -eu
SCRIPT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
if ! command -v python3 >/dev/null 2>&1; then
  printf '%s\n' '错误：需要 Python 3.9 或更高版本。请按 docs/environment/README.md 准备后重试。' >&2
  exit 2
fi
exec python3 "$SCRIPT_DIR/lab.py" "$@"
