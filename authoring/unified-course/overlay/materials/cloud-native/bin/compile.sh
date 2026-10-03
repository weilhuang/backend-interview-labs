#!/bin/sh
set -eu
HERE=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
OUT=${CLOUDNATIVE_CLASSES:-"$HERE/build/classes"}
exec python3 "$HERE/bin/compile.py" --out "$OUT"
