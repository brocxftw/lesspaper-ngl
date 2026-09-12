#!/usr/bin/env bash
set -euo pipefail

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
issues=draft ai=disabled headed="" journey=""
while [[ $# -gt 0 ]]; do
  case "$1" in
    --issues=off|--issues=draft|--issues=auto) issues="${1#*=}" ;;
    --ai=disabled|--ai=enabled) ai="${1#*=}" ;;
    --headed) headed="--headed" ;;
    --journey) shift; [[ $# -gt 0 ]] || { echo "--journey needs a UAT ID" >&2; exit 2; }; journey="$1" ;;
    --journey=*) journey="${1#*=}" ;;
    *) echo "Unknown option: $1" >&2; exit 2 ;;
  esac
  shift
done
export UAT_ISSUES="$issues" UAT_AI_PROFILE="$ai" UAT_RUN_ID="${UAT_RUN_ID:-$(date -u +%Y-%m-%dT%H-%M-%SZ)}"
export UAT_ORIGIN="${UAT_ORIGIN:-http://localhost:9398}"
if [[ "$ai" == disabled ]]; then export AI_ALLOW_REMOTE_EMBEDDINGS=false AI_ALLOW_REMOTE_QA=false AI_ALLOW_REMOTE_VISION=false; fi
args=(test -c "$root/frontend/playwright.uat.config.ts")
if [[ -n "$journey" ]]; then
  # Dependent journeys include the smallest deterministic setup journey.
  case "$journey" in
    UAT-021|UAT-030|UAT-040|UAT-050|UAT-080|UAT-081) args+=(--grep "UAT-010|UAT-021|$journey") ;;
    *) args+=(--grep "$journey") ;;
  esac
fi
[[ -n "$headed" ]] && args+=("$headed")
cd "$root/frontend"
npx playwright "${args[@]}"
