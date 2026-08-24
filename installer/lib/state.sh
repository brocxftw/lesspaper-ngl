# Installer metadata (no secrets).
# shellcheck shell=bash

state_file_path() {
  printf '%s/install-state.json' "${LESSPAPER_NGL_INSTALL_DIR:-/opt/lesspaper-ngl}"
}

state_exists() {
  [[ -f "$(state_file_path)" ]]
}

state_read_field() {
  local field="$1"
  local file
  file="$(state_file_path)"
  [[ -f "${file}" ]] || return 1
  python3 - "${file}" "${field}" <<'PY'
import json, sys
path, field = sys.argv[1], sys.argv[2]
with open(path, encoding="utf-8") as fh:
    data = json.load(fh)
cur = data
for part in field.split("."):
    if isinstance(cur, dict) and part in cur:
        cur = cur[part]
    else:
        sys.exit(1)
if isinstance(cur, (dict, list)):
    json.dump(cur, sys.stdout)
elif isinstance(cur, bool):
    print("true" if cur else "false", end="")
elif cur is None:
    print("", end="")
else:
    print(cur, end="")
PY
}

state_write() {
  local dest
  dest="$(state_file_path)"
  umask 022
  mkdir -p "${LESSPAPER_NGL_INSTALL_DIR}"
  export LESSPAPER_NGL_METHOD LESSPAPER_NGL_VERSION LESSPAPER_NGL_VERSION_TAG LESSPAPER_NGL_INSTALL_DIR
  export LESSPAPER_NGL_BIND LESSPAPER_NGL_HTTP_PORT LESSPAPER_NGL_API_PORT LESSPAPER_NGL_EXPOSE_API LESSPAPER_NGL_FRONTEND_ORIGIN
  export LESSPAPER_NGL_DOCS_PATH LESSPAPER_NGL_CONSUME_PATH LESSPAPER_NGL_EXPORT_PATH LESSPAPER_NGL_PADDLE_PATH
  export LESSPAPER_NGL_EXTRA_GID LESSPAPER_NGL_COMPOSE_PROJECT
  python3 - "${dest}" <<PY
import json, os, sys
dest = sys.argv[1]
data = {
  "schema": 1,
  "install_method": os.environ.get("LESSPAPER_NGL_METHOD", "image"),
  "version": os.environ.get("LESSPAPER_NGL_VERSION", ""),
  "version_tag": os.environ.get("LESSPAPER_NGL_VERSION_TAG", ""),
  "install_dir": os.environ.get("LESSPAPER_NGL_INSTALL_DIR", ""),
  "network": {
    "bind": os.environ.get("LESSPAPER_NGL_BIND", "0.0.0.0"),
    "port": int(os.environ.get("LESSPAPER_NGL_HTTP_PORT", "9398")),
    "api_port": int(os.environ.get("LESSPAPER_NGL_API_PORT", "9099")),
    "expose_api": os.environ.get("LESSPAPER_NGL_EXPOSE_API", "0") == "1",
    "frontend_origin": os.environ.get("LESSPAPER_NGL_FRONTEND_ORIGIN", ""),
  },
  "storage": {
    "documents": os.environ.get("LESSPAPER_NGL_DOCS_PATH", ""),
    "consume": os.environ.get("LESSPAPER_NGL_CONSUME_PATH", ""),
    "export": os.environ.get("LESSPAPER_NGL_EXPORT_PATH", ""),
    "paddle_cache": os.environ.get("LESSPAPER_NGL_PADDLE_PATH", ""),
  },
  "extra_gid": os.environ.get("LESSPAPER_NGL_EXTRA_GID", ""),
  "compose_project": os.environ.get("LESSPAPER_NGL_COMPOSE_PROJECT", "lesspaper-ngl"),
}
with open(dest, "w", encoding="utf-8") as fh:
    json.dump(data, fh, indent=2)
    fh.write("\n")
PY
  log_info "wrote install-state.json"
}

state_write_pointer() {
  if [[ "${LESSPAPER_NGL_SKIP_CLI:-0}" == "1" ]]; then
    return 0
  fi
  # Always write the new pointer; also refresh legacy pointer for older tooling.
  run_root mkdir -p /etc/lesspaper-ngl
  printf '%s\n' "${LESSPAPER_NGL_INSTALL_DIR}" | run_root tee /etc/lesspaper-ngl/install-dir >/dev/null
  run_root chmod 644 /etc/lesspaper-ngl/install-dir
  run_root mkdir -p /etc/folium
  printf '%s\n' "${LESSPAPER_NGL_INSTALL_DIR}" | run_root tee /etc/folium/install-dir >/dev/null
  run_root chmod 644 /etc/folium/install-dir
}

# Discover either new or legacy install locations. Never force-moves the install dir.
state_discover_dir() {
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
    if [[ -f "${p}/install-state.json" ]]; then
      printf '%s' "${p}"
      return 0
    fi
  fi
  if [[ -f /etc/folium/install-dir ]]; then
    p="$(tr -d '\n' </etc/folium/install-dir)"
    if [[ -f "${p}/install-state.json" ]]; then
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
