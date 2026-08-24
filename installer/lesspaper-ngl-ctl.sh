#!/usr/bin/env bash
# lesspaper-ngl management CLI (installed as /usr/local/bin/lesspaper-ngl; folium shim provided).
# shellcheck disable=SC1091
set -euo pipefail

usage() {
  cat <<'EOF'
Usage: lesspaper-ngl <command>

  status     Compose service status
  start      docker compose up -d
  stop       docker compose stop
  restart    docker compose restart
  logs       docker compose logs (optional service names)
  doctor     System, storage, port, and health checks (does not print .env)
  update     Upgrade install (default: newest beta; or latest / vX.Y.Z[-beta.N])
  uninstall  Not in v1
  help       Show this help

Update examples:
  lesspaper-ngl update                 # newest beta prerelease
  lesspaper-ngl update beta            # same
  lesspaper-ngl update latest          # newest stable
  lesspaper-ngl update v0.1.24-beta.5  # exact pin

Hosts still on an older CLI stub need one installer re-run before update exists.
EOF
}

discover_install_dir() {
  if [[ -n "${LESSPAPER_NGL_INSTALL_DIR:-}" && -f "${LESSPAPER_NGL_INSTALL_DIR}/install-state.json" ]]; then
    printf '%s' "${LESSPAPER_NGL_INSTALL_DIR}"
    return 0
  fi
  if [[ -n "${FOLIUM_INSTALL_DIR:-}" && -f "${FOLIUM_INSTALL_DIR}/install-state.json" ]]; then
    printf '%s' "${FOLIUM_INSTALL_DIR}"
    return 0
  fi
  local p
  if [[ -f /etc/lesspaper-ngl/install-dir ]]; then
    p="$(tr -d '\n' </etc/lesspaper-ngl/install-dir)"
    if [[ -d "${p}" ]]; then
      printf '%s' "${p}"
      return 0
    fi
  fi
  if [[ -f /etc/folium/install-dir ]]; then
    p="$(tr -d '\n' </etc/folium/install-dir)"
    if [[ -d "${p}" ]]; then
      printf '%s' "${p}"
      return 0
    fi
  fi
  if [[ -f /opt/lesspaper-ngl/install-state.json ]]; then
    printf '%s' "/opt/lesspaper-ngl"
    return 0
  fi
  if [[ -f /opt/folium/install-state.json ]]; then
    printf '%s' "/opt/folium"
    return 0
  fi
  return 1
}

load_libs() {
  if [[ "${LESSPAPER_NGL_PACKED:-0}" == "1" ]]; then
    LESSPAPER_NGL_LOG_FILE="${LESSPAPER_NGL_LOG_FILE:-/dev/null}"
    return 0
  fi
  local root=""
  if [[ -f "${LESSPAPER_NGL_INSTALL_DIR}/installer/lib/common.sh" ]]; then
    root="${LESSPAPER_NGL_INSTALL_DIR}/installer"
  else
    root="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
  fi
  if [[ ! -f "${root}/lib/common.sh" ]]; then
    return 1
  fi
  # shellcheck source=lib/common.sh
  source "${root}/lib/common.sh"
  # shellcheck source=lib/logging.sh
  source "${root}/lib/logging.sh"
  LESSPAPER_NGL_LOG_FILE="${LESSPAPER_NGL_LOG_FILE:-/dev/null}"
  # shellcheck source=lib/docker.sh
  source "${root}/lib/docker.sh"
  # shellcheck source=lib/system.sh
  source "${root}/lib/system.sh"
  # shellcheck source=lib/storage.sh
  source "${root}/lib/storage.sh"
  # shellcheck source=lib/network.sh
  source "${root}/lib/network.sh"
  # shellcheck source=lib/state.sh
  source "${root}/lib/state.sh"
  # shellcheck source=lib/health.sh
  source "${root}/lib/health.sh"
  # shellcheck source=lib/ctl_update.sh
  source "${root}/lib/ctl_update.sh"
}

cmd_not_v1() {
  echo "$1 is not available in installer v1." >&2
  exit 2
}

cmd_doctor() {
  echo "== lesspaper-ngl doctor =="
  echo "install_dir=${LESSPAPER_NGL_INSTALL_DIR}"
  echo
  echo "-- system --"
  system_collect_report
  if ! is_amd64; then
    echo "ERROR: architecture is not amd64"
  fi
  if docker_info_ok; then
    echo "docker: ok"
    docker_compose_version || true
  else
    echo "ERROR: docker is not usable"
  fi
  echo
  echo "-- storage --"
  local path
  for path in \
    "$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1])).get("storage",{}).get("documents",""))' "${LESSPAPER_NGL_INSTALL_DIR}/install-state.json" 2>/dev/null || true)" \
    "$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1])).get("storage",{}).get("consume",""))' "${LESSPAPER_NGL_INSTALL_DIR}/install-state.json" 2>/dev/null || true)" \
    "$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1])).get("storage",{}).get("export",""))' "${LESSPAPER_NGL_INSTALL_DIR}/install-state.json" 2>/dev/null || true)" \
    "$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1])).get("storage",{}).get("paddle_cache",""))' "${LESSPAPER_NGL_INSTALL_DIR}/install-state.json" 2>/dev/null || true)"; do
    [[ -n "${path}" ]] || continue
    printf '%s  fstype=%s  uid=%s\n' "${path}" "$(storage_fstype "${path}" 2>/dev/null || echo missing)" "$(storage_uid_of "${path}" 2>/dev/null || echo missing)"
  done
  echo
  echo "-- port --"
  local port
  port="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1])).get("network",{}).get("port",9398))' "${LESSPAPER_NGL_INSTALL_DIR}/install-state.json")"
  LESSPAPER_NGL_HTTP_PORT="${port}"
  if network_port_in_use "${port}"; then
    echo "port ${port} is listening (expected if lesspaper-ngl is up)"
    network_port_users "${port}" || true
  else
    echo "port ${port} is not listening"
  fi
  echo
  echo "-- services --"
  lesspaper_ngl_compose ps || true
  echo
  echo "-- health --"
  health_snapshot
}

# Download a fresh release installer and run noninteractive --update.
cmd_update() {
  local target
  if ! target="$(ctl_update_normalize_target "${1:-}")"; then
    echo "Invalid version '${1:-}'. Use beta, latest, or a pin like v0.1.24-beta.5." >&2
    exit 2
  fi
  if [[ -n "${2:-}" ]]; then
    echo "Unexpected argument: $2" >&2
    usage
    exit 2
  fi
  if [[ ! -f "${LESSPAPER_NGL_INSTALL_DIR}/.env" ]]; then
    echo "No .env in ${LESSPAPER_NGL_INSTALL_DIR}." >&2
    exit 1
  fi
  if [[ ! -f "${LESSPAPER_NGL_INSTALL_DIR}/docker-compose.yml" ]]; then
    echo "No docker-compose.yml in ${LESSPAPER_NGL_INSTALL_DIR}." >&2
    exit 1
  fi

  local url tmp rc=0 asset
  tmp="$(mktemp)"
  # shellcheck disable=SC2064
  trap "rm -f '${tmp}'" EXIT
  url=""
  while IFS= read -r asset; do
    [[ -n "${asset}" ]] || continue
    if ! url="$(ctl_update_installer_url "${target}" "${asset}")"; then
      continue
    fi
    echo "Downloading installer: ${url}" >&2
    if curl -fsSL --max-time 60 -o "${tmp}" "${url}"; then
      break
    fi
    echo "Download failed for ${asset}; trying fallback if available..." >&2
    url=""
  done < <(ctl_update_installer_asset_names)
  if [[ -z "${url}" || ! -s "${tmp}" ]]; then
    echo "Could not download install-lesspaper-ngl.sh or install-folium.sh for '${target}'." >&2
    exit 1
  fi
  chmod 700 "${tmp}"
  echo "Updating ${LESSPAPER_NGL_INSTALL_DIR} to ${target}..." >&2
  LESSPAPER_NGL_INSTALL_DIR="${LESSPAPER_NGL_INSTALL_DIR}" bash "${tmp}" \
    --noninteractive --update --version "${target}" --json || rc=$?
  trap - EXIT
  rm -f "${tmp}"
  return "${rc}"
}

main() {
  local cmd="${1:-status}"
  shift || true
  case "${cmd}" in
    -h|--help|help) usage; exit 0 ;;
    uninstall) cmd_not_v1 uninstall ;;
  esac
  LESSPAPER_NGL_INSTALL_DIR="$(discover_install_dir)" || {
    echo "Could not find a lesspaper-ngl install. Set LESSPAPER_NGL_INSTALL_DIR." >&2
    exit 1
  }
  export LESSPAPER_NGL_INSTALL_DIR
  if [[ -f "${LESSPAPER_NGL_INSTALL_DIR}/install-state.json" ]]; then
    LESSPAPER_NGL_COMPOSE_PROJECT="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1])).get("compose_project","lesspaper-ngl"))' "${LESSPAPER_NGL_INSTALL_DIR}/install-state.json")"
    LESSPAPER_NGL_HTTP_PORT="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1])).get("network",{}).get("port",9398))' "${LESSPAPER_NGL_INSTALL_DIR}/install-state.json")"
    export LESSPAPER_NGL_COMPOSE_PROJECT LESSPAPER_NGL_HTTP_PORT
  fi
  load_libs || {
    echo "Installer libraries were not found under ${LESSPAPER_NGL_INSTALL_DIR}/installer." >&2
    exit 1
  }
  case "${cmd}" in
    status) lesspaper_ngl_compose ps ;;
    start) lesspaper_ngl_compose up -d ;;
    stop) lesspaper_ngl_compose stop ;;
    restart) lesspaper_ngl_compose restart ;;
    logs) lesspaper_ngl_compose logs "$@" ;;
    doctor) cmd_doctor ;;
    update) cmd_update "$@" ;;
    *) usage; exit 2 ;;
  esac
}

main "$@"
