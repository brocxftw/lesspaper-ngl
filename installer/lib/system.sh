# Host capability checks. Hard-fail only where the plan requires it.
# shellcheck shell=bash

system_os_pretty() {
  if [[ -r /etc/os-release ]]; then
    # shellcheck disable=SC1091
    . /etc/os-release
    printf '%s' "${PRETTY_NAME:-unknown}"
  else
    printf 'unknown'
  fi
}

system_pkg_family() {
  if [[ -r /etc/os-release ]]; then
    # shellcheck disable=SC1091
    . /etc/os-release
    case "${ID_LIKE:-}${ID:-}" in
      *debian*|*ubuntu*) printf 'debian' ;;
      *rhel*|*fedora*|*centos*|*rocky*|*almalinux*) printf 'rhel' ;;
      *) printf 'unknown' ;;
    esac
  else
    printf 'unknown'
  fi
}

system_mem_kb() {
  awk '/MemTotal:/ {print $2; exit}' /proc/meminfo
}

system_disk_kb() {
  local path="${1:-/}"
  df -Pk "${path}" 2>/dev/null | awk 'NR==2 {print $4; exit}'
}

system_has_sudo() {
  if is_root; then
    return 0
  fi
  command -v sudo >/dev/null 2>&1 || return 1
  sudo -n true >/dev/null 2>&1 && return 0
  sudo -v
}

system_connectivity() {
  local url="${1:-https://api.github.com}"
  curl -fsSI --max-time 8 "${url}" >/dev/null 2>&1
}

system_collect_report() {
  local mem disk
  mem="$(system_mem_kb)"
  disk="$(system_disk_kb "${LESSPAPER_NGL_INSTALL_DIR:-/opt}")"
  printf 'os=%s\n' "$(system_os_pretty)"
  printf 'arch=%s\n' "$(uname -m)"
  printf 'mem_kb=%s\n' "${mem}"
  printf 'disk_avail_kb=%s\n' "${disk:-unknown}"
  printf 'user=%s uid=%s\n' "$(id -un)" "$(id -u)"
}

system_check() {
  local warnings=0
  local mem disk
  local report

  report="$(system_collect_report)"
  log_info "system: ${report}"

  if ! is_amd64; then
    log_error "architecture $(uname -m) is not linux/amd64"
    SYSTEM_CHECK_ERROR="Folium images are linux/amd64 only. This host is $(uname -m)."
    return 1
  fi

  if ! require_cmd curl; then
    log_error "curl is missing"
    SYSTEM_CHECK_ERROR="curl is required to download release files."
    return 1
  fi

  if ! require_cmd python3; then
    log_error "python3 is missing"
    SYSTEM_CHECK_ERROR="python3 is required for the installer."
    return 1
  fi

  if ! require_cmd openssl; then
    log_error "openssl is missing"
    SYSTEM_CHECK_ERROR="openssl is required to generate secrets."
    return 1
  fi

  if ! system_has_sudo; then
    log_error "sudo/root is required"
    SYSTEM_CHECK_ERROR="Installing lesspaper-ngl and managing Docker requires root or sudo."
    return 1
  fi

  mem="$(system_mem_kb)"
  if [[ -n "${mem}" && "${mem}" -lt 2097152 ]]; then
    log_warn "low memory: ${mem} kB"
    warnings=$((warnings + 1))
    SYSTEM_CHECK_WARNINGS="${SYSTEM_CHECK_WARNINGS:-}Less than 2 GiB RAM detected. Folium may be slow or fail under OCR load. "
  fi

  disk="$(system_disk_kb "${LESSPAPER_NGL_INSTALL_DIR:-/opt}")"
  if [[ -n "${disk}" && "${disk}" -lt 8388608 ]]; then
    log_warn "low disk: ${disk} kB"
    warnings=$((warnings + 1))
    SYSTEM_CHECK_WARNINGS="${SYSTEM_CHECK_WARNINGS:-}Less than 8 GiB free disk near the install directory. "
  fi

  if ! system_connectivity "https://api.github.com"; then
    log_warn "cannot reach api.github.com"
    warnings=$((warnings + 1))
    SYSTEM_CHECK_WARNINGS="${SYSTEM_CHECK_WARNINGS:-}GitHub API is unreachable; version listing and image installs may fail. "
  fi

  SYSTEM_CHECK_ERROR="${SYSTEM_CHECK_ERROR:-}"
  SYSTEM_CHECK_WARNINGS="${SYSTEM_CHECK_WARNINGS:-}"
  export SYSTEM_CHECK_ERROR SYSTEM_CHECK_WARNINGS
  return 0
}
