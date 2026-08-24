# Helpers for `lesspaper-ngl update` (download release installer + noninteractive --update).
# shellcheck shell=bash

ctl_update_default_version() {
  printf 'beta'
}

# Normalize an operator arg for --version and installer URL selection.
# Empty → default (beta). Aliases stay as latest|beta. Pins become v-prefixed.
ctl_update_normalize_target() {
  local raw="${1:-}"
  if [[ -z "${raw}" ]]; then
    ctl_update_default_version
    return 0
  fi
  local stripped
  stripped="$(config_strip_v_prefix "${raw}")"
  case "${stripped}" in
    latest|beta)
      printf '%s' "${stripped}"
      return 0
      ;;
  esac
  if config_is_pinned_version "${stripped}"; then
    printf 'v%s' "${stripped}"
    return 0
  fi
  return 1
}

# Newest GitHub prerelease tag (vX.Y.Z-beta.N). Override in unit tests.
ctl_update_latest_prerelease_tag() {
  local tag plain
  local repo="${LESSPAPER_NGL_GITHUB_REPO:-${FOLIUM_GITHUB_REPO:-brocxftw/lesspaper-ngl}}"
  while IFS= read -r tag; do
    [[ -n "${tag}" ]] || continue
    plain="$(config_strip_v_prefix "${tag}")"
    if [[ "${plain}" == "beta" || "${plain}" == "latest" ]]; then
      continue
    fi
    if [[ "${plain}" == *-* ]]; then
      printf '%s\n' "${tag}"
      return 0
    fi
  done < <(
    curl -fsSL --max-time 20 \
      -H "Accept: application/vnd.github+json" \
      "https://api.github.com/repos/${repo}/releases?per_page=30" \
      | python3 -c 'import json,sys
channel={"beta","latest"}
for rel in json.load(sys.stdin):
    if rel.get("draft"):
        continue
    tag=rel.get("tag_name") or ""
    if tag in channel or tag.lstrip("v") in channel:
        continue
    print(tag)
'
  )
  return 1
}

# Preferred asset is install-lesspaper-ngl.sh; callers may fall back to install-folium.sh.
ctl_update_installer_asset_names() {
  printf '%s\n' "install-lesspaper-ngl.sh" "install-folium.sh"
}

# Download URL for the preferred installer asset for a normalized target (latest|beta|v…).
ctl_update_installer_url() {
  local target="${1:-}"
  local asset="${2:-install-lesspaper-ngl.sh}"
  local repo="${LESSPAPER_NGL_GITHUB_REPO:-${FOLIUM_GITHUB_REPO:-brocxftw/lesspaper-ngl}}"
  case "${target}" in
    latest)
      printf 'https://github.com/%s/releases/latest/download/%s' "${repo}" "${asset}"
      ;;
    beta)
      printf 'https://github.com/%s/releases/download/beta/%s' "${repo}" "${asset}"
      ;;
    v*)
      printf 'https://github.com/%s/releases/download/%s/%s' "${repo}" "${target}" "${asset}"
      ;;
    *)
      return 1
      ;;
  esac
}
