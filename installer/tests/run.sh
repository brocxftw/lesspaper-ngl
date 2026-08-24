#!/usr/bin/env bash
# Unit-like tests for installer helpers (no TUI, no live stack).
# shellcheck disable=SC1091,SC2034,SC2016
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
REPO_ROOT="$(cd "${ROOT}/.." && pwd)"
# shellcheck source=../lib/common.sh
source "${ROOT}/lib/common.sh"
# shellcheck source=../lib/logging.sh
source "${ROOT}/lib/logging.sh"
# shellcheck source=../lib/storage.sh
source "${ROOT}/lib/storage.sh"
# shellcheck source=../lib/network.sh
source "${ROOT}/lib/network.sh"
# shellcheck source=../lib/config.sh
source "${ROOT}/lib/config.sh"
# shellcheck source=../lib/state.sh
source "${ROOT}/lib/state.sh"
# shellcheck source=../lib/docker.sh
source "${ROOT}/lib/docker.sh"
# shellcheck source=../lib/ctl_update.sh
source "${ROOT}/lib/ctl_update.sh"

LESSPAPER_NGL_LOG_FILE="/dev/null"
FAILED=0
PASSED=0

assert_eq() {
  local name="$1" got="$2" want="$3"
  if [[ "${got}" == "${want}" ]]; then
    PASSED=$((PASSED + 1))
    printf 'ok  %s\n' "${name}"
  else
    FAILED=$((FAILED + 1))
    printf 'FAIL %s\n  got:  %s\n  want: %s\n' "${name}" "${got}" "${want}"
  fi
}

assert_ok() {
  local name="$1"
  shift
  if "$@"; then
    PASSED=$((PASSED + 1))
    printf 'ok  %s\n' "${name}"
  else
    FAILED=$((FAILED + 1))
    printf 'FAIL %s (expected success)\n' "${name}"
  fi
}

assert_fail() {
  local name="$1"
  shift
  if "$@"; then
    FAILED=$((FAILED + 1))
    printf 'FAIL %s (expected failure)\n' "${name}"
  else
    PASSED=$((PASSED + 1))
    printf 'ok  %s\n' "${name}"
  fi
}

assert_eq "strip v prefix" "$(config_strip_v_prefix "v0.1.16")" "0.1.16"
assert_eq "strip already plain" "$(config_strip_v_prefix "0.1.16")" "0.1.16"
assert_ok "pinned semver" config_is_pinned_version "0.1.16"
assert_ok "pinned with v" config_is_pinned_version "v0.1.16"
assert_ok "pinned beta" config_is_pinned_version "0.1.24-beta.1"
assert_ok "pinned beta with v" config_is_pinned_version "v0.1.24-beta.1"
assert_fail "reject latest" config_is_pinned_version "latest"
assert_fail "reject moving beta tag" config_is_pinned_version "beta"
assert_fail "reject empty" config_is_pinned_version ""


assert_eq "default install dir" "${LESSPAPER_NGL_DEFAULT_INSTALL_DIR}" "/opt/lesspaper-ngl"
assert_eq "default project" "${LESSPAPER_NGL_DEFAULT_PROJECT}" "lesspaper-ngl"
assert_eq "default github repo" "${LESSPAPER_NGL_GITHUB_REPO}" "brocxftw/lesspaper-ngl"

# Dual discovery: new pointer preferred, legacy accepted
DISC_TMP="$(mktemp -d)"
mkdir -p "${DISC_TMP}/new" "${DISC_TMP}/legacy"
echo '{"schema":1}' >"${DISC_TMP}/new/install-state.json"
echo '{"schema":1}' >"${DISC_TMP}/legacy/install-state.json"
# Simulate pointer files via temp etc — state_discover_dir reads absolute /etc paths,
# so exercise the env override path and /opt fallbacks via INSTALL_DIR.
LESSPAPER_NGL_INSTALL_DIR="${DISC_TMP}/new"
assert_eq "discover via new install dir env" "$(state_discover_dir)" "${DISC_TMP}/new"
unset LESSPAPER_NGL_INSTALL_DIR
FOLIUM_INSTALL_DIR="${DISC_TMP}/legacy"
assert_eq "discover via legacy FOLIUM_INSTALL_DIR" "$(state_discover_dir)" "${DISC_TMP}/legacy"
unset FOLIUM_INSTALL_DIR
rm -rf "${DISC_TMP}"

assert_eq "menu latest stable" "$(github_release_menu_label "v0.1.23" "v0.1.23")" "Latest stable"
assert_eq "menu beta" "$(github_release_menu_label "v0.1.24-beta.1" "v0.1.23")" "Beta"
assert_eq "menu older stable" "$(github_release_menu_label "v0.1.22" "v0.1.23")" "v0.1.22"

# Version resolution (latest/beta aliases → pinned tags) with mocked GitHub helpers.
# Overrides sourced lib functions for unit tests; ShellCheck cannot see indirect calls.
# shellcheck disable=SC2317
github_latest_tag() { printf 'v0.1.23\n'; }
# shellcheck disable=SC2317
github_latest_prerelease_tag() { printf 'v0.1.24-beta.2\n'; }

LESSPAPER_NGL_VERSION="latest"
LESSPAPER_NGL_VERSION_TAG=""
assert_ok "resolve latest alias" config_resolve_version_tag
assert_eq "resolve latest version" "${LESSPAPER_NGL_VERSION}" "0.1.23"
assert_eq "resolve latest tag" "${LESSPAPER_NGL_VERSION_TAG}" "v0.1.23"

LESSPAPER_NGL_VERSION="beta"
LESSPAPER_NGL_VERSION_TAG=""
assert_ok "resolve beta alias" config_resolve_version_tag
assert_eq "resolve beta version" "${LESSPAPER_NGL_VERSION}" "0.1.24-beta.2"
assert_eq "resolve beta tag" "${LESSPAPER_NGL_VERSION_TAG}" "v0.1.24-beta.2"

LESSPAPER_NGL_VERSION="0.1.20"
LESSPAPER_NGL_VERSION_TAG=""
assert_ok "resolve pinned plain" config_resolve_version_tag
assert_eq "resolve pinned version" "${LESSPAPER_NGL_VERSION}" "0.1.20"
assert_eq "resolve pinned tag" "${LESSPAPER_NGL_VERSION_TAG}" "v0.1.20"

LESSPAPER_NGL_VERSION=""
LESSPAPER_NGL_VERSION_TAG="v0.1.19-beta.1"
assert_ok "resolve from version_tag" config_resolve_version_tag
assert_eq "resolve from tag version" "${LESSPAPER_NGL_VERSION}" "0.1.19-beta.1"

# shellcheck disable=SC2317
github_latest_tag() { return 1; }
LESSPAPER_NGL_VERSION=""
LESSPAPER_NGL_VERSION_TAG=""
assert_ok "resolve empty falls back to prerelease" config_resolve_version_tag
assert_eq "resolve empty version" "${LESSPAPER_NGL_VERSION}" "0.1.24-beta.2"
assert_eq "resolve empty tag" "${LESSPAPER_NGL_VERSION_TAG}" "v0.1.24-beta.2"
# shellcheck disable=SC2317
github_latest_tag() { printf 'v0.1.23\n'; }

# Explicit request wins over values hydrated from install-state / .env (issue #65).
LESSPAPER_NGL_VERSION="0.1.24-beta.2"
LESSPAPER_NGL_VERSION_TAG="v0.1.24-beta.2"
config_prefer_requested_version "beta" "beta"
assert_eq "prefer requested version" "${LESSPAPER_NGL_VERSION}" "beta"
assert_eq "prefer requested tag" "${LESSPAPER_NGL_VERSION_TAG}" "beta"
assert_ok "resolve preferred beta alias" config_resolve_version_tag
assert_eq "preferred beta resolves version" "${LESSPAPER_NGL_VERSION}" "0.1.24-beta.2"
assert_eq "preferred beta resolves tag" "${LESSPAPER_NGL_VERSION_TAG}" "v0.1.24-beta.2"

LESSPAPER_NGL_VERSION="0.1.24-beta.2"
LESSPAPER_NGL_VERSION_TAG="v0.1.24-beta.2"
config_prefer_requested_version "0.1.24-beta.5" "v0.1.24-beta.5"
assert_eq "prefer pinned version" "${LESSPAPER_NGL_VERSION}" "0.1.24-beta.5"
assert_eq "prefer pinned tag" "${LESSPAPER_NGL_VERSION_TAG}" "v0.1.24-beta.5"

LESSPAPER_NGL_VERSION="0.1.24-beta.2"
LESSPAPER_NGL_VERSION_TAG="v0.1.24-beta.2"
config_prefer_requested_version "" ""
assert_eq "empty prior keeps hydrated version" "${LESSPAPER_NGL_VERSION}" "0.1.24-beta.2"
assert_eq "empty prior keeps hydrated tag" "${LESSPAPER_NGL_VERSION_TAG}" "v0.1.24-beta.2"

# .env may bump LESSPAPER_NGL_VERSION while install-state still has the old version_tag.
LESSPAPER_NGL_VERSION="0.1.24-beta.5"
LESSPAPER_NGL_VERSION_TAG="v0.1.24-beta.2"
config_sync_version_tag
assert_eq "sync version from env pin" "${LESSPAPER_NGL_VERSION}" "0.1.24-beta.5"
assert_eq "sync tag from env pin" "${LESSPAPER_NGL_VERSION_TAG}" "v0.1.24-beta.5"

LESSPAPER_NGL_VERSION="beta"
LESSPAPER_NGL_VERSION_TAG="v0.1.24-beta.2"
config_sync_version_tag
assert_eq "sync alias version" "${LESSPAPER_NGL_VERSION}" "beta"
assert_eq "sync alias tag" "${LESSPAPER_NGL_VERSION_TAG}" "beta"

# lesspaper-ngl update: default target + installer asset URL selection
assert_eq "update default version" "$(ctl_update_default_version)" "beta"
assert_eq "update normalize empty" "$(ctl_update_normalize_target "")" "beta"
assert_eq "update normalize beta" "$(ctl_update_normalize_target "beta")" "beta"
assert_eq "update normalize latest" "$(ctl_update_normalize_target "latest")" "latest"
assert_eq "update normalize pin plain" "$(ctl_update_normalize_target "0.1.24-beta.5")" "v0.1.24-beta.5"
assert_eq "update normalize pin v" "$(ctl_update_normalize_target "v0.1.24-beta.5")" "v0.1.24-beta.5"
assert_fail "update normalize junk" ctl_update_normalize_target "not-a-version"

assert_eq "update url latest" \
  "$(ctl_update_installer_url "latest")" \
  "https://github.com/brocxftw/lesspaper-ngl/releases/latest/download/install-lesspaper-ngl.sh"
assert_eq "update url beta" \
  "$(ctl_update_installer_url "beta")" \
  "https://github.com/brocxftw/lesspaper-ngl/releases/download/beta/install-lesspaper-ngl.sh"
assert_eq "update url pin" \
  "$(ctl_update_installer_url "v0.1.20")" \
  "https://github.com/brocxftw/lesspaper-ngl/releases/download/v0.1.20/install-lesspaper-ngl.sh"

# Restore real helpers for later tests that may call GitHub (none currently).
unset -f github_latest_tag github_latest_prerelease_tag
# shellcheck source=../lib/config.sh
source "${ROOT}/lib/config.sh"

filtered_tags="$(printf '%s\n' '[
  {"tag_name":"beta","draft":false,"prerelease":true},
  {"tag_name":"latest","draft":false,"prerelease":false},
  {"tag_name":"v0.1.24-beta.1","draft":false,"prerelease":true},
  {"tag_name":"v0.1.23","draft":false,"prerelease":false},
  {"tag_name":"v0.1.22","draft":true,"prerelease":false}
]' | github_filter_release_tags)"
assert_eq "filter keeps beta and stable" "$(printf '%s' "${filtered_tags}" | tr '\n' ' ')" "v0.1.24-beta.1 v0.1.23"
assert_ok "channel pointer beta" github_is_channel_pointer_tag "beta"
assert_ok "channel pointer latest" github_is_channel_pointer_tag "latest"
assert_fail "channel pointer version" github_is_channel_pointer_tag "v0.1.24-beta.1"

# load_existing_defaults preserves secrets / bind from an existing .env
KEEP_TMP="$(mktemp -d)"
mkdir -p "${KEEP_TMP}"
cat >"${KEEP_TMP}/.env" <<'ENV'
FOLIUM_SECRET_KEY=keep-secret-key-aaaaaaaaaaaaaaaaaaaaaaaaaaaaaa
FOLIUM_ENCRYPTION_KEY=keep-encryption-key-bbbbbbbbbbbbbbbbbbbbbbbbbb
POSTGRES_PASSWORD=keep-postgres-password
FOLIUM_ADMIN_PASSWORD=keep-admin-password
FOLIUM_ADMIN_USERNAME=admin
FOLIUM_VERSION=0.1.16
FRONTEND_ORIGIN=https://docs.example.com
FOLIUM_BIND=0.0.0.0
FOLIUM_HTTP_PORT=9398
FOLIUM_API_PORT=9099
COMPOSE_PROJECT_NAME=folium
FOLIUM_DOCUMENTS_HOST=/opt/folium/data/documents
FOLIUM_CONSUME_HOST=/opt/folium/data/consume
FOLIUM_EXPORT_HOST=/opt/folium/data/export
FOLIUM_PADDLE_CACHE_HOST=/opt/folium/data/paddleocr
CUSTOM_OPERATOR_KEY=leave-me-alone
ENV
chmod 600 "${KEEP_TMP}/.env"
LESSPAPER_NGL_INSTALL_DIR="${KEEP_TMP}"
LESSPAPER_NGL_KEEP_SECRETS=0
LESSPAPER_NGL_SECRET_KEY=""
LESSPAPER_NGL_ENCRYPTION_KEY=""
POSTGRES_PASSWORD=""
LESSPAPER_NGL_ADMIN_PASSWORD=""
LESSPAPER_NGL_BIND=""
LESSPAPER_NGL_FRONTEND_ORIGIN=""
LESSPAPER_NGL_COMPOSE_PROJECT=""
# Dual-read legacy keys (install.sh load_existing_defaults path).
if [[ -f "${LESSPAPER_NGL_INSTALL_DIR}/.env" ]]; then
  LESSPAPER_NGL_KEEP_SECRETS=1
  LESSPAPER_NGL_SECRET_KEY="$(config_env_get_any LESSPAPER_NGL_SECRET_KEY FOLIUM_SECRET_KEY || true)"
  LESSPAPER_NGL_ENCRYPTION_KEY="$(config_env_get_any LESSPAPER_NGL_ENCRYPTION_KEY FOLIUM_ENCRYPTION_KEY || true)"
  POSTGRES_PASSWORD="$(config_env_get POSTGRES_PASSWORD || true)"
  LESSPAPER_NGL_ADMIN_PASSWORD="$(config_env_get_any LESSPAPER_NGL_ADMIN_PASSWORD FOLIUM_ADMIN_PASSWORD || true)"
  LESSPAPER_NGL_BIND="$(config_env_get_any LESSPAPER_NGL_BIND FOLIUM_BIND || true)"
  LESSPAPER_NGL_FRONTEND_ORIGIN="$(config_env_get FRONTEND_ORIGIN || true)"
  LESSPAPER_NGL_COMPOSE_PROJECT="$(config_env_get COMPOSE_PROJECT_NAME || true)"
fi
assert_eq "keep secrets flag" "${LESSPAPER_NGL_KEEP_SECRETS}" "1"
assert_eq "keep secret key" "${LESSPAPER_NGL_SECRET_KEY}" "keep-secret-key-aaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
assert_eq "keep bind" "${LESSPAPER_NGL_BIND}" "0.0.0.0"
assert_eq "keep frontend origin" "${LESSPAPER_NGL_FRONTEND_ORIGIN}" "https://docs.example.com"
assert_eq "compose project preserved from .env" "${LESSPAPER_NGL_COMPOSE_PROJECT}" "folium"

# One-shot env migration FOLIUM_* → LESSPAPER_NGL_*
config_migrate_folium_env "${KEEP_TMP}/.env"
bak_hits="$(compgen -G "${KEEP_TMP}/.env.bak.*" | wc -l | tr -d ' ')"
assert_ok "migration backup exists" test "${bak_hits}" -ge 1
assert_ok "migrated version key" grep -q '^LESSPAPER_NGL_VERSION=0.1.16$' "${KEEP_TMP}/.env"
assert_ok "migrated secret key" grep -q '^LESSPAPER_NGL_SECRET_KEY=keep-secret-key-aaaaaaaaaaaaaaaaaaaaaaaaaaaaaa$' "${KEEP_TMP}/.env"
assert_ok "migrated bind" grep -q '^LESSPAPER_NGL_BIND=0.0.0.0$' "${KEEP_TMP}/.env"
assert_fail "legacy version removed" grep -q '^FOLIUM_VERSION=' "${KEEP_TMP}/.env"
assert_ok "postgres untouched" grep -q '^POSTGRES_PASSWORD=keep-postgres-password$' "${KEEP_TMP}/.env"
assert_ok "compose project untouched" grep -q '^COMPOSE_PROJECT_NAME=folium$' "${KEEP_TMP}/.env"
assert_ok "frontend origin untouched" grep -q '^FRONTEND_ORIGIN=https://docs.example.com$' "${KEEP_TMP}/.env"
assert_ok "unknown operator key intact" grep -q '^CUSTOM_OPERATOR_KEY=leave-me-alone$' "${KEEP_TMP}/.env"
# Updating LESSPAPER_NGL_VERSION alone must not rewrite secrets.
config_env_set LESSPAPER_NGL_VERSION "0.1.24-beta.2"
assert_ok "update version only" grep -q '^LESSPAPER_NGL_VERSION=0.1.24-beta.2$' "${KEEP_TMP}/.env"
assert_ok "secrets still present after version bump" grep -q '^LESSPAPER_NGL_SECRET_KEY=keep-secret-key-aaaaaaaaaaaaaaaaaaaaaaaaaaaaaa$' "${KEEP_TMP}/.env"
assert_ok "bind still present after version bump" grep -q '^LESSPAPER_NGL_BIND=0.0.0.0$' "${KEEP_TMP}/.env"
rm -rf "${KEEP_TMP}"

assert_ok "forbid /" storage_is_critical_forbidden_path "/"
assert_ok "forbid /etc" storage_is_critical_forbidden_path "/etc"
assert_ok "forbid /usr/bin" storage_is_critical_forbidden_path "/usr/bin"
assert_ok "forbid /boot" storage_is_critical_forbidden_path "/boot"
assert_fail "allow /opt/folium" storage_is_critical_forbidden_path "/opt/folium"
assert_fail "allow /opt/lesspaper-ngl" storage_is_critical_forbidden_path "/opt/lesspaper-ngl"
assert_fail "allow /mnt/data/docs" storage_is_critical_forbidden_path "/mnt/data/docs"
assert_fail "allow /root/sandbox" storage_is_critical_forbidden_path "/root/sandbox/folium"
assert_ok "risky /root/sandbox" storage_is_risky_install_path "/root/sandbox/folium"
assert_fail "not risky /opt" storage_is_risky_install_path "/opt/folium"

assert_ok "bind lan" network_bind_valid "0.0.0.0"
assert_ok "bind loopback" network_bind_valid "127.0.0.1"
assert_fail "bind other" network_bind_valid "10.0.0.1"
assert_ok "port 9398" network_port_valid "9398"
assert_fail "port 0" network_port_valid "0"
assert_fail "port junk" network_port_valid "abc"

assert_eq "origin loopback" "$(network_origin_for 127.0.0.1 9398 "")" "http://127.0.0.1:9398"
assert_eq "origin public" "$(network_origin_for 0.0.0.0 9398 "https://docs.example.com/")" "https://docs.example.com"

redacted="$(printf 'LESSPAPER_NGL_SECRET_KEY=abc\nPOSTGRES_PASSWORD=s3cret\nFRONTEND_ORIGIN=http://x\n' | _lesspaper_ngl_redact)"
assert_eq "redact secret key" "$(printf '%s\n' "${redacted}" | sed -n '1p')" "LESSPAPER_NGL_SECRET_KEY=***REDACTED***"
assert_eq "redact password" "$(printf '%s\n' "${redacted}" | sed -n '2p')" "POSTGRES_PASSWORD=***REDACTED***"
assert_eq "keep origin" "$(printf '%s\n' "${redacted}" | sed -n '3p')" "FRONTEND_ORIGIN=http://x"

assert_fail "postgres @ rejected" config_postgres_password_ok "foo@bar"
assert_ok "postgres hex ok" config_postgres_password_ok "deadbeef"

TMP="$(mktemp -d)"
trap 'rm -rf "${TMP}"' EXIT

cp "${REPO_ROOT}/docker-compose.yml" "${TMP}/docker-compose.yml"
config_strip_compose_ports "${TMP}/docker-compose.yml"
if grep -q '9099:8000' "${TMP}/docker-compose.yml"; then
  FAILED=$((FAILED + 1))
  printf 'FAIL compose strip left api 9099\n'
else
  PASSED=$((PASSED + 1))
  printf 'ok  compose strip api port\n'
fi
if grep -q '9398:80' "${TMP}/docker-compose.yml"; then
  FAILED=$((FAILED + 1))
  printf 'FAIL compose strip left web 9398\n'
else
  PASSED=$((PASSED + 1))
  printf 'ok  compose strip web port\n'
fi

LESSPAPER_NGL_INSTALL_DIR="${TMP}"
LESSPAPER_NGL_BIND="127.0.0.1"
LESSPAPER_NGL_HTTP_PORT="18080"
LESSPAPER_NGL_EXPOSE_API="0"
LESSPAPER_NGL_EXTRA_GID="10000"
config_write_override
assert_ok "override has ui port" grep -q 'LESSPAPER_NGL_BIND' "${TMP}/docker-compose.override.yml"
assert_ok "override has extra gid" grep -q '10000' "${TMP}/docker-compose.override.yml"
assert_fail "override omits api publish" grep -q '9099:8000' "${TMP}/docker-compose.override.yml"

LESSPAPER_NGL_EXPOSE_API="1"
LESSPAPER_NGL_API_PORT="9099"
config_write_override
assert_ok "override can publish api" grep -q 'LESSPAPER_NGL_API_PORT' "${TMP}/docker-compose.override.yml"

assert_ok "blocked invalid port" network_port_blocked "0"

LESSPAPER_NGL_VERSION="0.1.16"
LESSPAPER_NGL_SECRET_KEY="unit-test-secret"
LESSPAPER_NGL_ENCRYPTION_KEY="unit-test-encryption"
POSTGRES_PASSWORD="unit-test-postgres"
LESSPAPER_NGL_ADMIN_PASSWORD="unit-test-admin"
LESSPAPER_NGL_FRONTEND_ORIGIN="http://127.0.0.1:18080"
LESSPAPER_NGL_DOCS_PATH="${TMP}/data/documents"
LESSPAPER_NGL_CONSUME_PATH="${TMP}/data/consume"
LESSPAPER_NGL_EXPORT_PATH="${TMP}/data/export"
LESSPAPER_NGL_PADDLE_PATH="${TMP}/data/paddleocr"
LESSPAPER_NGL_COMPOSE_PROJECT="lesspaper-ngl-unit"
mkdir -p "${LESSPAPER_NGL_DOCS_PATH}" "${LESSPAPER_NGL_CONSUME_PATH}" "${LESSPAPER_NGL_EXPORT_PATH}" "${LESSPAPER_NGL_PADDLE_PATH}"
config_write_env
mode="$(stat -c '%a' "${TMP}/.env")"
assert_eq "env mode 600" "${mode}" "600"
assert_ok "env pins version" grep -q '^LESSPAPER_NGL_VERSION=0.1.16$' "${TMP}/.env"
assert_ok "env has backups host" grep -q '^LESSPAPER_NGL_BACKUPS_HOST=' "${TMP}/.env"
assert_ok "env has backups path" grep -q '^BACKUPS_PATH=/backups$' "${TMP}/.env"
assert_fail "env not latest" grep -q '^LESSPAPER_NGL_VERSION=latest$' "${TMP}/.env"
config_env_set LESSPAPER_NGL_VERSION "0.1.17"
assert_ok "env set version" grep -q '^LESSPAPER_NGL_VERSION=0.1.17$' "${TMP}/.env"
config_env_set LESSPAPER_NGL_VERSION "0.1.16"

export LESSPAPER_NGL_METHOD=image LESSPAPER_NGL_VERSION_TAG=v0.1.16
state_write
assert_ok "state exists" test -f "${TMP}/install-state.json"
assert_fail "state has no secret key" grep -qi 'unit-test-secret' "${TMP}/install-state.json"
assert_fail "state has no admin password" grep -qi 'unit-test-admin' "${TMP}/install-state.json"
assert_eq "state version" "$(python3 -c 'import json; print(json.load(open("'"${TMP}"'/install-state.json"))["version"])')" "0.1.16"

if command -v docker >/dev/null 2>&1 && docker compose version >/dev/null 2>&1; then
  LESSPAPER_NGL_EXPOSE_API="0"
  LESSPAPER_NGL_EXTRA_GID=""
  config_write_override
  if (cd "${TMP}" && docker compose -p lesspaper-ngl-unit -f docker-compose.yml -f docker-compose.override.yml config >/dev/null); then
    PASSED=$((PASSED + 1))
    printf 'ok  docker compose config\n'
  else
    FAILED=$((FAILED + 1))
    printf 'FAIL docker compose config\n'
  fi
else
  printf 'skip docker compose config (docker not available)\n'
fi

PACK_DIR="$(mktemp -d)"
PACK="${PACK_DIR}/install-lesspaper-ngl.sh"
if bash "${ROOT}/pack.sh" "${PACK}" && bash -n "${PACK}"; then
  PASSED=$((PASSED + 1))
  printf 'ok  pack.sh bash -n\n'
else
  FAILED=$((FAILED + 1))
  printf 'FAIL pack.sh\n'
fi
if [[ -f "${PACK_DIR}/install-folium.sh" ]] && cmp -s "${PACK}" "${PACK_DIR}/install-folium.sh"; then
  PASSED=$((PASSED + 1))
  printf 'ok  pack produces install-folium.sh copy\n'
else
  FAILED=$((FAILED + 1))
  printf 'FAIL pack did not produce identical install-folium.sh\n'
fi
if grep -q '^LESSPAPER_NGL_PACKED=1$' "${PACK}" \
  && grep -q 'lesspaper_ngl_install_packed_ctl' "${PACK}" \
  && grep -q 'lesspaper-ngl interactive installer' "${PACK}" \
  && grep -q 'ctl_update_installer_url' "${PACK}" \
  && grep -q '/usr/local/bin/lesspaper-ngl' "${PACK}"; then
  PASSED=$((PASSED + 1))
  printf 'ok  packed installer is standalone\n'
else
  FAILED=$((FAILED + 1))
  printf 'FAIL packed installer missing expected markers\n'
fi
rm -rf "${PACK_DIR}"

printf '\n%d passed, %d failed\n' "${PASSED}" "${FAILED}"
[[ "${FAILED}" -eq 0 ]]
