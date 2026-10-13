#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"

# .env is local shell configuration, loaded only by this launcher.
if [[ -f "${NAVICAST_ENV_FILE:-.env}" ]]; then
    set -a
    source "${NAVICAST_ENV_FILE:-.env}"
    set +a
fi
export PORT="${PORT:-8000}"
if ! [[ "$PORT" =~ ^[0-9]+$ ]] || (( PORT < 1 || PORT > 65535 )); then
    echo 'PORT must be between 1 and 65535' >&2
    exit 1
fi
if [[ "${NAVICAST_MODE:-live}" != demo && -z "${NAVICAST_DB_PASSWORD:-}" ]]; then
    echo 'Set NAVICAST_DB_PASSWORD in .env or the environment' >&2
    exit 1
fi

python3 - <<'PY'
import os
if os.getenv('NAVICAST_MODE', 'live') != 'demo':
    import psycopg2
    from config import get_db_config
    try:
        conn = psycopg2.connect(**get_db_config())
        conn.close()
    except Exception:
        raise SystemExit('PostgreSQL unavailable; check NAVICAST_DB_* configuration')
PY

mkdir -p "${NAVICAST_LOG_DIR:-logs}"
pids=()
cleanup() {
    for pid in "${pids[@]:-}"; do
        [[ -n "$pid" ]] && kill "$pid" 2>/dev/null || true
    done
    wait 2>/dev/null || true
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

start_service() {
    python3 "$1.py" > "${NAVICAST_LOG_DIR:-logs}/$1-output.log" 2>&1 &
    pids+=("$!")
}
if [[ "${NAVICAST_MODE:-live}" != demo ]]; then
    start_service mqtt_client
    start_service prediction_service
fi
start_service api_server
sleep 1
printf 'NaviCast %s: http://localhost:%s (Ctrl+C to stop)\n' "${NAVICAST_MODE:-live}" "$PORT"
while true; do
    for pid in "${pids[@]}"; do
        if ! kill -0 "$pid" 2>/dev/null; then
            echo "A NaviCast service exited; inspect ${NAVICAST_LOG_DIR:-logs}/*-output.log" >&2
            exit 1
        fi
    done
    sleep 1
done
