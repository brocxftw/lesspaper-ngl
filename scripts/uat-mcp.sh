#!/usr/bin/env bash
# MCP UAT against a running lesspaper-ngl instance (API + worker + UI).
# Usage:
#   ./scripts/uat-mcp.sh
#   ORIGIN=http://localhost:8000 ./scripts/uat-mcp.sh          # API port
#   ORIGIN=http://localhost:8080 ./scripts/uat-mcp.sh          # Vite / nginx origin (default)
set -euo pipefail

ORIGIN="${ORIGIN:-http://localhost:8080}"
USER_NAME="${LESSPAPER_NGL_ADMIN_USERNAME:-admin}"
PASSWORD="${LESSPAPER_NGL_ADMIN_PASSWORD:-changeme}"
HANDSHAKE="${MCP_PROTOCOL_VERSION:-2025-11-25}"
SAMPLE="${SAMPLE:-backend/tests/fixtures/sample.txt}"
COOKIE_JAR="$(mktemp)"
trap 'rm -f "$COOKIE_JAR"' EXIT

pass=0
fail=0
ok() { echo "  PASS  $*"; pass=$((pass + 1)); }
bad() { echo "  FAIL  $*"; fail=$((fail + 1)); }
need() { [[ -n "${1:-}" ]] || { echo "missing: $2" >&2; exit 1; }; }

echo "== lesspaper-ngl MCP UAT  origin=$ORIGIN"

csrf="$(
  curl -sS -c "$COOKIE_JAR" -b "$COOKIE_JAR" \
    -H 'Content-Type: application/json' \
    -d "{\"username\":\"$USER_NAME\",\"password\":\"$PASSWORD\"}" \
    "$ORIGIN/api/auth/login" | jq -r .csrf_token
)"
need "$csrf" "login csrf (check $ORIGIN and admin password)"
ok "login as $USER_NAME"

token="$(
  curl -sS -c "$COOKIE_JAR" -b "$COOKIE_JAR" \
    -H "X-CSRF-Token: $csrf" \
    -H 'Content-Type: application/json' \
    -d '{"name":"uat-mcp"}' \
    "$ORIGIN/api/auth/tokens" | jq -r .token
)"
need "$token" "API token"
[[ "$token" == fol_* ]] && ok "create token (secret once, prefix fol_)" || bad "token format: $token"

code="$(curl -sS -o /dev/null -w '%{http_code}' -X POST "$ORIGIN/mcp" \
  -H 'Content-Type: application/json' \
  -d '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{}}')"
[[ "$code" == 401 ]] && ok "/mcp without Bearer → 401" || bad "/mcp without Bearer → $code (want 401)"

code="$(curl -sS -o /dev/null -w '%{http_code}' -X POST "$ORIGIN/mcp" \
  -b "$COOKIE_JAR" \
  -H 'Content-Type: application/json' \
  -d '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{}}')"
[[ "$code" == 401 ]] && ok "/mcp with session cookie only → 401" || bad "/mcp cookie-only → $code (want 401)"

mcp() {
  local method="$1"
  local params="$2"
  curl -sS -X POST "$ORIGIN/mcp" \
    -H "Authorization: Bearer $token" \
    -H 'Accept: application/json, text/event-stream' \
    -H 'Content-Type: application/json' \
    -H "MCP-Protocol-Version: $HANDSHAKE" \
    -d "{\"jsonrpc\":\"2.0\",\"id\":1,\"method\":\"$method\",\"params\":$params}"
}

init="$(mcp initialize "{\"protocolVersion\":\"$HANDSHAKE\",\"capabilities\":{},\"clientInfo\":{\"name\":\"uat\",\"version\":\"0.0.1\"}}")"
echo "$init" | jq -e '.result.protocolVersion' >/dev/null && ok "initialize" || bad "initialize: $init"

listed="$(mcp tools/list '{}')"
names="$(echo "$listed" | jq -r '[.result.tools[].name] | sort | join(",")')"
[[ "$names" == "get_document,list_folder,search_documents,search_evidence" ]] \
  && ok "tools/list exactly four tools" \
  || bad "tools/list got: $names"

tool() {
  local name="$1"
  local args="$2"
  mcp tools/call "{\"name\":\"$name\",\"arguments\":$args}"
}

payload() { jq -r '
  if .result.structuredContent != null then .result.structuredContent
  elif .result.content[0].text then (try (.result.content[0].text | fromjson) catch .result.content[0].text)
  else .result end
'; }

empty="$(tool search_evidence '{"query":""}')"
echo "$empty" | jq -e '.result.isError == true or has("error")' >/dev/null \
  && ok "search_evidence empty query errors" \
  || bad "empty query: $empty"

upload="$(
  curl -sS -c "$COOKIE_JAR" -b "$COOKIE_JAR" \
    -H "X-CSRF-Token: $csrf" \
    -F "file=@${SAMPLE};type=text/plain" \
    "$ORIGIN/api/documents/upload"
)"
doc_id="$(echo "$upload" | jq -r .id)"
need "$doc_id" "upload id ($upload)"
ok "upload sample.txt  id=$doc_id"

for _ in $(seq 1 30); do
  extracted="$(
    curl -sS -c "$COOKIE_JAR" -b "$COOKIE_JAR" "$ORIGIN/api/documents/$doc_id" | jq -r .text_extracted
  )"
  [[ "$extracted" == "true" ]] && break
  sleep 0.5
done
[[ "$extracted" == "true" ]] && ok "text extracted" || bad "text not extracted (is worker running?)"

got="$(tool get_document "{\"document_id\":\"$doc_id\"}" | payload)"
echo "$got" | jq -e --arg id "$doc_id" '.document.id == $id and .text_available == true and (.pages|length) > 0' >/dev/null \
  && ok "get_document returns metadata + page text" \
  || bad "get_document: $got"

missing="$(tool get_document '{"document_id":"00000000-0000-0000-0000-000000000000"}')"
echo "$missing" | jq -e '.result.isError == true or has("error")' >/dev/null \
  && ok "get_document unknown id errors" \
  || bad "missing document: $missing"

folder_id="$(
  curl -sS -c "$COOKIE_JAR" -b "$COOKIE_JAR" \
    -H "X-CSRF-Token: $csrf" \
    -H 'Content-Type: application/json' \
    -d '{"name":"MCP UAT"}' \
    "$ORIGIN/api/folders" | jq -r .id
)"
need "$folder_id" "folder id"
curl -sS -o /dev/null -c "$COOKIE_JAR" -b "$COOKIE_JAR" \
  -H "X-CSRF-Token: $csrf" \
  -H 'Content-Type: application/json' \
  -X PATCH \
  -d "{\"folder_id\":\"$folder_id\",\"needs_review\":false}" \
  "$ORIGIN/api/documents/$doc_id/metadata"
process="$(
  curl -sS -c "$COOKIE_JAR" -b "$COOKIE_JAR" \
    -H "X-CSRF-Token: $csrf" \
    -H 'Content-Type: application/json' \
    -d "{\"document_ids\":[\"$doc_id\"]}" \
    "$ORIGIN/api/documents/process"
)"
echo "$process" | jq -e --arg id "$doc_id" '.processed[0].id == $id' >/dev/null \
  && ok "process inbox → library" \
  || bad "process: $process"

indexed=false
for _ in $(seq 1 40); do
  indexed="$(
    curl -sS -c "$COOKIE_JAR" -b "$COOKIE_JAR" "$ORIGIN/api/documents/$doc_id" | jq -r .document_indexed
  )"
  [[ "$indexed" == "true" ]] && break
  sleep 0.5
done
[[ "$indexed" == "true" ]] && ok "document indexed" || bad "not indexed (search will be empty)"

evidence="$(tool search_evidence '{"query":"LPPSA refinance","mode":"keyword"}' | payload)"
echo "$evidence" | jq -e --arg id "$doc_id" '[.items[] | select(.document_id == $id)] | length > 0' >/dev/null \
  && ok "search_evidence keyword hit" \
  || bad "search_evidence: $evidence"

docs="$(tool search_documents '{"query":"LPPSA refinance","mode":"keyword"}' | payload)"
echo "$docs" | jq -e --arg id "$doc_id" '[.items[] | select(.id == $id)] | length > 0' >/dev/null \
  && ok "search_documents keyword hit" \
  || bad "search_documents: $docs"

tree="$(tool list_folder '{}' | payload)"
echo "$tree" | jq -e '.folders | length > 0' >/dev/null \
  && ok "list_folder root tree" \
  || bad "list_folder root: $tree"

one="$(tool list_folder "{\"folder_id\":\"$folder_id\",\"recursive\":false}" | payload)"
echo "$one" | jq -e --arg id "$doc_id" '[.documents[] | select(.id == $id)] | length > 0' >/dev/null \
  && ok "list_folder one folder includes the document" \
  || bad "list_folder one: $one"

echo
echo "== $pass passed, $fail failed"
[[ "$fail" -eq 0 ]]
