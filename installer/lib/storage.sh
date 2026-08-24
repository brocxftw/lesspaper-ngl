# Host path validation for document binds. UID 1000; no chmod 777.
# shellcheck shell=bash

storage_is_critical_forbidden_path() {
  local raw="${1:-}"
  local path
  [[ -n "${raw}" ]] || return 0
  path="$(storage_normalize_path "${raw}")" || return 0
  case "${path}" in
    /|/bin|/boot|/dev|/etc|/lib|/lib64|/proc|/sbin|/sys|/usr)
      return 0
      ;;
    /bin/*|/boot/*|/dev/*|/etc/*|/lib/*|/lib64/*|/proc/*|/sbin/*|/sys/*|/usr/*)
      return 0
      ;;
  esac
  return 1
}

storage_is_risky_install_path() {
  local raw="${1:-}"
  local path
  [[ -n "${raw}" ]] || return 1
  path="$(storage_normalize_path "${raw}")" || return 1
  case "${path}" in
    /root|/tmp)
      return 0
      ;;
    /root/*|/tmp/*)
      return 0
      ;;
  esac
  return 1
}

# Backwards-compatible alias: critical system paths only (not /root or /tmp).
storage_is_forbidden_path() {
  storage_is_critical_forbidden_path "$@"
}

storage_normalize_path() {
  local raw="${1:-}"
  python3 - "${raw}" <<'PY'
import os, sys
raw = sys.argv[1]
if not raw:
    sys.exit(1)
print(os.path.abspath(os.path.expanduser(raw)))
PY
}

storage_fstype() {
  local path="$1"
  df -T "${path}" 2>/dev/null | awk 'NR==2 {print $2; exit}'
}

storage_is_remote_fstype() {
  local t="${1:-}"
  case "${t}" in
    nfs|nfs4|nfs3|cifs|smb3|smb2|fuse.sshfs) return 0 ;;
  esac
  return 1
}

storage_uid_of() {
  local path="$1"
  stat -c '%u' "${path}" 2>/dev/null || stat -f '%u' "${path}"
}

storage_gid_of() {
  local path="$1"
  stat -c '%g' "${path}" 2>/dev/null || stat -f '%g' "${path}"
}

storage_writable_by_app_user() {
  local path="$1"
  local marker="${path}/.folium-write-test"
  if docker_info_ok; then
    local -a docker_args=(
      run --rm
      --user "${LESSPAPER_NGL_APP_UID}:${LESSPAPER_NGL_APP_GID}"
    )
    if [[ -n "${LESSPAPER_NGL_EXTRA_GID:-}" ]]; then
      docker_args+=(--group-add "${LESSPAPER_NGL_EXTRA_GID}")
    fi
    docker_bin "${docker_args[@]}" \
      -v "${path}:/mnt" alpine:3.20 sh -c 'touch /mnt/.folium-write-test && rm -f /mnt/.folium-write-test' \
      >/dev/null 2>&1
    return $?
  fi
  if [[ "$(storage_uid_of "${path}")" == "${LESSPAPER_NGL_APP_UID}" ]]; then
    touch "${marker}" 2>/dev/null && rm -f "${marker}"
    return $?
  fi
  return 1
}

storage_prepare_dir() {
  local path="$1"
  local do_chown="${2:-0}"
  if [[ ! -d "${path}" ]]; then
    run_root mkdir -p "${path}"
  fi
  if [[ "${do_chown}" == "1" ]]; then
    run_root chown "${LESSPAPER_NGL_APP_UID}:${LESSPAPER_NGL_APP_GID}" "${path}"
  fi
  storage_writable_by_app_user "${path}"
}

storage_confirm_risky_install_path() {
  local path="$1"
  local choice=""
  export LESSPAPER_NGL_UI_NOCANCEL=1
  choice="$(ui_menu "${path} is under /root or /tmp.

Installing here is at your own risk (permissions, backups, and upgrades are your responsibility).

Continue with this install directory?" \
    yes "Continue at my own risk" \
    abort "Choose another directory")"
  export LESSPAPER_NGL_UI_NOCANCEL=0
  [[ "${choice}" == "yes" ]]
}

storage_validate_install_path() {
  local path="$1"
  if storage_is_critical_forbidden_path "${path}"; then
    return 1
  fi
  if ! storage_is_risky_install_path "${path}"; then
    return 0
  fi
  if [[ "${LESSPAPER_NGL_NONINTERACTIVE}" == "1" ]]; then
    [[ "${LESSPAPER_NGL_ACCEPT_RISKY_PATH:-0}" == "1" ]]
    return
  fi
  storage_confirm_risky_install_path "${path}"
}

storage_validate_bind_path() {
  local path="$1"
  ! storage_is_critical_forbidden_path "${path}"
}
