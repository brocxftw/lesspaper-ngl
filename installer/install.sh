#!/usr/bin/env bash
# lesspaper-ngl interactive installer (whiptail TUI).
# shellcheck disable=SC1091
set -euo pipefail

INSTALLER_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
export INSTALLER_ROOT
LESSPAPER_NGL_DEFAULT_INSTALL_DIR="${LESSPAPER_NGL_DEFAULT_INSTALL_DIR:-${INSTALLER_ROOT}}"

if [[ "${LESSPAPER_NGL_PACKED:-0}" != "1" ]]; then
  # shellcheck source=lib/common.sh
  source "${INSTALLER_ROOT}/lib/common.sh"
  # shellcheck source=lib/logging.sh
  source "${INSTALLER_ROOT}/lib/logging.sh"
  # shellcheck source=lib/ui.sh
  source "${INSTALLER_ROOT}/lib/ui.sh"
  # shellcheck source=lib/state.sh
  source "${INSTALLER_ROOT}/lib/state.sh"
  # shellcheck source=lib/system.sh
  source "${INSTALLER_ROOT}/lib/system.sh"
  # shellcheck source=lib/docker.sh
  source "${INSTALLER_ROOT}/lib/docker.sh"
  # shellcheck source=lib/dependencies.sh
  source "${INSTALLER_ROOT}/lib/dependencies.sh"
  # shellcheck source=lib/storage.sh
  source "${INSTALLER_ROOT}/lib/storage.sh"
  # shellcheck source=lib/network.sh
  source "${INSTALLER_ROOT}/lib/network.sh"
  # shellcheck source=lib/config.sh
  source "${INSTALLER_ROOT}/lib/config.sh"
  # shellcheck source=lib/health.sh
  source "${INSTALLER_ROOT}/lib/health.sh"
fi

LESSPAPER_NGL_NONINTERACTIVE="${LESSPAPER_NGL_NONINTERACTIVE:-0}"
LESSPAPER_NGL_KEEP_SECRETS="${LESSPAPER_NGL_KEEP_SECRETS:-0}"
LESSPAPER_NGL_JSON="${LESSPAPER_NGL_JSON:-0}"
LESSPAPER_NGL_MODE="${LESSPAPER_NGL_MODE:-install}"
SHOW_ADMIN_PASSWORD=0
LESSPAPER_NGL_HEALTHY="${LESSPAPER_NGL_HEALTHY:-1}"

on_interrupt() {
  # Set the flag first so any UI retry loop stops immediately.
  LESSPAPER_NGL_INTERRUPTED=1
  export LESSPAPER_NGL_INTERRUPTED
  # Avoid re-entering cleanup if a nested signal arrives.
  trap '' INT TERM
  ui_kill_whiptail_children 2>/dev/null || true
  ui_session_end 2>/dev/null || true
  stty sane </dev/tty 2>/dev/null || stty sane 2>/dev/null || true
  printf '\nInstall cancelled. Existing data was not deleted.\n' >/dev/tty 2>/dev/null \
    || printf '\nInstall cancelled. Existing data was not deleted.\n' >&2
  log_info "interrupted by signal"
  exit 130
}

usage() {
  cat <<'EOF'
Usage: install.sh [options]

Interactive (default): whiptail TUI that writes an install directory,
Compose overlay, and .env, then pulls or builds images and waits for health.

Options:
  --noninteractive       Run without TUI (automation / CI / agents)
  --update               Update an existing install (implies --noninteractive)
  --version <tag>        Pin or alias: vX.Y.Z, X.Y.Z-beta.N, latest, beta
  --preserve-secrets     Keep existing .env secrets (default on update)
  --json                 Print one JSON summary line on completion
  -h, --help             Show this help

Non-interactive environment variables (also see docs/deployment/installer.md):
  LESSPAPER_NGL_VERSION / LESSPAPER_NGL_VERSION_TAG   pinned release, or latest / beta
  LESSPAPER_NGL_INSTALL_DIR                    install root (default /opt/lesspaper-ngl)
  LESSPAPER_NGL_KEEP_SECRETS=1                 preserve secrets when .env exists
  LESSPAPER_NGL_MODE=update|install            force update vs fresh install
  LESSPAPER_NGL_BIND, LESSPAPER_NGL_HTTP_PORT, LESSPAPER_NGL_API_PORT, LESSPAPER_NGL_EXPOSE_API
  FRONTEND_ORIGIN / LESSPAPER_NGL_FRONTEND_ORIGIN
  LESSPAPER_NGL_DOCUMENTS_HOST, LESSPAPER_NGL_CONSUME_HOST, LESSPAPER_NGL_EXPORT_HOST, LESSPAPER_NGL_PADDLE_CACHE_HOST
  LESSPAPER_NGL_SECRET_KEY, LESSPAPER_NGL_ENCRYPTION_KEY, POSTGRES_PASSWORD, LESSPAPER_NGL_ADMIN_*
  COMPOSE_PROJECT_NAME, LESSPAPER_NGL_ACCEPT_RISKY_PATH=1, LESSPAPER_NGL_SKIP_CLI=1
  Legacy FOLIUM_* equivalents are accepted for one cycle.

Examples:
  # Fresh install of newest beta
  bash install-lesspaper-ngl.sh --noninteractive --version beta

  # Update existing install to newest beta (secrets/bind preserved)
  bash install-lesspaper-ngl.sh --noninteractive --update --version beta --json

Exit codes:
  0  success and healthy
  1  install/update failed
  2  bad arguments / config
  3  completed but health checks failed
  130 interrupted
EOF
}

parse_args() {
  while [[ $# -gt 0 ]]; do
    case "$1" in
      --noninteractive)
        LESSPAPER_NGL_NONINTERACTIVE=1
        LESSPAPER_NGL_UI=none
        export LESSPAPER_NGL_UI
        shift
        ;;
      --update)
        LESSPAPER_NGL_NONINTERACTIVE=1
        LESSPAPER_NGL_UI=none
        export LESSPAPER_NGL_UI
        LESSPAPER_NGL_MODE=update
        shift
        ;;
      --version)
        if [[ $# -lt 2 || -z "${2:-}" ]]; then
          echo "Missing value for --version" >&2
          usage
          exit 2
        fi
        LESSPAPER_NGL_VERSION="$2"
        LESSPAPER_NGL_VERSION_TAG="v$(config_strip_v_prefix "$2")"
        # Allow aliases to pass through resolve later (vlatest / vbeta are wrong).
        case "$(config_strip_v_prefix "$2")" in
          latest|beta)
            LESSPAPER_NGL_VERSION="$(config_strip_v_prefix "$2")"
            LESSPAPER_NGL_VERSION_TAG="${LESSPAPER_NGL_VERSION}"
            ;;
        esac
        shift 2
        ;;
      --preserve-secrets)
        LESSPAPER_NGL_KEEP_SECRETS=1
        shift
        ;;
      --json)
        LESSPAPER_NGL_JSON=1
        shift
        ;;
      -h|--help)
        usage
        exit 0
        ;;
      *)
        echo "Unknown argument: $1" >&2
        usage
        exit 2
        ;;
    esac
  done
}

emit_json_summary() {
  [[ "${LESSPAPER_NGL_JSON}" == "1" ]] || return 0
  local healthy_json="false"
  [[ "${LESSPAPER_NGL_HEALTHY:-0}" == "1" ]] && healthy_json="true"
  LESSPAPER_NGL_SUMMARY_HEALTHY="${healthy_json}" \
  LESSPAPER_NGL_VERSION="${LESSPAPER_NGL_VERSION:-}" \
  LESSPAPER_NGL_VERSION_TAG="${LESSPAPER_NGL_VERSION_TAG:-}" \
  LESSPAPER_NGL_INSTALL_DIR="${LESSPAPER_NGL_INSTALL_DIR:-}" \
  LESSPAPER_NGL_FRONTEND_ORIGIN="${LESSPAPER_NGL_FRONTEND_ORIGIN:-}" \
  LESSPAPER_NGL_MODE="${LESSPAPER_NGL_MODE:-install}" \
  python3 -c 'import json,os
print(json.dumps({
  "version": os.environ.get("LESSPAPER_NGL_VERSION",""),
  "version_tag": os.environ.get("LESSPAPER_NGL_VERSION_TAG",""),
  "healthy": os.environ.get("LESSPAPER_NGL_SUMMARY_HEALTHY","false") == "true",
  "install_dir": os.environ.get("LESSPAPER_NGL_INSTALL_DIR",""),
  "frontend_origin": os.environ.get("LESSPAPER_NGL_FRONTEND_ORIGIN",""),
  "mode": os.environ.get("LESSPAPER_NGL_MODE","install"),
}, separators=(",", ":")))'
}

# Print summary (and optional JSON), then exit with the health-aware status code.
finish_noninteractive() {
  success_screen
  emit_json_summary
  if [[ "${LESSPAPER_NGL_HEALTHY:-0}" == "1" ]]; then
    exit 0
  fi
  exit 3
}

ensure_whiptail() {
  if [[ "${LESSPAPER_NGL_UI}" == "none" ]]; then
    return 0
  fi
  if ui_available; then
    return 0
  fi
  printf 'whiptail is not installed. Install it now? [Y/n] '
  local ans=""
  read -r ans || true
  case "${ans}" in
    n|N|no|NO) echo "whiptail is required."; exit 1 ;;
  esac
  dep_install_whiptail
}

abort() {
  local msg="$1"
  log_error "${msg}"
  ui_gauge_stop 2>/dev/null || true
  if [[ "${LESSPAPER_NGL_UI}" == "none" ]]; then
    printf '%s\n' "${msg}" >&2
  else
    ui_msgbox "${msg}"
  fi
  ui_session_end 2>/dev/null || true
  exit 1
}

ensure_docker_ready() {
  if docker_info_ok && docker_compose_ok; then
    log_info "docker ok: $(docker_compose_version)"
    return 0
  fi
  if [[ "${LESSPAPER_NGL_NONINTERACTIVE}" == "1" ]]; then
    abort "Docker Engine and the Compose plugin are required."
  fi
  local choice=""
  LESSPAPER_NGL_UI_NOCANCEL=1
  choice="$(ui_menu "Docker Engine is not running (or Compose is missing).

lesspaper-ngl can run Docker's official install script (get.docker.com). This requires root, adds Docker's apt/yum repository, and starts the docker service.

Ctrl+C cancels the installer." \
    install "Install Docker Engine now" \
    exit "Exit installer")" || abort "Docker is required."
  LESSPAPER_NGL_UI_NOCANCEL=0
  if [[ "${choice}" != "install" ]]; then
    abort "Docker is required. Install Docker, then re-run this installer."
  fi
  ui_gauge_start "Installing Docker Engine..."
  ui_gauge_update 20 "Running get.docker.com (output in log)"
  local rc=0
  dep_install_docker_engine >>"${LESSPAPER_NGL_LOG_FILE}" 2>&1 || rc=$?
  ui_gauge_stop
  if [[ "${rc}" -ne 0 ]]; then
    abort "Docker installation failed. See ${LESSPAPER_NGL_LOG_FILE}."
  fi
  if ! docker_info_ok || ! docker_compose_ok; then
    abort "Docker is installed but not usable yet. You may need to log out and back in, then re-run the installer."
  fi
}

prompt_existing() {
  local dir="$1"
  local current_ver=""
  local choice=""
  current_ver="$(config_env_get_any LESSPAPER_NGL_VERSION FOLIUM_VERSION -- "${dir}/.env" 2>/dev/null || true)"
  if [[ -z "${current_ver}" ]]; then
    current_ver="$(LESSPAPER_NGL_INSTALL_DIR="${dir}" state_read_field version 2>/dev/null || true)"
  fi
  LESSPAPER_NGL_UI_NOCANCEL=1
  choice="$(ui_menu "lesspaper-ngl is already installed in:
${dir}
${current_ver:+Current version: ${current_ver}}

Update pulls the selected release images and restarts the stack (keeps data and .env secrets).
Reconfigure walks through settings again.
Repair restarts the stack and waits for health without rewriting .env.

Ctrl+C cancels." \
    update "Update (pull release images)" \
    reconfigure "Reconfigure" \
    repair "Repair (re-up + health)" \
    exit "Exit")"
  LESSPAPER_NGL_UI_NOCANCEL=0
  case "${choice}" in
    update) LESSPAPER_NGL_MODE=update ;;
    reconfigure) LESSPAPER_NGL_MODE=reconfigure ;;
    repair) LESSPAPER_NGL_MODE=repair ;;
    *) ui_session_end; exit 0 ;;
  esac
}

discover_existing_install() {
  local dir=""
  dir="$(state_discover_dir || true)"
  if [[ -z "${dir}" && -f "${LESSPAPER_NGL_DEFAULT_INSTALL_DIR}/docker-compose.yml" ]]; then
    dir="${LESSPAPER_NGL_DEFAULT_INSTALL_DIR}"
  fi
  if [[ -z "${dir}" && -f "${LESSPAPER_NGL_DEFAULT_INSTALL_DIR}/.env" ]]; then
    dir="${LESSPAPER_NGL_DEFAULT_INSTALL_DIR}"
  fi
  [[ -n "${dir}" ]] || return 1
  printf '%s' "${dir}"
}

load_existing_defaults() {
  # CLI --version / process env must win over install-state and .env (issue #65).
  local prior_version="${LESSPAPER_NGL_VERSION:-}"
  local prior_version_tag="${LESSPAPER_NGL_VERSION_TAG:-}"

  LESSPAPER_NGL_INSTALL_DIR="${LESSPAPER_NGL_INSTALL_DIR:-$(state_discover_dir || true)}"
  LESSPAPER_NGL_INSTALL_DIR="${LESSPAPER_NGL_INSTALL_DIR:-${LESSPAPER_NGL_DEFAULT_INSTALL_DIR}}"
  if [[ -f "${LESSPAPER_NGL_INSTALL_DIR}/install-state.json" ]]; then
    LESSPAPER_NGL_METHOD="$(state_read_field install_method || true)"
    LESSPAPER_NGL_VERSION="$(state_read_field version || true)"
    LESSPAPER_NGL_VERSION_TAG="$(state_read_field version_tag || true)"
    LESSPAPER_NGL_BIND="$(state_read_field network.bind || true)"
    LESSPAPER_NGL_HTTP_PORT="$(state_read_field network.port || true)"
    LESSPAPER_NGL_FRONTEND_ORIGIN="$(state_read_field network.frontend_origin || true)"
    LESSPAPER_NGL_DOCS_PATH="$(state_read_field storage.documents || true)"
    LESSPAPER_NGL_CONSUME_PATH="$(state_read_field storage.consume || true)"
    LESSPAPER_NGL_EXPORT_PATH="$(state_read_field storage.export || true)"
    LESSPAPER_NGL_PADDLE_PATH="$(state_read_field storage.paddle_cache || true)"
    LESSPAPER_NGL_EXTRA_GID="$(state_read_field extra_gid || true)"
    LESSPAPER_NGL_COMPOSE_PROJECT="$(state_read_field compose_project || true)"
    if [[ "$(state_read_field network.expose_api || true)" == "true" ]]; then
      LESSPAPER_NGL_EXPOSE_API=1
    fi
    LESSPAPER_NGL_API_PORT="$(state_read_field network.api_port || true)"
  fi
  if [[ -f "${LESSPAPER_NGL_INSTALL_DIR}/.env" ]]; then
    LESSPAPER_NGL_KEEP_SECRETS=1
    LESSPAPER_NGL_SECRET_KEY="$(config_env_get_any LESSPAPER_NGL_SECRET_KEY FOLIUM_SECRET_KEY || true)"
    LESSPAPER_NGL_ENCRYPTION_KEY="$(config_env_get_any LESSPAPER_NGL_ENCRYPTION_KEY FOLIUM_ENCRYPTION_KEY || true)"
    POSTGRES_PASSWORD="$(config_env_get POSTGRES_PASSWORD || true)"
    LESSPAPER_NGL_ADMIN_PASSWORD="$(config_env_get_any LESSPAPER_NGL_ADMIN_PASSWORD FOLIUM_ADMIN_PASSWORD || true)"
    LESSPAPER_NGL_ADMIN_USERNAME="$(config_env_get_any LESSPAPER_NGL_ADMIN_USERNAME FOLIUM_ADMIN_USERNAME || true)"
    LESSPAPER_NGL_VERSION="$(config_env_get_any LESSPAPER_NGL_VERSION FOLIUM_VERSION || printf '%s' "${LESSPAPER_NGL_VERSION:-}")"
    LESSPAPER_NGL_FRONTEND_ORIGIN="$(config_env_get FRONTEND_ORIGIN || printf '%s' "${LESSPAPER_NGL_FRONTEND_ORIGIN:-}")"
    LESSPAPER_NGL_BIND="$(config_env_get_any LESSPAPER_NGL_BIND FOLIUM_BIND || printf '%s' "${LESSPAPER_NGL_BIND:-}")"
    LESSPAPER_NGL_HTTP_PORT="$(config_env_get_any LESSPAPER_NGL_HTTP_PORT FOLIUM_HTTP_PORT || printf '%s' "${LESSPAPER_NGL_HTTP_PORT:-}")"
    LESSPAPER_NGL_API_PORT="$(config_env_get_any LESSPAPER_NGL_API_PORT FOLIUM_API_PORT || printf '%s' "${LESSPAPER_NGL_API_PORT:-}")"
    # Always hydrate compose project from existing .env/state on update — never force-rename.
    LESSPAPER_NGL_COMPOSE_PROJECT="$(config_env_get COMPOSE_PROJECT_NAME || printf '%s' "${LESSPAPER_NGL_COMPOSE_PROJECT:-}")"
    LESSPAPER_NGL_DOCS_PATH="$(config_env_get_any LESSPAPER_NGL_DOCUMENTS_HOST FOLIUM_DOCUMENTS_HOST || printf '%s' "${LESSPAPER_NGL_DOCS_PATH:-}")"
    LESSPAPER_NGL_CONSUME_PATH="$(config_env_get_any LESSPAPER_NGL_CONSUME_HOST FOLIUM_CONSUME_HOST || printf '%s' "${LESSPAPER_NGL_CONSUME_PATH:-}")"
    LESSPAPER_NGL_EXPORT_PATH="$(config_env_get_any LESSPAPER_NGL_EXPORT_HOST FOLIUM_EXPORT_HOST || printf '%s' "${LESSPAPER_NGL_EXPORT_PATH:-}")"
    LESSPAPER_NGL_PADDLE_PATH="$(config_env_get_any LESSPAPER_NGL_PADDLE_CACHE_HOST FOLIUM_PADDLE_CACHE_HOST || printf '%s' "${LESSPAPER_NGL_PADDLE_PATH:-}")"
  fi

  if [[ -n "${prior_version}" || -n "${prior_version_tag}" ]]; then
    config_prefer_requested_version "${prior_version}" "${prior_version_tag}"
  else
    # .env may pin LESSPAPER_NGL_VERSION while install-state still has an older version_tag;
    # resolve prefers TAG, so keep the pair consistent when using persisted defaults.
    config_sync_version_tag
  fi
}

wizard_method() {
  local choice=""
  choice="$(ui_menu "How should lesspaper-ngl be installed?

Pre-built images pull ghcr.io/brocxftw/lesspaper-ngl-* for the selected release (recommended).
Build from source clones that release tag and builds images locally. Git is required.

Use Back to return to the previous screen. Ctrl+C exits." \
    image "Pre-built image (recommended)" \
    source "Build from source" \
    back "Back")" || return "${UI_BACK}"
  if [[ "${choice}" == "back" ]]; then
    return "${UI_BACK}"
  fi
  LESSPAPER_NGL_METHOD="${choice}"
  return "${UI_OK}"
}

wizard_version() {
  local latest tags choice=""
  latest="$(github_latest_tag || true)"
  tags="$(github_release_tags || true)"
  if [[ -z "${tags}" && -z "${latest}" ]]; then
    LESSPAPER_NGL_VERSION_TAG="$(ui_input "Could not list GitHub Releases. Enter a version tag (for example v0.1.24-beta.1):" "${LESSPAPER_NGL_VERSION_TAG:-v0.1.24-beta.1}")" || return "${UI_BACK}"
  else
    local -a ordered=()
    local -a menu_items=()
    local tag
    if [[ -n "${latest}" ]] && grep -qxF "${latest}" <<<"${tags}"; then
      ordered+=("${latest}")
    elif [[ -n "${latest}" && -z "${tags}" ]]; then
      ordered+=("${latest}")
    fi
    while IFS= read -r tag; do
      [[ -n "${tag}" && "${tag}" != "${latest}" ]] || continue
      ordered+=("${tag}")
    done <<<"${tags}"
    for tag in "${ordered[@]}"; do
      menu_items+=("${tag}" "$(github_release_menu_label "${tag}" "${latest}")")
    done
    choice="$(ui_menu "Select a lesspaper-ngl release. The installer pins this version (never stores 'latest'). Beta tags are prereleases." "${menu_items[@]}")" || return "${UI_BACK}"
    LESSPAPER_NGL_VERSION_TAG="${choice}"
  fi
  LESSPAPER_NGL_VERSION="$(config_strip_v_prefix "${LESSPAPER_NGL_VERSION_TAG}")"
  if [[ "${LESSPAPER_NGL_VERSION}" == "latest" || "${LESSPAPER_NGL_VERSION}" == "beta" ]] || ! config_is_pinned_version "${LESSPAPER_NGL_VERSION}"; then
    ui_msgbox "Refusing to install an unpinned version (${LESSPAPER_NGL_VERSION_TAG}). Choose a vX.Y.Z or vX.Y.Z-beta.N release."
    return 1
  fi
  return "${UI_OK}"
}

wizard_directory() {
  local dir=""
  dir="$(ui_input "Install directory:" "${LESSPAPER_NGL_INSTALL_DIR:-${LESSPAPER_NGL_DEFAULT_INSTALL_DIR}}")" || return "${UI_BACK}"
  dir="$(storage_normalize_path "${dir}")"
  if storage_is_critical_forbidden_path "${dir}"; then
    ui_msgbox "Refusing to install into ${dir}. Choose another directory."
    return 1
  fi
  if ! storage_validate_install_path "${dir}"; then
    if storage_is_risky_install_path "${dir}"; then
      ui_msgbox "Refusing to install into ${dir} without accepting the risk.

Set LESSPAPER_NGL_ACCEPT_RISKY_PATH=1 for non-interactive installs under /root or /tmp."
    else
      ui_msgbox "Refusing to install into ${dir}. Choose another directory."
    fi
    return 1
  fi
  LESSPAPER_NGL_INSTALL_DIR="${dir}"
  LESSPAPER_NGL_COMPOSE_PROJECT="${LESSPAPER_NGL_COMPOSE_PROJECT:-${LESSPAPER_NGL_DEFAULT_PROJECT}}"
  return "${UI_OK}"
}

wizard_storage_kind() {
  local choice=""
  choice="$(ui_menu "Where should document files live?

Managed directories are created under the install directory.
Existing host paths are used as-is (including NFS/CIFS mounts already on this host). The installer will not edit /etc/fstab." \
    managed "Managed paths under the install directory" \
    existing "Use existing host paths" \
    back "Back")" || return "${UI_BACK}"
  if [[ "${choice}" == "back" ]]; then
    return "${UI_BACK}"
  fi
  LESSPAPER_NGL_STORAGE_KIND="${choice}"
  if [[ "${choice}" == "managed" ]]; then
    LESSPAPER_NGL_DOCS_PATH="$(storage_normalize_path "${LESSPAPER_NGL_INSTALL_DIR}/data/documents")"
    LESSPAPER_NGL_CONSUME_PATH="$(storage_normalize_path "${LESSPAPER_NGL_INSTALL_DIR}/data/consume")"
    LESSPAPER_NGL_EXPORT_PATH="$(storage_normalize_path "${LESSPAPER_NGL_INSTALL_DIR}/data/export")"
  fi
  LESSPAPER_NGL_PADDLE_PATH="${LESSPAPER_NGL_INSTALL_DIR}/data/paddleocr"
  return "${UI_OK}"
}

wizard_storage_paths() {
  local docs consume export_path
  docs="$(ui_input "Documents host path:" "${LESSPAPER_NGL_DOCS_PATH:-${LESSPAPER_NGL_INSTALL_DIR}/data/documents}")" || return "${UI_BACK}"
  consume="$(ui_input "Consume (drop folder) host path:" "${LESSPAPER_NGL_CONSUME_PATH:-${LESSPAPER_NGL_INSTALL_DIR}/data/consume}")" || return "${UI_BACK}"
  export_path="$(ui_input "Export host path:" "${LESSPAPER_NGL_EXPORT_PATH:-${LESSPAPER_NGL_INSTALL_DIR}/data/export}")" || return "${UI_BACK}"
  LESSPAPER_NGL_DOCS_PATH="$(storage_normalize_path "${docs}")"
  LESSPAPER_NGL_CONSUME_PATH="$(storage_normalize_path "${consume}")"
  LESSPAPER_NGL_EXPORT_PATH="$(storage_normalize_path "${export_path}")"
  LESSPAPER_NGL_PADDLE_PATH="${LESSPAPER_NGL_INSTALL_DIR}/data/paddleocr"
  local p
  for p in "${LESSPAPER_NGL_DOCS_PATH}" "${LESSPAPER_NGL_CONSUME_PATH}" "${LESSPAPER_NGL_EXPORT_PATH}" "${LESSPAPER_NGL_PADDLE_PATH}"; do
    if ! storage_validate_bind_path "${p}"; then
      ui_msgbox "Refusing storage path ${p}. Choose another path."
      return 1
    fi
  done
  return "${UI_OK}"
}

wizard_extra_gid() {
  local gid_raw=""
  gid_raw="$(ui_input "Optional extra host GID for 0770 CIFS binds (leave empty for none):" "${LESSPAPER_NGL_EXTRA_GID:-}")" || return "${UI_BACK}"
  if [[ -n "${gid_raw}" && ! "${gid_raw}" =~ ^[0-9]+$ ]]; then
    ui_msgbox "Extra GID must be numeric (or empty)."
    return 1
  fi
  LESSPAPER_NGL_EXTRA_GID="${gid_raw}"
  return "${UI_OK}"
}

wizard_bind() {
  local bind_choice=""
  bind_choice="$(ui_menu "Who should be able to open the UI?

LAN bind (0.0.0.0) listens on all interfaces.
Localhost (127.0.0.1) is for this host or a reverse proxy on the same machine." \
    lan "LAN — bind 0.0.0.0" \
    local "Localhost — bind 127.0.0.1" \
    back "Back")" || return "${UI_BACK}"
  if [[ "${bind_choice}" == "back" ]]; then
    return "${UI_BACK}"
  fi
  if [[ "${bind_choice}" == "local" ]]; then
    LESSPAPER_NGL_BIND="127.0.0.1"
  else
    LESSPAPER_NGL_BIND="0.0.0.0"
  fi
  return "${UI_OK}"
}

wizard_http_port() {
  local port="${LESSPAPER_NGL_HTTP_PORT:-${LESSPAPER_NGL_DEFAULT_HTTP_PORT}}"
  local users=""
  while true; do
    port="$(ui_input "HTTP port for the UI:" "${port}")" || return "${UI_BACK}"
    if ! network_port_valid "${port}"; then
      ui_msgbox "Invalid port: ${port}

Enter a number from 1 to 65535."
      continue
    fi
    if network_port_blocked "${port}"; then
      users="$(network_port_users "${port}" || true)"
      ui_msgbox "Port ${port} is already in use.

${users}

Enter a different HTTP port."
      continue
    fi
    LESSPAPER_NGL_HTTP_PORT="${port}"
    return "${UI_OK}"
  done
}

wizard_expose_api() {
  local choice=""
  LESSPAPER_NGL_API_PORT="${LESSPAPER_NGL_API_PORT:-${LESSPAPER_NGL_DEFAULT_API_PORT}}"
  choice="$(ui_menu "Publish the API/OpenAPI port on ${LESSPAPER_NGL_BIND} as well?

The UI already proxies /api and /health. Leave this off unless you need OpenAPI from other hosts." \
    no "No (recommended)" \
    yes "Yes, publish OpenAPI" \
    back "Back")" || return "${UI_BACK}"
  if [[ "${choice}" == "back" ]]; then
    return "${UI_BACK}"
  fi
  if [[ "${choice}" != "yes" ]]; then
    LESSPAPER_NGL_EXPOSE_API=0
    return "${UI_OK}"
  fi
  LESSPAPER_NGL_EXPOSE_API=1
  local port="${LESSPAPER_NGL_API_PORT:-${LESSPAPER_NGL_DEFAULT_API_PORT}}"
  local users=""
  while true; do
    port="$(ui_input "Host port to publish for OpenAPI (container stays 8000):" "${port}")" || return "${UI_BACK}"
    if ! network_port_valid "${port}"; then
      ui_msgbox "Invalid port: ${port}

Enter a number from 1 to 65535."
      continue
    fi
    if [[ "${port}" == "${LESSPAPER_NGL_HTTP_PORT}" ]]; then
      ui_msgbox "Port ${port} is already chosen for the UI. Pick another port."
      continue
    fi
    if network_port_blocked "${port}"; then
      users="$(network_port_users "${port}" || true)"
      ui_msgbox "Port ${port} is already in use.

${users}

Enter a different host port."
      continue
    fi
    LESSPAPER_NGL_API_PORT="${port}"
    return "${UI_OK}"
  done
}

wizard_origin() {
  local choice="" origin=""
  choice="$(ui_menu "Browser origin (FRONTEND_ORIGIN)

List every URL you will open in a browser (comma-separated). Include reverse-proxy URLs and direct LAN URLs if you use both.

The installer does not install Caddy or nginx on the host." \
    default "Default from bind address and port" \
    custom "Enter custom origin(s)" \
    back "Back")" || return "${UI_BACK}"
  if [[ "${choice}" == "back" ]]; then
    return "${UI_BACK}"
  fi
  if [[ "${choice}" == "default" ]]; then
    LESSPAPER_NGL_FRONTEND_ORIGIN="$(network_origin_for "${LESSPAPER_NGL_BIND}" "${LESSPAPER_NGL_HTTP_PORT}" "")"
    return "${UI_OK}"
  fi
  origin="$(ui_input "Origins (comma-separated, no spaces after commas):" "${LESSPAPER_NGL_FRONTEND_ORIGIN:-https://docs.example.com,http://192.168.1.1:${LESSPAPER_NGL_HTTP_PORT}}")" || return "${UI_BACK}"
  origin="$(printf '%s' "${origin}" | tr -d ' ')"
  if [[ -z "${origin}" ]]; then
    ui_msgbox "At least one origin is required."
    return 1
  fi
  LESSPAPER_NGL_FRONTEND_ORIGIN="${origin}"
  return "${UI_OK}"
}

wizard_secrets() {
  LESSPAPER_NGL_ADMIN_USERNAME="${LESSPAPER_NGL_ADMIN_USERNAME:-admin}"
  if [[ "${LESSPAPER_NGL_KEEP_SECRETS}" == "1" && -n "${LESSPAPER_NGL_SECRET_KEY:-}" ]]; then
    local choice=""
    choice="$(ui_menu "Keep existing secrets and admin password in .env?

Choosing No generates new keys. That does not rotate an already-bootstrapped admin account." \
      keep "Keep existing secrets" \
      rotate "Generate new secrets" \
      back "Back")" || return "${UI_BACK}"
    if [[ "${choice}" == "back" ]]; then
      return "${UI_BACK}"
    fi
    if [[ "${choice}" == "keep" ]]; then
      SHOW_ADMIN_PASSWORD=0
      return "${UI_OK}"
    fi
  fi
  LESSPAPER_NGL_SECRET_KEY="$(config_generate_secret 32)"
  LESSPAPER_NGL_ENCRYPTION_KEY="$(config_generate_secret 32)"
  POSTGRES_PASSWORD="$(config_generate_secret 24)"
  LESSPAPER_NGL_ADMIN_PASSWORD="$(config_generate_secret 12)"
  if ! config_postgres_password_ok "${POSTGRES_PASSWORD}"; then
    abort "Generated database password contained a reserved character. Re-run the installer."
  fi
  SHOW_ADMIN_PASSWORD=1
  return "${UI_OK}"
}

wizard_summary() {
  local summary_file rc=0
  summary_file="$(mktemp)"
  config_render_summary >"${summary_file}"
  ui_confirm_summary_file "${summary_file}" || rc=$?
  rm -f "${summary_file}"
  case "${rc}" in
    0) return "${UI_OK}" ;;
    "${UI_CANCEL}")
      ui_session_end
      exit 0
      ;;
    *) return "${UI_BACK}" ;;
  esac
}

# Return 1 from a step to stay on that screen (validation failed).
wizard_dispatch() {
  local step="$1"
  local rc=0
  set +e
  case "${step}" in
    0) wizard_method ;;
    1) wizard_version ;;
    2) wizard_directory ;;
    3) wizard_storage_kind ;;
    4) wizard_storage_paths ;;
    5) wizard_extra_gid ;;
    6) wizard_bind ;;
    7) wizard_http_port ;;
    8) wizard_expose_api ;;
    9) wizard_origin ;;
    10) wizard_secrets ;;
    11) wizard_summary ;;
    *) rc=0 ;;
  esac
  rc=$?
  set -e
  return "${rc}"
}

wizard_skip_paths() {
  [[ "${LESSPAPER_NGL_STORAGE_KIND:-managed}" == "managed" ]]
}

run_wizard() {
  local step=0
  local rc=0
  LESSPAPER_NGL_STORAGE_KIND="${LESSPAPER_NGL_STORAGE_KIND:-managed}"
  LESSPAPER_NGL_UI_NOCANCEL=0
  LESSPAPER_NGL_UI_CANCEL_LABEL="Back"
  LESSPAPER_NGL_UI_OK_LABEL="OK"
  while true; do
    if [[ "${LESSPAPER_NGL_INTERRUPTED}" == "1" ]]; then
      exit 130
    fi
    rc=0
    wizard_dispatch "${step}" || rc=$?
    case "${rc}" in
      0)
        if [[ "${step}" -eq 11 ]]; then
          return 0
        fi
        step=$((step + 1))
        if [[ "${step}" -eq 4 ]] && wizard_skip_paths; then
          step=5
        fi
        ;;
      1)
        # Stay on this screen after a validation msgbox.
        ;;
      2)
        if [[ "${step}" -le 0 ]]; then
          step=0
        else
          step=$((step - 1))
          if [[ "${step}" -eq 4 ]] && wizard_skip_paths; then
            step=3
          fi
        fi
        ;;
      "${UI_CANCEL}")
        ui_session_end
        exit 0
        ;;
      130) exit 130 ;;
      *) abort "Unexpected installer state (${rc})." ;;
    esac
  done
}

apply_storage() {
  local path fst chown_now suggested_gid
  for path in "${LESSPAPER_NGL_DOCS_PATH}" "${LESSPAPER_NGL_CONSUME_PATH}" "${LESSPAPER_NGL_EXPORT_PATH}" "${LESSPAPER_NGL_PADDLE_PATH}"; do
    if [[ ! -d "${path}" ]]; then
      run_root mkdir -p "${path}"
    fi
    fst="$(storage_fstype "${path}" || true)"
    if storage_is_remote_fstype "${fst}"; then
      log_info "path ${path} fstype=${fst} (remote-backed, ok)"
    fi
    if storage_writable_by_app_user "${path}"; then
      continue
    fi
    chown_now=0
    if [[ "${LESSPAPER_NGL_NONINTERACTIVE}" == "1" ]]; then
      chown_now=1
    else
      local choice=""
      LESSPAPER_NGL_UI_NOCANCEL=1
      choice="$(ui_menu "${path} is not writable by UID ${LESSPAPER_NGL_APP_UID} (the container user).

Allow chown ${LESSPAPER_NGL_APP_UID}:${LESSPAPER_NGL_APP_GID} on this directory? lesspaper-ngl will not chmod 777.

Ctrl+C cancels." \
        chown "chown ${LESSPAPER_NGL_APP_UID}:${LESSPAPER_NGL_APP_GID}" \
        abort "Abort install")"
      LESSPAPER_NGL_UI_NOCANCEL=0
      if [[ "${choice}" == "chown" ]]; then
        chown_now=1
      else
        abort "Storage path ${path} is not writable by UID ${LESSPAPER_NGL_APP_UID}."
      fi
    fi
    if [[ "${chown_now}" == "1" ]]; then
      run_root chown "${LESSPAPER_NGL_APP_UID}:${LESSPAPER_NGL_APP_GID}" "${path}"
    fi
    if storage_writable_by_app_user "${path}"; then
      continue
    fi
    suggested_gid="$(storage_gid_of "${path}" 2>/dev/null || true)"
    if [[ -n "${suggested_gid}" && "${suggested_gid}" != "${LESSPAPER_NGL_APP_GID}" && -z "${LESSPAPER_NGL_EXTRA_GID:-}" ]]; then
      if [[ "${LESSPAPER_NGL_NONINTERACTIVE}" == "1" ]]; then
        LESSPAPER_NGL_EXTRA_GID="${suggested_gid}"
        log_info "auto-selected extra GID ${suggested_gid} for ${path}"
      else
        local gid_choice=""
        LESSPAPER_NGL_UI_NOCANCEL=1
        gid_choice="$(ui_menu "${path} is still not writable after chown.

Directory group GID is ${suggested_gid}. CIFS/NFS paths with mode 0770 often need group_add in Compose.

Add GID ${suggested_gid} as an extra container group?" \
          yes "Add GID ${suggested_gid}" \
          abort "Abort install")"
        LESSPAPER_NGL_UI_NOCANCEL=0
        if [[ "${gid_choice}" == "yes" ]]; then
          LESSPAPER_NGL_EXTRA_GID="${suggested_gid}"
        else
          abort "Storage path ${path} is not writable. Configure LESSPAPER_NGL_EXTRA_GID for 0770 CIFS binds."
        fi
      fi
    fi
    if storage_writable_by_app_user "${path}"; then
      continue
    fi
    abort "Storage path ${path} is still not writable by UID ${LESSPAPER_NGL_APP_UID}. For 0770 CIFS binds set LESSPAPER_NGL_EXTRA_GID to the directory group GID."
  done
}

fetch_compose() {
  local dest="${LESSPAPER_NGL_INSTALL_DIR}/docker-compose.yml"
  mkdir -p "${LESSPAPER_NGL_INSTALL_DIR}"
  if [[ -n "${LESSPAPER_NGL_RELEASE_COMPOSE_FILE:-}" ]]; then
    cp "${LESSPAPER_NGL_RELEASE_COMPOSE_FILE}" "${dest}"
  else
    config_download "$(github_asset_url "${LESSPAPER_NGL_VERSION_TAG}" "docker-compose.yml")" "${dest}"
  fi
  config_strip_compose_ports "${dest}"
}

prepare_source() {
  if ! require_cmd git; then
    ui_gauge_stop 2>/dev/null || true
    dep_install_git >>"${LESSPAPER_NGL_LOG_FILE}" 2>&1 || abort "git is required to build from source."
  fi
  mkdir -p "${LESSPAPER_NGL_INSTALL_DIR}"
  if [[ -d "${LESSPAPER_NGL_INSTALL_DIR}/src/.git" ]]; then
    git -C "${LESSPAPER_NGL_INSTALL_DIR}/src" fetch --tags >>"${LESSPAPER_NGL_LOG_FILE}" 2>&1 \
      || abort "git fetch failed. See ${LESSPAPER_NGL_LOG_FILE}."
    git -C "${LESSPAPER_NGL_INSTALL_DIR}/src" checkout "${LESSPAPER_NGL_VERSION_TAG}" >>"${LESSPAPER_NGL_LOG_FILE}" 2>&1 \
      || abort "git checkout ${LESSPAPER_NGL_VERSION_TAG} failed. See ${LESSPAPER_NGL_LOG_FILE}."
  else
    rm -rf "${LESSPAPER_NGL_INSTALL_DIR}/src"
    git clone --branch "${LESSPAPER_NGL_VERSION_TAG}" --depth 1 \
      "${LESSPAPER_NGL_GITHUB_URL}.git" "${LESSPAPER_NGL_INSTALL_DIR}/src" >>"${LESSPAPER_NGL_LOG_FILE}" 2>&1 \
      || abort "git clone failed. See ${LESSPAPER_NGL_LOG_FILE}."
  fi
  config_write_source_overlay
}

install_cli() {
  mkdir -p "${LESSPAPER_NGL_INSTALL_DIR}/installer"
  if [[ "${LESSPAPER_NGL_PACKED:-0}" == "1" ]]; then
    lesspaper_ngl_install_packed_ctl
  else
    cp -a "${INSTALLER_ROOT}/install.sh" "${LESSPAPER_NGL_INSTALL_DIR}/installer/"
    cp -a "${INSTALLER_ROOT}/lesspaper-ngl-ctl.sh" "${LESSPAPER_NGL_INSTALL_DIR}/installer/"
    cp -a "${INSTALLER_ROOT}/lib" "${LESSPAPER_NGL_INSTALL_DIR}/installer/"
    cp -a "${INSTALLER_ROOT}/templates" "${LESSPAPER_NGL_INSTALL_DIR}/installer/"
    if [[ -f "${INSTALLER_ROOT}/pack.sh" ]]; then
      cp -a "${INSTALLER_ROOT}/pack.sh" "${LESSPAPER_NGL_INSTALL_DIR}/installer/"
    fi
    run_root install -m 755 "${INSTALLER_ROOT}/lesspaper-ngl-ctl.sh" /usr/local/bin/lesspaper-ngl
    # Compat shim for existing operator muscle memory / docs.
    local shim
    shim="$(mktemp)"
    cat >"${shim}" <<'SHIM'
#!/usr/bin/env bash
exec /usr/local/bin/lesspaper-ngl "$@"
SHIM
    chmod 755 "${shim}"
    run_root install -m 755 "${shim}" /usr/local/bin/folium
    rm -f "${shim}"
  fi
  state_write_pointer
}

ensure_install_dir() {
  run_root mkdir -p "${LESSPAPER_NGL_INSTALL_DIR}/backups" "${LESSPAPER_NGL_INSTALL_DIR}/data"
  if ! is_root; then
    run_root chown "$(id -u):$(id -g)" "${LESSPAPER_NGL_INSTALL_DIR}" "${LESSPAPER_NGL_INSTALL_DIR}/backups" "${LESSPAPER_NGL_INSTALL_DIR}/data"
  fi
}

run_install_cmd() {
  log_cmd "$*"
  if [[ "${LESSPAPER_NGL_UI}" == "none" ]]; then
    "$@"
  else
    "$@" >>"${LESSPAPER_NGL_LOG_FILE}" 2>&1
  fi
}

lesspaper_ngl_health_progress() {
  local i="$1"
  local n="$2"
  local pct=$((75 + (i * 20 / n)))
  if [[ "${pct}" -gt 95 ]]; then
    pct=95
  fi
  ui_gauge_update "${pct}" "Waiting for health (${i}/${n})..."
}

execute_install() {
  log_info "execute_install method=${LESSPAPER_NGL_METHOD} version=${LESSPAPER_NGL_VERSION}"
  LESSPAPER_NGL_API_PORT="${LESSPAPER_NGL_API_PORT:-${LESSPAPER_NGL_DEFAULT_API_PORT}}"
  ensure_install_dir
  if [[ "${LESSPAPER_NGL_MODE}" == "reconfigure" ]]; then
    config_backup_install_dir
  fi
  apply_storage

  ui_gauge_start "Installing lesspaper-ngl ${LESSPAPER_NGL_VERSION}..."
  ui_gauge_update 10 "Writing Compose files..."
  fetch_compose
  config_write_override
  if [[ "${LESSPAPER_NGL_METHOD}" == "source" ]]; then
    ui_gauge_update 20 "Cloning source ${LESSPAPER_NGL_VERSION_TAG}..."
    prepare_source
  else
    rm -f "${LESSPAPER_NGL_INSTALL_DIR}/compose.source.yaml"
  fi
  ui_gauge_update 30 "Writing .env..."
  config_write_env
  if ! config_compose_validate; then
    ui_gauge_stop
    abort "docker compose config failed. See ${LESSPAPER_NGL_LOG_FILE}."
  fi
  if [[ "${LESSPAPER_NGL_METHOD}" == "source" ]]; then
    ui_gauge_update 40 "Building images (this may take several minutes)..."
    log_info "building images from source"
    if ! run_install_cmd lesspaper_ngl_compose build; then
      ui_gauge_stop
      abort "Image build failed. See ${LESSPAPER_NGL_LOG_FILE}."
    fi
  else
    ui_gauge_update 40 "Pulling images (this may take several minutes)..."
    log_info "pulling images"
    if ! run_install_cmd lesspaper_ngl_compose pull; then
      ui_gauge_stop
      abort "Image pull failed. See ${LESSPAPER_NGL_LOG_FILE}."
    fi
  fi
  ui_gauge_update 70 "Starting services..."
  if ! run_install_cmd lesspaper_ngl_compose up -d; then
    ui_gauge_stop
    abort "docker compose up failed. See ${LESSPAPER_NGL_LOG_FILE}."
  fi
  local healthy=1
  ui_gauge_update 75 "Waiting for health checks..."
  if ! health_wait; then
    healthy=0
  fi
  ui_gauge_update 96 "Writing install state..."
  state_write
  if [[ "${LESSPAPER_NGL_SKIP_CLI:-0}" != "1" ]]; then
    ui_gauge_update 98 "Installing lesspaper-ngl CLI..."
    install_cli
  fi
  ui_gauge_update 100 "Done."
  ui_gauge_stop
  LESSPAPER_NGL_HEALTHY="${healthy}"
}

repair_install() {
  load_existing_defaults
  [[ -n "${LESSPAPER_NGL_INSTALL_DIR:-}" ]] || abort "No install directory found."
  [[ -f "${LESSPAPER_NGL_INSTALL_DIR}/docker-compose.yml" ]] || abort "No docker-compose.yml in ${LESSPAPER_NGL_INSTALL_DIR}."
  ui_gauge_start "Repairing lesspaper-ngl..."
  ui_gauge_update 30 "Starting services..."
  if ! run_install_cmd lesspaper_ngl_compose up -d; then
    ui_gauge_stop
    abort "Repair failed to start services. See ${LESSPAPER_NGL_LOG_FILE}."
  fi
  ui_gauge_update 60 "Waiting for health..."
  local ok=0
  if health_wait; then
    ok=1
  fi
  ui_gauge_update 100 "Done."
  ui_gauge_stop
  if [[ "${ok}" == "1" ]]; then
    ui_msgbox "Repair finished. lesspaper-ngl is healthy.

UI: ${LESSPAPER_NGL_FRONTEND_ORIGIN:-http://127.0.0.1:${LESSPAPER_NGL_HTTP_PORT:-9398}}
CLI: lesspaper-ngl status
Log: ${LESSPAPER_NGL_LOG_FILE}"
  else
    ui_msgbox "Repair completed but lesspaper-ngl is not healthy yet.

See: ${LESSPAPER_NGL_LOG_FILE}
Then: lesspaper-ngl doctor"
  fi
}

update_install() {
  load_existing_defaults
  [[ -n "${LESSPAPER_NGL_INSTALL_DIR:-}" ]] || abort "No install directory found."
  [[ -f "${LESSPAPER_NGL_INSTALL_DIR}/.env" ]] || abort "No .env in ${LESSPAPER_NGL_INSTALL_DIR}."
  [[ -f "${LESSPAPER_NGL_INSTALL_DIR}/docker-compose.yml" ]] || abort "No docker-compose.yml in ${LESSPAPER_NGL_INSTALL_DIR}."

  LESSPAPER_NGL_MODE=update
  LESSPAPER_NGL_METHOD=image
  SHOW_ADMIN_PASSWORD=0
  LESSPAPER_NGL_BIND="${LESSPAPER_NGL_BIND:-0.0.0.0}"
  LESSPAPER_NGL_HTTP_PORT="${LESSPAPER_NGL_HTTP_PORT:-${LESSPAPER_NGL_DEFAULT_HTTP_PORT}}"
  LESSPAPER_NGL_API_PORT="${LESSPAPER_NGL_API_PORT:-${LESSPAPER_NGL_DEFAULT_API_PORT}}"
  LESSPAPER_NGL_COMPOSE_PROJECT="${LESSPAPER_NGL_COMPOSE_PROJECT:-${LESSPAPER_NGL_DEFAULT_PROJECT}}"
  LESSPAPER_NGL_EXPOSE_API="${LESSPAPER_NGL_EXPOSE_API:-0}"
  LESSPAPER_NGL_FRONTEND_ORIGIN="$(config_env_get FRONTEND_ORIGIN || printf '%s' "${LESSPAPER_NGL_FRONTEND_ORIGIN:-http://127.0.0.1:${LESSPAPER_NGL_HTTP_PORT}}")"
  LESSPAPER_NGL_DOCS_PATH="$(config_env_get_any LESSPAPER_NGL_DOCUMENTS_HOST FOLIUM_DOCUMENTS_HOST || printf '%s' "${LESSPAPER_NGL_DOCS_PATH:-${LESSPAPER_NGL_INSTALL_DIR}/data/documents}")"
  LESSPAPER_NGL_CONSUME_PATH="$(config_env_get_any LESSPAPER_NGL_CONSUME_HOST FOLIUM_CONSUME_HOST || printf '%s' "${LESSPAPER_NGL_CONSUME_PATH:-${LESSPAPER_NGL_INSTALL_DIR}/data/consume}")"
  LESSPAPER_NGL_EXPORT_PATH="$(config_env_get_any LESSPAPER_NGL_EXPORT_HOST FOLIUM_EXPORT_HOST || printf '%s' "${LESSPAPER_NGL_EXPORT_PATH:-${LESSPAPER_NGL_INSTALL_DIR}/data/export}")"
  LESSPAPER_NGL_PADDLE_PATH="$(config_env_get_any LESSPAPER_NGL_PADDLE_CACHE_HOST FOLIUM_PADDLE_CACHE_HOST || printf '%s' "${LESSPAPER_NGL_PADDLE_PATH:-${LESSPAPER_NGL_INSTALL_DIR}/data/paddleocr}")"

  if [[ "${LESSPAPER_NGL_NONINTERACTIVE}" == "1" ]]; then
    if ! config_resolve_version_tag; then
      abort "Could not resolve LESSPAPER_NGL_VERSION / LESSPAPER_NGL_VERSION_TAG to a pinned release."
    fi
    log_info "noninteractive update to ${LESSPAPER_NGL_VERSION_TAG}"
  else
    local rc=0
    while true; do
      rc=0
      wizard_version || rc=$?
      case "${rc}" in
        0) break ;;
        1) continue ;;
        2)
          prompt_existing "${LESSPAPER_NGL_INSTALL_DIR}"
          case "${LESSPAPER_NGL_MODE}" in
            update) continue ;;
            repair) repair_install; return 0 ;;
            reconfigure) return 2 ;;
            *) return 0 ;;
          esac
          ;;
        130) exit 130 ;;
        *) abort "Unexpected update state (${rc})." ;;
      esac
    done

    local go=""
    go="$(ui_menu "Update lesspaper-ngl to ${LESSPAPER_NGL_VERSION_TAG} (image tag ${LESSPAPER_NGL_VERSION})?

Install dir: ${LESSPAPER_NGL_INSTALL_DIR}
Secrets and document data are kept. Compose will pull release images and restart.

Log file:
${LESSPAPER_NGL_LOG_FILE}" \
      update "Update now" \
      back "Back")" || return 2
    if [[ "${go}" != "update" ]]; then
      return 2
    fi
  fi

  config_backup_install_dir
  config_migrate_folium_env "${LESSPAPER_NGL_INSTALL_DIR}/.env"
  config_env_set LESSPAPER_NGL_VERSION "${LESSPAPER_NGL_VERSION}"
  rm -f "${LESSPAPER_NGL_INSTALL_DIR}/compose.source.yaml"

  ui_gauge_start "Updating lesspaper-ngl to ${LESSPAPER_NGL_VERSION}..."
  ui_gauge_update 15 "Downloading release Compose..."
  fetch_compose
  # Re-apply port/bind overlay from current settings (ports stay stripped on the base file).
  config_write_override
  if ! config_compose_validate; then
    ui_gauge_stop
    abort "docker compose config failed after update. See ${LESSPAPER_NGL_LOG_FILE}."
  fi
  ui_gauge_update 40 "Pulling images..."
  if ! run_install_cmd lesspaper_ngl_compose pull; then
    ui_gauge_stop
    abort "Image pull failed. See ${LESSPAPER_NGL_LOG_FILE}."
  fi
  ui_gauge_update 70 "Restarting services..."
  if ! run_install_cmd lesspaper_ngl_compose up -d; then
    ui_gauge_stop
    abort "docker compose up failed. See ${LESSPAPER_NGL_LOG_FILE}."
  fi
  local healthy=1
  ui_gauge_update 75 "Waiting for health checks..."
  if ! health_wait; then
    healthy=0
  fi
  ui_gauge_update 96 "Writing install state..."
  state_write
  if [[ "${LESSPAPER_NGL_SKIP_CLI:-0}" != "1" ]]; then
    ui_gauge_update 98 "Refreshing lesspaper-ngl CLI..."
    install_cli
  fi
  ui_gauge_update 100 "Done."
  ui_gauge_stop
  LESSPAPER_NGL_HEALTHY="${healthy}"
  LESSPAPER_NGL_FRONTEND_ORIGIN="$(config_env_get FRONTEND_ORIGIN || printf '%s' "${LESSPAPER_NGL_FRONTEND_ORIGIN:-}")"
  if [[ "${LESSPAPER_NGL_NONINTERACTIVE}" != "1" ]]; then
    success_screen
  fi
  return 0
}

success_screen() {
  local admin_note="" mcp_note="" api_note=""
  local primary_origin="${LESSPAPER_NGL_FRONTEND_ORIGIN%*,*}"
  primary_origin="${primary_origin%/}"
  mcp_note="

MCP (Bearer token): ${primary_origin}/mcp"
  if [[ "${LESSPAPER_NGL_EXPOSE_API:-0}" == "1" ]]; then
    api_note="

API (optional): http://${LESSPAPER_NGL_BIND}:${LESSPAPER_NGL_API_PORT:-${LESSPAPER_NGL_DEFAULT_API_PORT}}/mcp"
  fi
  if [[ "${SHOW_ADMIN_PASSWORD}" == "1" ]]; then
    admin_note="

Admin username: ${LESSPAPER_NGL_ADMIN_USERNAME:-admin}
Admin password: ${LESSPAPER_NGL_ADMIN_PASSWORD}

Save this password now. It will not be shown again and is not written to the installer log."
  else
    admin_note="

Existing admin credentials were kept and are not displayed."
  fi
  if [[ "${LESSPAPER_NGL_HEALTHY:-1}" == "1" ]]; then
    local verb="installed"
    [[ "${LESSPAPER_NGL_MODE}" == "update" ]] && verb="updated"
    ui_msgbox "lesspaper-ngl ${LESSPAPER_NGL_VERSION} is ${verb} and healthy.

Open: ${LESSPAPER_NGL_FRONTEND_ORIGIN}${mcp_note}${api_note}
Install dir: ${LESSPAPER_NGL_INSTALL_DIR}
CLI: lesspaper-ngl status | start | stop | logs | doctor  (folium shim also installed)
Log: ${LESSPAPER_NGL_LOG_FILE}${admin_note}"
  else
    local verb="Install"
    [[ "${LESSPAPER_NGL_MODE}" == "update" ]] && verb="Update"
    ui_msgbox "${verb} completed but lesspaper-ngl is not healthy yet.

Open: ${LESSPAPER_NGL_FRONTEND_ORIGIN}${mcp_note}${api_note}
Install dir: ${LESSPAPER_NGL_INSTALL_DIR}
Log: ${LESSPAPER_NGL_LOG_FILE}
Next: lesspaper-ngl doctor

Do not treat this as a successful install until health checks pass.${admin_note}"
  fi
}

main() {
  parse_args "$@"
  if declare -F lesspaper_ngl_hydrate_legacy_env >/dev/null 2>&1; then
    lesspaper_ngl_hydrate_legacy_env
  fi
  log_init
  log_info "installer root=${INSTALLER_ROOT}"

  ensure_whiptail

  local discovered=""
  discovered="$(discover_existing_install || true)"

  if [[ "${LESSPAPER_NGL_NONINTERACTIVE}" != "1" ]]; then
    ui_session_start
    local welcome_extra=""
    if [[ -n "${discovered}" ]]; then
      welcome_extra="

lesspaper-ngl is already installed at:
${discovered}"
    fi
    ui_msgbox "Welcome to the lesspaper-ngl installer.

This will install or update a Docker Compose stack (Postgres, API, worker, web).
AI providers are optional and are not configured here.
${welcome_extra}

Installation log file:
${LESSPAPER_NGL_LOG_FILE}

Use Back to return to the previous screen.
Ctrl+C cancels; existing data is not deleted."
  fi

  SYSTEM_CHECK_WARNINGS=""
  if ! system_check; then
    abort "${SYSTEM_CHECK_ERROR}"
  fi
  if [[ -n "${SYSTEM_CHECK_WARNINGS:-}" && "${LESSPAPER_NGL_NONINTERACTIVE}" != "1" ]]; then
    ui_msgbox "Warnings:
${SYSTEM_CHECK_WARNINGS}

You can continue, but performance or disk space may be tight."
  fi

  ensure_docker_ready

  if [[ "${LESSPAPER_NGL_NONINTERACTIVE}" == "1" ]]; then
    LESSPAPER_NGL_METHOD="${LESSPAPER_NGL_METHOD:-image}"
    LESSPAPER_NGL_INSTALL_DIR="${LESSPAPER_NGL_INSTALL_DIR:-${LESSPAPER_NGL_DEFAULT_INSTALL_DIR}}"
    LESSPAPER_NGL_INSTALL_DIR="$(storage_normalize_path "${LESSPAPER_NGL_INSTALL_DIR}")"
    if storage_is_critical_forbidden_path "${LESSPAPER_NGL_INSTALL_DIR}"; then
      abort "Refusing to install into ${LESSPAPER_NGL_INSTALL_DIR}."
    fi
    if ! storage_validate_install_path "${LESSPAPER_NGL_INSTALL_DIR}"; then
      abort "Refusing risky install path ${LESSPAPER_NGL_INSTALL_DIR}. Set LESSPAPER_NGL_ACCEPT_RISKY_PATH=1 to allow /root or /tmp."
    fi

    # Prefer discovered install path when updating (or when one already exists).
    if [[ -z "${discovered}" ]]; then
      discovered="$(discover_existing_install || true)"
    fi
    if [[ -z "${discovered}" \
      && -f "${LESSPAPER_NGL_INSTALL_DIR}/.env" \
      && -f "${LESSPAPER_NGL_INSTALL_DIR}/docker-compose.yml" ]]; then
      discovered="${LESSPAPER_NGL_INSTALL_DIR}"
    fi
    local want_update=0
    if [[ "${LESSPAPER_NGL_MODE}" == "update" ]]; then
      want_update=1
    elif [[ -n "${discovered}" ]]; then
      # Default: existing install → update (preserve secrets/bind).
      want_update=1
    fi

    if [[ "${want_update}" == "1" ]]; then
      if [[ -z "${discovered}" ]]; then
        abort "No existing lesspaper-ngl install found to update. Set LESSPAPER_NGL_INSTALL_DIR or install first."
      fi
      LESSPAPER_NGL_INSTALL_DIR="${discovered}"
      LESSPAPER_NGL_MODE=update
      update_install
      finish_noninteractive
    fi

    LESSPAPER_NGL_MODE=install
    # Fresh install defaults (only applied when not already set via env / --preserve-secrets path).
    if [[ -f "${LESSPAPER_NGL_INSTALL_DIR}/.env" ]]; then
      load_existing_defaults
    fi
    LESSPAPER_NGL_BIND="${LESSPAPER_NGL_BIND:-127.0.0.1}"
    LESSPAPER_NGL_HTTP_PORT="${LESSPAPER_NGL_HTTP_PORT:-${LESSPAPER_NGL_DEFAULT_HTTP_PORT}}"
    LESSPAPER_NGL_API_PORT="${LESSPAPER_NGL_API_PORT:-${LESSPAPER_NGL_DEFAULT_API_PORT}}"
    LESSPAPER_NGL_EXPOSE_API="${LESSPAPER_NGL_EXPOSE_API:-0}"
    LESSPAPER_NGL_COMPOSE_PROJECT="${LESSPAPER_NGL_COMPOSE_PROJECT:-${LESSPAPER_NGL_DEFAULT_PROJECT}}"
    if ! config_resolve_version_tag; then
      abort "Non-interactive install requires a pinned LESSPAPER_NGL_VERSION / LESSPAPER_NGL_VERSION_TAG (or latest/beta)."
    fi
    LESSPAPER_NGL_DOCS_PATH="${LESSPAPER_NGL_DOCS_PATH:-${LESSPAPER_NGL_INSTALL_DIR}/data/documents}"
    LESSPAPER_NGL_CONSUME_PATH="${LESSPAPER_NGL_CONSUME_PATH:-${LESSPAPER_NGL_INSTALL_DIR}/data/consume}"
    LESSPAPER_NGL_EXPORT_PATH="${LESSPAPER_NGL_EXPORT_PATH:-${LESSPAPER_NGL_INSTALL_DIR}/data/export}"
    LESSPAPER_NGL_PADDLE_PATH="${LESSPAPER_NGL_PADDLE_PATH:-${LESSPAPER_NGL_INSTALL_DIR}/data/paddleocr}"
    local bind_path
    for bind_path in "${LESSPAPER_NGL_DOCS_PATH}" "${LESSPAPER_NGL_CONSUME_PATH}" "${LESSPAPER_NGL_EXPORT_PATH}" "${LESSPAPER_NGL_PADDLE_PATH}"; do
      if ! storage_validate_bind_path "${bind_path}"; then
        abort "Refusing storage bind path ${bind_path}."
      fi
    done
    LESSPAPER_NGL_FRONTEND_ORIGIN="${LESSPAPER_NGL_FRONTEND_ORIGIN:-$(network_origin_for "${LESSPAPER_NGL_BIND}" "${LESSPAPER_NGL_HTTP_PORT}" "")}"
    wizard_secrets
    execute_install
    finish_noninteractive
  fi

  # Prefer the path discovered on the welcome screen; re-check after Docker is ready.
  if [[ -z "${discovered}" ]]; then
    discovered="$(discover_existing_install || true)"
  fi

  if [[ -n "${discovered}" ]]; then
    LESSPAPER_NGL_INSTALL_DIR="${discovered}"
    while true; do
      prompt_existing "${discovered}"
      case "${LESSPAPER_NGL_MODE}" in
        update)
          local urc=0
          update_install || urc=$?
          case "${urc}" in
            0)
              ui_session_end
              return 0
              ;;
            2)
              # Nested Back may have switched mode via prompt_existing.
              case "${LESSPAPER_NGL_MODE}" in
                reconfigure)
                  load_existing_defaults
                  break
                  ;;
                repair)
                  repair_install
                  ui_session_end
                  return 0
                  ;;
                *)
                  continue
                  ;;
              esac
              ;;
            130) exit 130 ;;
            *) abort "Update failed." ;;
          esac
          ;;
        repair)
          repair_install
          ui_session_end
          return 0
          ;;
        reconfigure)
          load_existing_defaults
          break
          ;;
        *)
          ui_session_end
          return 0
          ;;
      esac
    done
  fi

  run_wizard
  execute_install
  success_screen
  ui_session_end
}

trap on_interrupt INT TERM
main "$@"
