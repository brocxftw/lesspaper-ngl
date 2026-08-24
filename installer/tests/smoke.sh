#!/usr/bin/env bash
# Throwaway Compose smoke: non-8080 port, dedicated project name.
# Does not touch the live lesspaper-ngl stack. Does not install /usr/local/bin/lesspaper-ngl.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
REPO_ROOT="$(cd "${ROOT}/.." && pwd)"
SMOKE_DIR="${LESSPAPER_NGL_SMOKE_DIR:-/tmp/lesspaper-ngl-installer-smoke}"
PORT="${LESSPAPER_NGL_HTTP_PORT:-18080}"
PROJECT="${LESSPAPER_NGL_COMPOSE_PROJECT:-lesspaper-ngl-installer-smoke}"

if ss -ltnH "sport = :${PORT}" 2>/dev/null | grep -q .; then
  echo "Port ${PORT} is in use; set LESSPAPER_NGL_HTTP_PORT to a free port." >&2
  exit 1
fi

rm -rf "${SMOKE_DIR}"
mkdir -p "${SMOKE_DIR}"

cleanup() {
  if [[ "${LESSPAPER_NGL_SMOKE_KEEP:-0}" != "1" ]]; then
    (
      cd "${SMOKE_DIR}"
      docker compose -p "${PROJECT}" -f docker-compose.yml -f docker-compose.override.yml down -v >/dev/null 2>&1 || true
    )
    rm -rf "${SMOKE_DIR}"
  fi
}
trap cleanup EXIT

export LESSPAPER_NGL_UI=none
export LESSPAPER_NGL_NONINTERACTIVE=1
export LESSPAPER_NGL_SKIP_CLI=1
export LESSPAPER_NGL_INSTALL_DIR="${SMOKE_DIR}"
export LESSPAPER_NGL_METHOD=image
export LESSPAPER_NGL_VERSION=0.1.16
export LESSPAPER_NGL_VERSION_TAG=v0.1.16
export LESSPAPER_NGL_BIND=127.0.0.1
export LESSPAPER_NGL_HTTP_PORT="${PORT}"
export LESSPAPER_NGL_EXPOSE_API=0
export LESSPAPER_NGL_COMPOSE_PROJECT="${PROJECT}"
export LESSPAPER_NGL_RELEASE_COMPOSE_FILE="${REPO_ROOT}/docker-compose.yml"
export LESSPAPER_NGL_HEALTH_RETRIES="${LESSPAPER_NGL_HEALTH_RETRIES:-36}"
export LESSPAPER_NGL_DOCS_PATH="${SMOKE_DIR}/data/documents"
export LESSPAPER_NGL_CONSUME_PATH="${SMOKE_DIR}/data/consume"
export LESSPAPER_NGL_EXPORT_PATH="${SMOKE_DIR}/data/export"
export LESSPAPER_NGL_PADDLE_PATH="${SMOKE_DIR}/data/paddleocr"
export LESSPAPER_NGL_FRONTEND_ORIGIN="http://127.0.0.1:${PORT}"

bash "${ROOT}/install.sh" --noninteractive

curl -sf "http://127.0.0.1:${PORT}/health"
echo
curl -sf "http://127.0.0.1:${PORT}/health/database"
echo
echo "Smoke install succeeded on ${PROJECT} port ${PORT}."
