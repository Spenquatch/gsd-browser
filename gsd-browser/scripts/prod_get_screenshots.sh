#!/usr/bin/env bash
set -euo pipefail

GSD_MCP_URL="${GSD_MCP_URL:-https://gsd-prod-api.yellowplant-7a34cb33.eastus.azurecontainerapps.io/mcp}"

if [[ -z "${GSD_TOKEN:-}" ]]; then
  echo "Missing GSD_TOKEN. Export it first:" >&2
  echo "  export GSD_TOKEN=\"<token-from-dashboard>\"" >&2
  exit 2
fi

SESSION_ID="${1:-}"
LAST_N="${2:-5}"
SCREENSHOT_TYPE="${3:-agent_step}"

if [[ -z "$SESSION_ID" ]]; then
  echo "Usage: $0 <session-id> [last-n] [agent_step|stream_sample|all]" >&2
  echo "" >&2
  echo "Tip: get session_id from job_wait:" >&2
  echo "  ./gsd-browser/scripts/prod_job_wait.sh --json <job-id> 240 | jq -r .session_id" >&2
  exit 2
fi

OUT_DIR="${GSD_SCREENSHOT_OUT_DIR:-artifacts/screenshots/${SESSION_ID}}"
mkdir -p "$OUT_DIR"

payload="$(cat <<JSON
{
  "jsonrpc": "2.0",
  "id": 4,
  "method": "tools/call",
  "params": {
    "name": "get_screenshots",
    "arguments": {
      "session_id": "$SESSION_ID",
      "last_n": $LAST_N,
      "screenshot_type": "$SCREENSHOT_TYPE",
      "include_images": true
    }
  }
}
JSON
)"

out="$(curl -sN --max-time 60 -X POST "$GSD_MCP_URL" \
  -H "Content-Type: application/json" \
  -H "Accept: application/json, text/event-stream" \
  -H "Authorization: Bearer $GSD_TOKEN" \
  -d "$payload")"

tmp_sse="$(mktemp)"
trap 'rm -f "$tmp_sse"' EXIT
printf '%s' "$out" > "$tmp_sse"

python - "$OUT_DIR" "$tmp_sse" <<'PY'
import base64
import json
import os
import sys
import urllib.request

out_dir = sys.argv[1]
raw_path = sys.argv[2]
with open(raw_path, "r", encoding="utf-8", errors="replace") as f:
    raw = f.read()

data_lines = [line[6:] for line in raw.splitlines() if line.startswith("data: ")]
if not data_lines:
    print("No SSE data lines returned.", file=sys.stderr)
    sys.exit(1)

msg = json.loads(data_lines[-1])
result = msg.get("result") or {}
content = result.get("content") or []

payload_obj = None
images = []
for item in content:
    if not isinstance(item, dict):
        continue
    if item.get("type") == "text" and payload_obj is None:
        text = item.get("text")
        if isinstance(text, str):
            payload_obj = json.loads(text)
    elif item.get("type") == "image":
        data = item.get("data")
        mime = item.get("mimeType") or "image/png"
        if isinstance(data, str):
            images.append({"data": data, "mimeType": str(mime)})

if payload_obj is None:
    print("No text payload returned.", file=sys.stderr)
    sys.exit(1)

os.makedirs(out_dir, exist_ok=True)
meta_path = os.path.join(out_dir, "get_screenshots.json")
with open(meta_path, "w", encoding="utf-8") as f:
    json.dump(payload_obj, f, ensure_ascii=False, indent=2)

shots = payload_obj.get("screenshots") or []
saved_paths = []

def _ext(mime: str) -> str:
    mime = (mime or "").lower()
    if "png" in mime:
        return "png"
    if "jpeg" in mime or "jpg" in mime:
        return "jpg"
    if "webp" in mime:
        return "webp"
    return "bin"

def _safe(s: object) -> str:
    return "".join(c if c.isalnum() or c in ("-", "_", ".") else "_" for c in str(s or ""))

for idx, shot in enumerate(shots):
    if not isinstance(shot, dict):
        continue
    shot_id = _safe(shot.get("id") or f"shot_{idx}")
    shot_type = _safe(shot.get("type") or "shot")
    step = shot.get("step")
    step_part = f"step{_safe(step)}_" if step is not None else ""
    ts = shot.get("timestamp")
    ts_part = f"{int(float(ts))}_" if ts is not None else ""
    mime = str(shot.get("mime_type") or "image/png")

    path = os.path.join(out_dir, f"{ts_part}{shot_type}_{step_part}{shot_id}.{_ext(mime)}")

    wrote = False
    if idx < len(images):
        try:
            data = base64.b64decode(images[idx]["data"])
            with open(path, "wb") as f:
                f.write(data)
            wrote = True
        except Exception:
            wrote = False

    if not wrote:
        artifact = shot.get("artifact") or {}
        url = artifact.get("url")
        if isinstance(url, str) and url:
            try:
                with urllib.request.urlopen(url, timeout=30) as resp:
                    data = resp.read()
                with open(path, "wb") as f:
                    f.write(data)
                wrote = True
            except Exception:
                wrote = False

    if wrote:
        saved_paths.append(path)

print(meta_path)
for p in saved_paths:
    print(p)
PY
