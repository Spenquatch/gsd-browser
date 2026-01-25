#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
STATE_DIR="${ROOT}/.redistest"
PIDFILE="${STATE_DIR}/redis.pid"
LOGFILE="${STATE_DIR}/redis.log"
MODEFILE="${STATE_DIR}/mode"
BIN_DIR="${STATE_DIR}/bin"
REDIS_SERVER="${BIN_DIR}/redis-server"
REDIS_CLI="${BIN_DIR}/redis-cli"
COMPOSE_FILE="${ROOT}/docker/compose.redistest.yml"

cmd="${1:-}"

docker_available() {
  command -v docker >/dev/null 2>&1 || return 1
  docker compose version >/dev/null 2>&1 || return 1
  docker info >/dev/null 2>&1 || return 1
  return 0
}

build_redis_if_needed() {
  if [[ -x "${REDIS_SERVER}" && -x "${REDIS_CLI}" ]]; then
    return 0
  fi

  mkdir -p "${STATE_DIR}"
  local build_dir="${STATE_DIR}/redis-src"
  rm -rf "${build_dir}"
  mkdir -p "${build_dir}"

  echo "redistest: building local redis-server (docker unavailable)"
  curl -fsSL "https://download.redis.io/redis-stable.tar.gz" -o "${build_dir}/redis-stable.tar.gz"
  tar -xzf "${build_dir}/redis-stable.tar.gz" -C "${build_dir}"

  local src_dir
  src_dir="$(find "${build_dir}" -mindepth 1 -maxdepth 1 -type d -name "redis-*" | head -n 1)"
  if [[ -z "${src_dir}" ]]; then
    echo "redistest: failed to locate redis source directory" >&2
    exit 1
  fi

  make -C "${src_dir}" -j"$(getconf _NPROCESSORS_ONLN || echo 2)" >/dev/null
  mkdir -p "${BIN_DIR}"
  cp -f "${src_dir}/src/redis-server" "${REDIS_SERVER}"
  cp -f "${src_dir}/src/redis-cli" "${REDIS_CLI}"
}

start_local_redis() {
  mkdir -p "${STATE_DIR}"

  if [[ -f "${PIDFILE}" ]]; then
    local pid
    pid="$(cat "${PIDFILE}" || true)"
    if [[ -n "${pid}" ]] && kill -0 "${pid}" >/dev/null 2>&1; then
      echo "redistest: local redis already running (pid=${pid})"
      echo "local" >"${MODEFILE}"
      return 0
    fi
    rm -f "${PIDFILE}"
  fi

  build_redis_if_needed

  : >"${LOGFILE}"
  "${REDIS_SERVER}" \
    --bind 127.0.0.1 \
    --port 6379 \
    --save "" \
    --appendonly no \
    --daemonize yes \
    --pidfile "${PIDFILE}" \
    --logfile "${LOGFILE}"

  for _ in $(seq 1 100); do
    if "${REDIS_CLI}" -p 6379 ping >/dev/null 2>&1; then
      echo "redistest: local redis ready on 127.0.0.1:6379"
      echo "local" >"${MODEFILE}"
      return 0
    fi
    sleep 0.1
  done

  echo "redistest: local redis did not become ready" >&2
  exit 1
}

stop_local_redis() {
  if [[ ! -f "${PIDFILE}" ]]; then
    return 0
  fi

  local pid
  pid="$(cat "${PIDFILE}" || true)"
  rm -f "${PIDFILE}"
  if [[ -z "${pid}" ]]; then
    return 0
  fi

  if kill -0 "${pid}" >/dev/null 2>&1; then
    kill "${pid}" >/dev/null 2>&1 || true
    for _ in $(seq 1 50); do
      if ! kill -0 "${pid}" >/dev/null 2>&1; then
        break
      fi
      sleep 0.1
    done
  fi
}

case "${cmd}" in
  up)
    if docker_available; then
      docker compose -f "${COMPOSE_FILE}" up -d
      mkdir -p "${STATE_DIR}"
      echo "docker" >"${MODEFILE}"
      exit 0
    fi
    start_local_redis
    ;;
  down)
    set +e
    if command -v docker >/dev/null 2>&1; then
      docker compose -f "${COMPOSE_FILE}" down -v >/dev/null 2>&1
    fi
    set -e
    stop_local_redis
    rm -f "${MODEFILE}" "${LOGFILE}"
    ;;
  logs)
    if [[ -f "${MODEFILE}" && "$(cat "${MODEFILE}")" == "docker" ]]; then
      exec docker compose -f "${COMPOSE_FILE}" logs -f --tail=200
    fi
    if [[ -f "${LOGFILE}" ]]; then
      exec tail -f "${LOGFILE}"
    fi
    echo "redistest: no logs available" >&2
    ;;
  *)
    echo "Usage: $0 {up|down|logs}" >&2
    exit 2
    ;;
esac
