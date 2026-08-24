# Release fetch, .env generation, compose overlay, backups.
# shellcheck shell=bash

github_latest_tag() {
  curl -fsSL --max-time 20 \
    -H "Accept: application/vnd.github+json" \
    "https://api.github.com/repos/${LESSPAPER_NGL_GITHUB_REPO}/releases/latest" \
    | python3 -c 'import json,sys; print(json.load(sys.stdin)["tag_name"])'
}

# Moving GitHub Release/tag names used as channel pointers, not installable versions.
github_is_channel_pointer_tag() {
  local tag="${1:-}"
  tag="$(config_strip_v_prefix "${tag}")"
  [[ "${tag}" == "beta" || "${tag}" == "latest" ]]
}

# Published tags, including GitHub prereleases (vX.Y.Z-beta.N). Drafts and
# moving channel pointers (`beta`, `latest`) are omitted.
github_filter_release_tags() {
  python3 -c 'import json,sys
channel={"beta","latest"}
for rel in json.load(sys.stdin):
    if rel.get("draft"):
        continue
    tag=rel.get("tag_name") or ""
    if tag in channel or tag.lstrip("v") in channel:
        continue
    print(tag)
'
}

github_release_tags() {
  curl -fsSL --max-time 20 \
    -H "Accept: application/vnd.github+json" \
    "https://api.github.com/repos/${LESSPAPER_NGL_GITHUB_REPO}/releases?per_page=30" \
    | github_filter_release_tags
}

github_tag_is_prerelease() {
  local tag="${1:-}"
  tag="$(config_strip_v_prefix "${tag}")"
  [[ "${tag}" == *-* ]]
}

# Newest prerelease tag from the releases list (GitHub returns newest first).
github_latest_prerelease_tag() {
  local tag
  while IFS= read -r tag; do
    [[ -n "${tag}" ]] || continue
    if github_is_channel_pointer_tag "${tag}"; then
      continue
    fi
    if github_tag_is_prerelease "${tag}"; then
      printf '%s\n' "${tag}"
      return 0
    fi
  done < <(github_release_tags)
  return 1
}

# Keep LESSPAPER_NGL_VERSION_TAG aligned with LESSPAPER_NGL_VERSION.
# Aliases (latest/beta) stay unprefixed so config_resolve_version_tag can expand them.
config_sync_version_tag() {
  local stripped
  stripped="$(config_strip_v_prefix "${LESSPAPER_NGL_VERSION:-}")"
  [[ -n "${stripped}" ]] || return 0
  case "${stripped}" in
    latest|beta)
      LESSPAPER_NGL_VERSION="${stripped}"
      LESSPAPER_NGL_VERSION_TAG="${stripped}"
      ;;
    *)
      LESSPAPER_NGL_VERSION="${stripped}"
      LESSPAPER_NGL_VERSION_TAG="v${stripped}"
      ;;
  esac
}

# Restore a version already chosen via CLI (--version) or process environment.
# Empty prior values mean "use whatever load_existing_defaults hydrated".
config_prefer_requested_version() {
  local prior_version="${1:-}"
  local prior_version_tag="${2:-}"
  if [[ -n "${prior_version}" || -n "${prior_version_tag}" ]]; then
    LESSPAPER_NGL_VERSION="${prior_version}"
    LESSPAPER_NGL_VERSION_TAG="${prior_version_tag}"
  fi
}

# Resolve LESSPAPER_NGL_VERSION / LESSPAPER_NGL_VERSION_TAG to a pinned release.
# Accepts pinned semver, or the moving aliases "latest" (stable) and "beta" (newest prerelease).
# Sets LESSPAPER_NGL_VERSION_TAG (with v prefix) and LESSPAPER_NGL_VERSION (without). Returns 0 on success.
config_resolve_version_tag() {
  local raw=""
  if [[ -n "${LESSPAPER_NGL_VERSION_TAG:-}" ]]; then
    raw="${LESSPAPER_NGL_VERSION_TAG}"
  elif [[ -n "${LESSPAPER_NGL_VERSION:-}" ]]; then
    raw="${LESSPAPER_NGL_VERSION}"
  else
    raw="$(github_latest_tag || github_latest_prerelease_tag)" || return 1
  fi
  local stripped
  stripped="$(config_strip_v_prefix "${raw}")"
  if [[ "${stripped}" == "latest" ]]; then
    LESSPAPER_NGL_VERSION_TAG="$(github_latest_tag)" || return 1
  elif [[ "${stripped}" == "beta" ]]; then
    LESSPAPER_NGL_VERSION_TAG="$(github_latest_prerelease_tag)" || return 1
  else
    LESSPAPER_NGL_VERSION_TAG="v${stripped}"
  fi
  LESSPAPER_NGL_VERSION="$(config_strip_v_prefix "${LESSPAPER_NGL_VERSION_TAG}")"
  if [[ "${LESSPAPER_NGL_VERSION}" == "latest" || "${LESSPAPER_NGL_VERSION}" == "beta" ]] \
    || ! config_is_pinned_version "${LESSPAPER_NGL_VERSION}"; then
    return 1
  fi
  return 0
}

github_release_menu_label() {
  local tag="${1:-}"
  local latest="${2:-}"
  if [[ -n "${latest}" && "${tag}" == "${latest}" ]]; then
    printf 'Latest stable'
  elif github_tag_is_prerelease "${tag}"; then
    printf 'Beta'
  else
    printf '%s' "${tag}"
  fi
}

github_asset_url() {
  local tag="$1"
  local name="$2"
  printf 'https://github.com/%s/releases/download/%s/%s' "${LESSPAPER_NGL_GITHUB_REPO}" "${tag}" "${name}"
}

config_download() {
  local url="$1"
  local dest="$2"
  log_cmd "curl ${url} -> ${dest}"
  curl -fsSL --max-time 60 -o "${dest}" "${url}"
}

config_download_env_example() {
  local tag="$1"
  local dest="$2"
  local name
  for name in env.example default.env.example .env.example; do
    if config_download "$(github_asset_url "${tag}" "${name}")" "${dest}"; then
      log_info "downloaded env template as ${name}"
      return 0
    fi
  done
  return 1
}

config_generate_secret() {
  local bytes="${1:-32}"
  openssl rand -hex "${bytes}"
}

config_postgres_password_ok() {
  local pw="${1:-}"
  [[ -n "${pw}" ]] || return 1
  [[ "${pw}" != *[@:/\#\?]* ]]
}

config_write_env() {
  local dest="${LESSPAPER_NGL_INSTALL_DIR}/.env"
  umask 077
  cat >"${dest}" <<EOF
# Generated by the lesspaper-ngl installer. Do not commit this file.
LESSPAPER_NGL_VERSION=${LESSPAPER_NGL_VERSION}
LESSPAPER_NGL_SECRET_KEY=${LESSPAPER_NGL_SECRET_KEY}
LESSPAPER_NGL_ENCRYPTION_KEY=${LESSPAPER_NGL_ENCRYPTION_KEY}
POSTGRES_USER=${POSTGRES_USER:-folium}
POSTGRES_PASSWORD=${POSTGRES_PASSWORD}
POSTGRES_DB=${POSTGRES_DB:-folium}
LESSPAPER_NGL_ADMIN_USERNAME=${LESSPAPER_NGL_ADMIN_USERNAME:-admin}
LESSPAPER_NGL_ADMIN_PASSWORD=${LESSPAPER_NGL_ADMIN_PASSWORD}
FRONTEND_ORIGIN=${LESSPAPER_NGL_FRONTEND_ORIGIN}
ALLOW_REGISTRATION=false
LESSPAPER_NGL_DOCUMENTS_HOST=${LESSPAPER_NGL_DOCS_PATH}
LESSPAPER_NGL_CONSUME_HOST=${LESSPAPER_NGL_CONSUME_PATH}
LESSPAPER_NGL_EXPORT_HOST=${LESSPAPER_NGL_EXPORT_PATH}
LESSPAPER_NGL_PADDLE_CACHE_HOST=${LESSPAPER_NGL_PADDLE_PATH}
LESSPAPER_NGL_BACKUPS_HOST=${LESSPAPER_NGL_INSTALL_DIR}/data/backups
DOCUMENTS_PATH=/documents
CONSUME_PATH=/consume
EXPORT_PATH=/export
BACKUPS_PATH=/backups
LESSPAPER_NGL_ENV=production
LESSPAPER_NGL_LOG_LEVEL=INFO
AI_PRIVACY_MODE=local_only
AI_PROFILE=lightweight
AI_ALLOW_REMOTE_EMBEDDINGS=false
AI_ALLOW_REMOTE_QA=false
AI_ALLOW_REMOTE_VISION=false
AI_WARN_BEFORE_REMOTE=true
COMPOSE_PROJECT_NAME=${LESSPAPER_NGL_COMPOSE_PROJECT:-lesspaper-ngl}
LESSPAPER_NGL_BIND=${LESSPAPER_NGL_BIND}
LESSPAPER_NGL_HTTP_PORT=${LESSPAPER_NGL_HTTP_PORT}
LESSPAPER_NGL_API_PORT=${LESSPAPER_NGL_API_PORT:-9099}
EOF
  chmod 600 "${dest}"
  log_info "wrote .env (mode 600)"
}

config_env_get() {
  local key="$1"
  local file="${2:-${LESSPAPER_NGL_INSTALL_DIR}/.env}"
  [[ -f "${file}" ]] || return 1
  python3 - "${file}" "${key}" <<'PY'
import sys
path, key = sys.argv[1], sys.argv[2]
for raw in open(path, encoding="utf-8"):
    line = raw.strip()
    if not line or line.startswith("#") or "=" not in line:
        continue
    k, v = line.split("=", 1)
    if k == key:
        print(v, end="")
        break
else:
    sys.exit(1)
PY
}

config_env_set() {
  local key="$1"
  local value="$2"
  local file="${3:-${LESSPAPER_NGL_INSTALL_DIR}/.env}"
  [[ -f "${file}" ]] || return 1
  python3 - "${file}" "${key}" "${value}" <<'PY'
import sys
path, key, value = sys.argv[1], sys.argv[2], sys.argv[3]
lines = open(path, encoding="utf-8").read().splitlines(True)
out = []
found = False
for line in lines:
    raw = line.strip()
    if raw and not raw.startswith("#") and "=" in raw:
        k, _ = raw.split("=", 1)
        if k == key:
            out.append(f"{key}={value}\n")
            found = True
            continue
    out.append(line)
if not found:
    if out and not out[-1].endswith("\n"):
        out[-1] = out[-1] + "\n"
    out.append(f"{key}={value}\n")
with open(path, "w", encoding="utf-8") as fh:
    fh.writelines(out)
PY
  chmod 600 "${file}"
  log_info "updated .env key=${key}"
}

config_env_get_any() {
  local file="${LESSPAPER_NGL_INSTALL_DIR}/.env"
  local -a keys=()
  local key
  while [[ $# -gt 0 ]]; do
    if [[ "$1" == "--" ]]; then
      shift
      file="${1:-$file}"
      break
    fi
    keys+=("$1")
    shift
  done
  [[ -f "${file}" ]] || return 1
  for key in "${keys[@]}"; do
    if config_env_get "${key}" "${file}"; then
      return 0
    fi
  done
  return 1
}

# One-shot .env migration: known FOLIUM_* → LESSPAPER_NGL_*. Backs up first.
# Never renames POSTGRES_*, COMPOSE_PROJECT_NAME, AI_*, path constants, FRONTEND_ORIGIN,
# ALLOW_REGISTRATION, SESSION_*, CSRF_*, DATABASE_URL*. Unknown keys left intact.
config_migrate_folium_env() {
  local file="${1:-${LESSPAPER_NGL_INSTALL_DIR}/.env}"
  [[ -f "${file}" ]] || return 0
  local stamp bak count
  stamp="$(date -u +%Y%m%d-%H%M%S)"
  bak="${file}.bak.${stamp}"
  cp -a "${file}" "${bak}"
  chmod 600 "${bak}"
  count="$(
    python3 - "${file}" <<'PY'
import sys
path = sys.argv[1]
RENAME = {
    "FOLIUM_VERSION": "LESSPAPER_NGL_VERSION",
    "FOLIUM_VERSION_TAG": "LESSPAPER_NGL_VERSION_TAG",
    "FOLIUM_SECRET_KEY": "LESSPAPER_NGL_SECRET_KEY",
    "FOLIUM_ENCRYPTION_KEY": "LESSPAPER_NGL_ENCRYPTION_KEY",
    "FOLIUM_ADMIN_USERNAME": "LESSPAPER_NGL_ADMIN_USERNAME",
    "FOLIUM_ADMIN_PASSWORD": "LESSPAPER_NGL_ADMIN_PASSWORD",
    "FOLIUM_DOCUMENTS_HOST": "LESSPAPER_NGL_DOCUMENTS_HOST",
    "FOLIUM_CONSUME_HOST": "LESSPAPER_NGL_CONSUME_HOST",
    "FOLIUM_EXPORT_HOST": "LESSPAPER_NGL_EXPORT_HOST",
    "FOLIUM_BACKUPS_HOST": "LESSPAPER_NGL_BACKUPS_HOST",
    "FOLIUM_PADDLE_CACHE_HOST": "LESSPAPER_NGL_PADDLE_CACHE_HOST",
    "FOLIUM_DOCUMENTS_HOST_SOURCE": "LESSPAPER_NGL_DOCUMENTS_HOST_SOURCE",
    "FOLIUM_ENV": "LESSPAPER_NGL_ENV",
    "FOLIUM_LOG_LEVEL": "LESSPAPER_NGL_LOG_LEVEL",
    "FOLIUM_HOST": "LESSPAPER_NGL_HOST",
    "FOLIUM_PORT": "LESSPAPER_NGL_PORT",
    "FOLIUM_SECURE_COOKIES": "LESSPAPER_NGL_SECURE_COOKIES",
    "FOLIUM_BIND": "LESSPAPER_NGL_BIND",
    "FOLIUM_HTTP_PORT": "LESSPAPER_NGL_HTTP_PORT",
    "FOLIUM_API_PORT": "LESSPAPER_NGL_API_PORT",
    "FOLIUM_BUILD_REVISION": "LESSPAPER_NGL_BUILD_REVISION",
    "FOLIUM_BUILD_DATE": "LESSPAPER_NGL_BUILD_DATE",
}

def excluded(key: str) -> bool:
    if key in {
        "COMPOSE_PROJECT_NAME", "DOCUMENTS_PATH", "CONSUME_PATH", "EXPORT_PATH",
        "BACKUPS_PATH", "FRONTEND_ORIGIN", "ALLOW_REGISTRATION",
    }:
        return True
    return key.startswith(("POSTGRES_", "AI_", "SESSION_", "CSRF_", "DATABASE_URL"))

lines = open(path, encoding="utf-8").read().splitlines(True)
existing_new = set()
parsed = []
for line in lines:
    raw = line.strip()
    if raw and not raw.startswith("#") and "=" in raw:
        k, v = raw.split("=", 1)
        parsed.append((k, v, line))
        if k.startswith("LESSPAPER_NGL_"):
            existing_new.add(k)
    else:
        parsed.append((None, None, line))

out = []
renamed = 0
for k, v, line in parsed:
    if k is None:
        out.append(line)
        continue
    if excluded(k) or k not in RENAME:
        out.append(line)
        continue
    new_k = RENAME[k]
    if new_k in existing_new:
        renamed += 1
        continue
    out.append(f"{new_k}={v}\n")
    existing_new.add(new_k)
    renamed += 1

text = "".join(out)
if text.startswith("# Generated by the Folium installer"):
    text = text.replace(
        "# Generated by the Folium installer. Do not commit this file.\n",
        "# Generated by the lesspaper-ngl installer. Do not commit this file.\n",
        1,
    )
with open(path, "w", encoding="utf-8") as fh:
    fh.write(text)
print(renamed)
PY
  )"
  log_info "migrated .env keys (${count} FOLIUM_* → LESSPAPER_NGL_*); backup ${bak}"
}


config_strip_compose_ports() {
  local file="$1"
  python3 - "${file}" <<'PY'
import re, sys
path = sys.argv[1]
with open(path, encoding="utf-8") as fh:
    lines = fh.readlines()
out = []
current = None
i = 0
while i < len(lines):
    line = lines[i]
    m = re.match(r"^  ([a-zA-Z0-9_]+):\s*$", line)
    if m:
        current = m.group(1)
        out.append(line)
        i += 1
        continue
    if current in {"api", "web"} and re.match(r"^    ports:\s*$", line):
        i += 1
        while i < len(lines) and re.match(r"^      - ", lines[i]):
            i += 1
        continue
    out.append(line)
    i += 1
with open(path, "w", encoding="utf-8") as fh:
    fh.writelines(out)
PY
}

config_write_override() {
  local dest="${LESSPAPER_NGL_INSTALL_DIR}/docker-compose.override.yml"
  local extra_gid="${LESSPAPER_NGL_EXTRA_GID:-}"
  local expose="${LESSPAPER_NGL_EXPOSE_API:-0}"
  python3 - "${dest}" "${expose}" "${extra_gid}" <<'PY'
import sys
dest, expose, extra = sys.argv[1], sys.argv[2], sys.argv[3]
lines = [
    "# Generated by the lesspaper-ngl installer. Ports and optional extra GID only.",
    "# Do not store secrets here.",
    "services:",
    "  web:",
    "    ports:",
    '      - "${LESSPAPER_NGL_BIND}:${LESSPAPER_NGL_HTTP_PORT}:80"',
]
if expose == "1":
    lines += [
        "  api:",
        "    ports:",
        '      - "${LESSPAPER_NGL_BIND}:${LESSPAPER_NGL_API_PORT}:8000"',
    ]
    if extra:
        lines += ["    group_add:", f'      - "{extra}"']
elif extra:
    lines += ["  api:", "    group_add:", f'      - "{extra}"']
if extra:
    lines += ["  worker:", "    group_add:", f'      - "{extra}"']
text = "\n".join(lines) + "\n"
with open(dest, "w", encoding="utf-8") as fh:
    fh.write(text)
PY
  log_info "wrote docker-compose.override.yml"
}

config_write_source_overlay() {
  local dest="${LESSPAPER_NGL_INSTALL_DIR}/compose.source.yaml"
  cat >"${dest}" <<'EOF'
# Generated by the lesspaper-ngl installer for source builds.
# Build context is INSTALL_DIR/src (git clone of the tagged release).
# Does not publish Postgres.
services:
  api:
    build:
      context: ./src
      dockerfile: docker/Dockerfile.backend
      args:
        LESSPAPER_NGL_VERSION: ${LESSPAPER_NGL_VERSION}
        LESSPAPER_NGL_BUILD_REVISION: ${LESSPAPER_NGL_BUILD_REVISION:-}
        LESSPAPER_NGL_BUILD_DATE: ${LESSPAPER_NGL_BUILD_DATE:-}
    image: ghcr.io/brocxftw/lesspaper-ngl-backend:${LESSPAPER_NGL_VERSION}
  worker:
    build:
      context: ./src
      dockerfile: docker/Dockerfile.backend
      args:
        LESSPAPER_NGL_VERSION: ${LESSPAPER_NGL_VERSION}
        LESSPAPER_NGL_BUILD_REVISION: ${LESSPAPER_NGL_BUILD_REVISION:-}
        LESSPAPER_NGL_BUILD_DATE: ${LESSPAPER_NGL_BUILD_DATE:-}
    image: ghcr.io/brocxftw/lesspaper-ngl-backend:${LESSPAPER_NGL_VERSION}
  web:
    build:
      context: ./src
      dockerfile: docker/Dockerfile.frontend
      args:
        LESSPAPER_NGL_VERSION: ${LESSPAPER_NGL_VERSION}
        LESSPAPER_NGL_BUILD_REVISION: ${LESSPAPER_NGL_BUILD_REVISION:-}
        LESSPAPER_NGL_BUILD_DATE: ${LESSPAPER_NGL_BUILD_DATE:-}
    image: ghcr.io/brocxftw/lesspaper-ngl-web:${LESSPAPER_NGL_VERSION}
EOF
  log_info "wrote compose.source.yaml"
}

config_backup_install_dir() {
  local src="${LESSPAPER_NGL_INSTALL_DIR}"
  local stamp backup
  [[ -d "${src}" ]] || return 0
  stamp="$(date -u +%Y%m%d-%H%M%S)"
  backup="${src}/backups/${stamp}"
  mkdir -p "${backup}"
  chmod 700 "${backup}"
  local f
  for f in .env docker-compose.yml docker-compose.override.yml compose.source.yaml install-state.json; do
    if [[ -f "${src}/${f}" ]]; then
      cp -a "${src}/${f}" "${backup}/${f}"
    fi
  done
  if [[ -f "${backup}/.env" ]]; then
    chmod 600 "${backup}/.env"
  fi
  log_info "backed up existing files to backups/${stamp}"
}

config_compose_validate() {
  local out
  if ! out="$(lesspaper_ngl_compose config 2>&1)"; then
    log_error "docker compose config failed"
    printf '%s\n' "${out}" | _lesspaper_ngl_redact >>"${LESSPAPER_NGL_LOG_FILE:-/dev/null}"
    return 1
  fi
  log_info "docker compose config ok"
  return 0
}

config_render_summary() {
  cat <<EOF
Install method:  ${LESSPAPER_NGL_METHOD}
Version:         ${LESSPAPER_NGL_VERSION_TAG} (image tag ${LESSPAPER_NGL_VERSION})
Directory:       ${LESSPAPER_NGL_INSTALL_DIR}
Project name:    ${LESSPAPER_NGL_COMPOSE_PROJECT}
Bind / port:     ${LESSPAPER_NGL_BIND}:${LESSPAPER_NGL_HTTP_PORT}
Expose OpenAPI:  ${LESSPAPER_NGL_EXPOSE_API}${LESSPAPER_NGL_EXPOSE_API:+ (host ${LESSPAPER_NGL_API_PORT:-9099})}
FRONTEND_ORIGIN: ${LESSPAPER_NGL_FRONTEND_ORIGIN}
Documents:       ${LESSPAPER_NGL_DOCS_PATH}
Consume:         ${LESSPAPER_NGL_CONSUME_PATH}
Export:          ${LESSPAPER_NGL_EXPORT_PATH}
Paddle cache:    ${LESSPAPER_NGL_PADDLE_PATH}
Extra GID:       ${LESSPAPER_NGL_EXTRA_GID:-none}
Admin user:      ${LESSPAPER_NGL_ADMIN_USERNAME:-admin}
EOF
}
