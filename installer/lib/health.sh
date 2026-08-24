# Bounded health wait. AI endpoints are never part of install success.
# shellcheck shell=bash

health_http_ok() {
  local url="$1"
  local expect="${2:-ok}"
  python3 - "${url}" "${expect}" <<'PY'
import json, sys, urllib.request
url, expect = sys.argv[1], sys.argv[2]
try:
    with urllib.request.urlopen(url, timeout=5) as resp:
        body = resp.read().decode("utf-8", "replace")
        data = json.loads(body)
except Exception:
    sys.exit(1)
status = str(data.get("status", ""))
if expect == "ok":
    sys.exit(0 if status in {"ok", "healthy"} else 1)
sys.exit(0 if status == expect else 1)
PY
}

health_compose_ps_healthy() {
  local line
  local pending=0
  while IFS= read -r line; do
    [[ -n "${line}" ]] || continue
    case "${line}" in
      *\(healthy\)*) ;;
      *) pending=$((pending + 1)) ;;
    esac
  done < <(lesspaper_ngl_compose ps --format '{{.Service}} {{.Status}}' 2>/dev/null || true)
  [[ "${pending}" -eq 0 ]]
}

health_services_present() {
  local out
  out="$(lesspaper_ngl_compose ps 2>/dev/null || true)"
  [[ "${out}" == *db* && "${out}" == *api* && "${out}" == *worker* && "${out}" == *web* ]]
}

health_wait() {
  local retries="${LESSPAPER_NGL_HEALTH_RETRIES:-48}"
  local sleep_s="${LESSPAPER_NGL_HEALTH_SLEEP:-5}"
  local base
  local i
  local ok=0
  base="$(network_health_base)"
  log_info "waiting for health at ${base} (${retries} attempts)"
  for i in $(seq 1 "${retries}"); do
    if declare -F lesspaper_ngl_health_progress >/dev/null 2>&1; then
      lesspaper_ngl_health_progress "${i}" "${retries}"
    fi
    if health_services_present \
      && health_http_ok "${base}/health" "ok" \
      && health_http_ok "${base}/health/database" "ok" \
      && health_http_ok "${base}/health/storage" "ok" \
      && health_http_ok "${base}/health/worker" "healthy"; then
      ok=1
      log_info "application health ok on attempt ${i}"
      break
    fi
    sleep "${sleep_s}"
  done
  if [[ "${ok}" != "1" ]]; then
    log_warn "application health did not become ready"
    return 1
  fi
  return 0
}

health_snapshot() {
  local base
  base="$(network_health_base)"
  printf 'compose:\n'
  lesspaper_ngl_compose ps 2>/dev/null || true
  printf '\nGET /health:\n'
  curl -sf "${base}/health" 2>/dev/null || printf 'unreachable\n'
  printf '\nGET /health/database:\n'
  curl -sf "${base}/health/database" 2>/dev/null || printf 'unreachable\n'
  printf '\nGET /health/storage:\n'
  curl -sf "${base}/health/storage" 2>/dev/null || printf 'unreachable\n'
  printf '\nGET /health/worker:\n'
  curl -sf "${base}/health/worker" 2>/dev/null || printf 'unreachable\n'
}
