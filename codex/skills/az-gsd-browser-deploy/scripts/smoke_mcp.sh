#!/usr/bin/env bash
set -euo pipefail

DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=/dev/null
source "$DIR/_lib.sh"

require_cmd curl

[ -n "${GSD_TOKEN:-}" ] || die "GSD_TOKEN is not set"

FQDN="$(containerapp_fqdn)"
BASE="https://${FQDN}"
MCP_URL="${BASE}/mcp"

echo "== mcp initialize =="
curl -sS -i -N --max-time 20 -X POST "$MCP_URL" \
  -H "Content-Type: application/json" \
  -H "Accept: application/json, text/event-stream" \
  -H "Authorization: Bearer ${GSD_TOKEN}" \
  --data '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2024-11-05","capabilities":{},"clientInfo":{"name":"smoke_mcp","version":"1.0"}}}' \
  | head -c 600
echo

echo "== mcp tools/list =="
curl -sS -i -N --max-time 20 -X POST "$MCP_URL" \
  -H "Content-Type: application/json" \
  -H "Accept: application/json, text/event-stream" \
  -H "Authorization: Bearer ${GSD_TOKEN}" \
  --data '{"jsonrpc":"2.0","id":2,"method":"tools/list","params":{}}' \
  | head -c 600
echo

