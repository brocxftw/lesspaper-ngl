#!/usr/bin/env bash
set -euo pipefail

run_api() {
  echo "Running database migrations..."
  alembic upgrade head
  exec uvicorn lesspaper_ngl.main:app --host 0.0.0.0 --port 8000
}

if [[ "${1:-}" == "lesspaper-ngl-worker" ]] || [[ "${1:-}" == "folium-worker" ]]; then
  exec lesspaper-ngl-worker
fi

if [[ "${1:-}" == "lesspaper-ngl-api" ]] || [[ "${1:-}" == "folium-api" ]] || [[ $# -eq 0 ]]; then
  run_api
fi

exec "$@"
