# Folium installer logging. Never write secrets.
# shellcheck shell=bash

LESSPAPER_NGL_LOG_FILE="${LESSPAPER_NGL_LOG_FILE:-}"

_lesspaper_ngl_redact() {
  # Redact assignment values for sensitive keys and long hex tokens.
  sed -E \
    -e 's/([A-Za-z0-9_]*(PASSWORD|SECRET|KEY|TOKEN|ENCRYPTION)[A-Za-z0-9_]*)=.*/\1=***REDACTED***/Ig' \
    -e 's#(postgresql(\+[a-z]+)?:\/\/)([^:@/]+):([^@/]+)@#\1\3:***REDACTED***@#g' \
    -e 's/\b[0-9a-fA-F]{32,}\b/***REDACTED***/g'
}

log_init() {
  local ts
  ts="$(date -u +%Y%m%d-%H%M%S)"
  LESSPAPER_NGL_LOG_FILE="${LESSPAPER_NGL_LOG_FILE:-/tmp/lesspaper-ngl-install-${ts}.log}"
  umask 077
  : >"${LESSPAPER_NGL_LOG_FILE}"
  log_info "lesspaper-ngl installer log started"
  log_info "timestamp_utc=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
}

log_info() {
  local line
  line="$(printf '%s %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$*" | _lesspaper_ngl_redact)"
  printf '%s\n' "${line}" >>"${LESSPAPER_NGL_LOG_FILE:-/dev/null}"
}

log_warn() {
  log_info "WARN: $*"
}

log_error() {
  log_info "ERROR: $*"
}

log_cmd() {
  # Log a command line after redaction; do not log output here.
  log_info "exec: $*"
}
