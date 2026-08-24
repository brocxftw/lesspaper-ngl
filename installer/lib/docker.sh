# Docker Engine / Compose helpers.
# shellcheck shell=bash

LESSPAPER_NGL_DOCKER_CMD=(docker)

docker_available() {
  command -v docker >/dev/null 2>&1
}

docker_configure_cmd() {
  LESSPAPER_NGL_DOCKER_CMD=(docker)
  if docker info >/dev/null 2>&1; then
    return 0
  fi
  if ! is_root && command -v sudo >/dev/null 2>&1 && sudo docker info >/dev/null 2>&1; then
    LESSPAPER_NGL_DOCKER_CMD=(sudo docker)
    return 0
  fi
  return 1
}

docker_bin() {
  "${LESSPAPER_NGL_DOCKER_CMD[@]}" "$@"
}

docker_info_ok() {
  docker_configure_cmd && docker_bin info >/dev/null 2>&1
}

docker_compose_ok() {
  docker_configure_cmd || return 1
  docker_bin compose version >/dev/null 2>&1
}

docker_compose_version() {
  docker_bin compose version 2>/dev/null | head -n 1
}

lesspaper_ngl_compose() {
  local -a args
  docker_configure_cmd || return 1
  (
    cd "${LESSPAPER_NGL_INSTALL_DIR}" || exit 1
    args=(-p "${LESSPAPER_NGL_COMPOSE_PROJECT:-lesspaper-ngl}" -f docker-compose.yml)
    if [[ -f docker-compose.override.yml ]]; then
      args+=(-f docker-compose.override.yml)
    fi
    if [[ -f compose.source.yaml ]]; then
      args+=(-f compose.source.yaml)
    fi
    docker_bin compose "${args[@]}" "$@"
  )
}

docker_port_owner() {
  local port="$1"
  docker_bin ps --format '{{.Names}} {{.Ports}}' 2>/dev/null | awk -v p=":${port}" '$0 ~ p'
}
