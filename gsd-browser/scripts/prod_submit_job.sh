#!/usr/bin/env bash
set -euo pipefail

GSD_MCP_URL="${GSD_MCP_URL:-https://gsd-prod-api.yellowplant-7a34cb33.eastus.azurecontainerapps.io/mcp}"
GSD_OUTPUT="${GSD_OUTPUT:-sse}"

if [[ "${1:-}" == "--json" ]]; then
  GSD_OUTPUT="json"
  shift
elif [[ "${1:-}" == "--sse" ]]; then
  GSD_OUTPUT="sse"
  shift
fi

if [[ -z "${GSD_TOKEN:-}" ]]; then
  echo "Missing GSD_TOKEN. Export it first:" >&2
  echo "  export GSD_TOKEN=\"<token-from-dashboard>\"" >&2
  exit 2
fi

URL="${1:-https://example.com}"
shift || true
if [[ $# -gt 0 ]]; then
  TASK="$*"
else
  TASK="Tell me the title of this page"
fi

payload="$(cat <<JSON
{
  "jsonrpc": "2.0",
  "id": 1,
  "method": "tools/call",
  "params": {
    "name": "web_eval_agent_submit",
    "arguments": {
      "url": "$URL",
      "task": "$TASK"
    }
  }
}
JSON
)"

out="$(curl -sN --max-time 30 -X POST "$GSD_MCP_URL" \
  -H "Content-Type: application/json" \
  -H "Accept: application/json, text/event-stream" \
  -H "Authorization: Bearer $GSD_TOKEN" \
  -d "$payload")"

if [[ "$GSD_OUTPUT" == "json" ]]; then
  printf '%s' "$out" | python -c $'import json,sys\nraw=sys.stdin.read()\ndata_lines=[line[6:] for line in raw.splitlines() if line.startswith(\"data: \")]\nif not data_lines: sys.exit(0)\nmsg=json.loads(data_lines[-1])\nresult=msg.get(\"result\") or {}\ncontent=result.get(\"content\") or []\ntext=None\nfor item in content:\n    if isinstance(item, dict) and item.get(\"type\") == \"text\":\n        text=item.get(\"text\")\n        break\nif isinstance(text, str):\n    try:\n        obj=json.loads(text)\n    except json.JSONDecodeError:\n        obj={\"raw_text\": text}\n    print(json.dumps(obj, ensure_ascii=False))\nelse:\n    print(json.dumps(msg, ensure_ascii=False))\n'
else
  printf '%s\n' "$out"
fi
