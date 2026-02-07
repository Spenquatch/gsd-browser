#!/usr/bin/env bash
set -euo pipefail

DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=/dev/null
source "$DIR/_lib.sh"

require_cmd az
require_cmd curl

RG="$(default_rg)"
APP="$(default_app)"

REV="${1:-}"
if [ -z "$REV" ]; then
  REV="$(az containerapp show -n "$APP" -g "$RG" --query "properties.latestRevisionName" -o tsv)"
fi

FQDN="$(containerapp_fqdn)"
BASE="https://${FQDN}"
HEALTH_URL="${BASE}/.well-known/oauth-protected-resource"
MCP_URL="${BASE}/mcp"

echo "== wait for healthy =="
for i in $(seq 1 30); do
  state_json="$(az containerapp revision show -n "$APP" -g "$RG" --revision "$REV" --query '{runningState:properties.runningState,healthState:properties.healthState,replicas:properties.replicas,active:properties.active}' -o json)"
  running="$(echo "$state_json" | python -c 'import json,sys; print(json.load(sys.stdin).get(\"runningState\"))')"
  health="$(echo "$state_json" | python -c 'import json,sys; print(json.load(sys.stdin).get(\"healthState\"))')"
  echo "$i runningState=$running healthState=$health revision=$REV"
  if [ "$running" = "Running" ] && [ "$health" = "Healthy" ]; then
    break
  fi
  sleep 5
done

echo
echo "== health probe loop (60s) =="
ok=0
fail=0
for _ in $(seq 1 12); do
  if curl -fsS --max-time 5 "$HEALTH_URL" >/dev/null; then
    ok=$((ok+1))
  else
    fail=$((fail+1))
  fi
  sleep 5
done
echo "health_ok=$ok health_fail=$fail url=$HEALTH_URL"

if [ -n "${GSD_TOKEN:-}" ]; then
  echo
  echo "== mcp initialize (20s max) =="
  curl -sS -i -N --max-time 20 -X POST "$MCP_URL" \
    -H "Content-Type: application/json" \
    -H "Accept: application/json, text/event-stream" \
    -H "Authorization: Bearer ${GSD_TOKEN}" \
    --data '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2024-11-05","capabilities":{},"clientInfo":{"name":"verify_prod_api","version":"1.0"}}}' \
    | head -c 600 || true
  echo
else
  echo
  echo "note: set GSD_TOKEN to run MCP smoke checks"
fi

