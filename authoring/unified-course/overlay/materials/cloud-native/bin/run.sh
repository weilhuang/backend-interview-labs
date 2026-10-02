#!/bin/sh
set -eu
HERE=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
export WEB_ROOT=${WEB_ROOT:-"$HERE/web"}
export BIND_HOST=${BIND_HOST:-127.0.0.1}
export HTTP_PORT=${HTTP_PORT:-18085}
exec java -cp "${CLOUDNATIVE_CLASSES:-$HERE/build/classes}" labs.CloudNativeApp "$@"
