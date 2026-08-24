# Bind address, HTTP port, and FRONTEND_ORIGIN helpers.
# shellcheck shell=bash

network_port_valid() {
  local port="${1:-}"
  [[ "${port}" =~ ^[0-9]+$ ]] || return 1
  [[ "${port}" -ge 1 && "${port}" -le 65535 ]]
}

network_bind_valid() {
  local bind="${1:-}"
  [[ "${bind}" == "0.0.0.0" || "${bind}" == "127.0.0.1" ]]
}

network_port_in_use() {
  local port="$1"
  network_port_valid "${port}" || return 0
  if command -v ss >/dev/null 2>&1; then
    if ss -ltnH "sport = :${port}" 2>/dev/null | grep -q .; then
      return 0
    fi
  elif command -v netstat >/dev/null 2>&1; then
    if netstat -ltn 2>/dev/null | awk -v p=":${port}" '$4 ~ p"$" {found=1} END {exit !found}'; then
      return 0
    fi
  fi
  return 1
}

network_port_is_ours() {
  local port="$1"
  docker_info_ok || return 1
  docker_bin ps \
    --filter "label=com.docker.compose.project=${LESSPAPER_NGL_COMPOSE_PROJECT:-lesspaper-ngl}" \
    --format '{{.Ports}}' 2>/dev/null | grep -Eq ":${port}->|:0\.0\.0\.0:${port}->|127\.0\.0\.1:${port}->"
}

network_port_blocked() {
  local port="$1"
  network_port_in_use "${port}" && ! network_port_is_ours "${port}"
}

network_port_users() {
  local port="$1"
  if command -v ss >/dev/null 2>&1; then
    ss -ltnp "sport = :${port}" 2>/dev/null || ss -ltn "sport = :${port}" 2>/dev/null
  fi
  if docker_info_ok; then
    docker_port_owner "${port}" || true
  fi
}

network_lan_ipv4() {
  local ip=""
  if command -v ip >/dev/null 2>&1; then
    ip="$(ip -4 route get 1.1.1.1 2>/dev/null | awk '{for (i=1;i<=NF;i++) if ($i=="src") {print $(i+1); exit}}')"
  fi
  if [[ -z "${ip}" ]] && command -v hostname >/dev/null 2>&1; then
    ip="$(hostname -I 2>/dev/null | awk '{print $1}')"
  fi
  printf '%s' "${ip}"
}

network_origin_for() {
  local bind="$1"
  local port="$2"
  local public="${3:-}"
  if [[ -n "${public}" ]]; then
    printf '%s' "${public%/}"
    return 0
  fi
  if [[ "${bind}" == "127.0.0.1" ]]; then
    printf 'http://127.0.0.1:%s' "${port}"
    return 0
  fi
  local lan
  lan="$(network_lan_ipv4)"
  if [[ -n "${lan}" ]]; then
    printf 'http://%s:%s' "${lan}" "${port}"
  else
    printf 'http://localhost:%s' "${port}"
  fi
}

network_health_base() {
  local port="${LESSPAPER_NGL_HTTP_PORT:-9398}"
  printf 'http://127.0.0.1:%s' "${port}"
}
