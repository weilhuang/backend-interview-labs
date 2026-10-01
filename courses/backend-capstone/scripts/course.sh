#!/usr/bin/env bash
set -euo pipefail
root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
versions=${LAB_SHARED_VERSIONS:-"$root/../../infra/versions.env"}
if [[ ! -f "$versions" && -f "$root/shared/versions.env" && -z "${LAB_SHARED_VERSIONS:-}" ]]; then versions="$root/shared/versions.env"; fi
[[ -f "$versions" ]] || { echo "缺少唯一镜像台账，请设置 LAB_SHARED_VERSIONS 指向仓库 infra/versions.env" >&2; exit 2; }
project="capstone-$(python3 -c 'import hashlib,sys; print(hashlib.sha256(sys.argv[1].encode()).hexdigest()[:12])' "$root")"
export CAPSTONE_STAGE=${CAPSTONE_STAGE:-05-defense}
case "$CAPSTONE_STAGE" in 01-contract|02-reliability|03-delivery|04-recovery|05-defense) ;; *) echo "未知检查点" >&2; exit 2;; esac
compose() { docker compose --project-name "$project" --env-file "$versions" --file "$root/compose.yaml" "$@"; }
service() { case "${1:-}" in mysql|redis|kafka|delivery|orders) printf '%s' "$1";; *) echo "只允许操作本项目 mysql/redis/kafka/delivery/orders" >&2; exit 2;; esac; }
case "${1:-help}" in
 doctor) java -version; docker version; docker compose version; compose config --quiet; echo "检查点：$CAPSTONE_STAGE；项目：$project；业务卷保留";;
 start) (cd "$root" && bash ./gradlew --no-daemon ":$CAPSTONE_STAGE:installDist"); compose up -d --wait --wait-timeout 180; echo "中文工作台：http://127.0.0.1:${CAPSTONE_HTTP_PORT:-8088}";;
 stop) compose stop --timeout 20; echo "已停止本课程服务，数据卷完整保留";;
 status) compose ps;;
 logs) compose logs --tail=150;;
 pause-service) target=$(service "${2:-}"); compose stop --timeout 20 "$target";;
 crash-service) case "${2:-}" in orders|delivery) target=$2;; *) echo "故障注入仅允许本项目orders或delivery进程" >&2; exit 2;; esac; compose kill --signal SIGKILL "$target";;
 recover-service) target=$(service "${2:-}"); compose up -d --wait --wait-timeout 180 "$target";;
 check) python3 "$root/scripts/check.py";;
 test) (cd "$root" && bash ./gradlew --no-daemon test);;
 integration) (cd "$root" && bash ./gradlew --no-daemon integrationTest);;
 *) echo "用法：scripts/course.sh doctor|start|stop|status|logs|check|test|integration|pause-service 服务|recover-service 服务|crash-service orders或delivery"; echo "没有重置或删除数据命令。检查点用 CAPSTONE_STAGE=02-reliability 选择";;
esac
