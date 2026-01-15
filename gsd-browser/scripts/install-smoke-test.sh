#!/usr/bin/env bash
# Full install smoke test:
# - installs via ./tools/install.sh (pipx)
# - launches dashboard + runs a Playwright task via `gsd mcp smoke`
# - validates /healthz, dashboard HTML, and screenshot capture
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

BIN="${GSD_BIN:-$HOME/.local/bin/gsd}"
ENV_FILE_DEFAULT="$ROOT_DIR/.env"

HOST="${GSD_SMOKE_HOST:-127.0.0.1}"
PORT="${GSD_SMOKE_PORT:-5009}"
URL="${GSD_SMOKE_URL:-https://example.com}"

if [ ! -f "$ENV_FILE_DEFAULT" ]; then
  echo "Missing $ENV_FILE_DEFAULT. Create it from .env.example first." >&2
  exit 1
fi

echo "[install-smoke] Installing via pipx..."
./tools/install.sh

if [ ! -x "$BIN" ]; then
  echo "[install-smoke] Expected installed binary at $BIN but it was not found." >&2
  echo "[install-smoke] Check your PATH or set GSD_BIN explicitly." >&2
  exit 1
fi

if [ -x "$HOME/.local/bin/playwright" ]; then
  echo "[install-smoke] Ensuring Playwright Chromium is installed..."
  "$HOME/.local/bin/playwright" install chromium >/dev/null
fi

TMP_DIR="$(mktemp -d)"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
REPORT_PATH="${GSD_INSTALL_SMOKE_REPORT:-/tmp/gsd-install-smoke-report.${STAMP}.json}"

cleanup() {
  rm -rf "$TMP_DIR"
}
trap cleanup EXIT

echo "[install-smoke] Running end-to-end smoke (dashboard + Playwright + screenshots)..."
(
  cd "$TMP_DIR"
  export GSD_ENV_FILE="$ENV_FILE_DEFAULT"
  export STREAMING_MODE="cdp"
  export STREAMING_QUALITY="med"
  "$BIN" validate-llm >/dev/null
  "$BIN" mcp-tool-smoke \
    --host "$HOST" \
    --port "$PORT" \
    --timeout 40 \
    --url "$URL" \
    --expect-streaming-mode cdp \
    --output "$REPORT_PATH" \
    --verbose \
    >/dev/null
)

python3 - <<PY
import json
from pathlib import Path

path = Path("$REPORT_PATH")
data = json.loads(path.read_text(encoding="utf-8"))

def req(cond: bool, msg: str) -> None:
    if not cond:
        raise SystemExit(f"[install-smoke] FAIL: {msg}")

tool = data.get("tool", {})
dash = data.get("dashboard", {})
healthz = data.get("healthz", {})

req(tool.get("success") is True, f"tool.success expected True, got {tool.get('success')!r}")
req(dash.get("reachable") is True, f"dashboard.reachable expected True, got {dash.get('reachable')!r}")
req(dash.get("html_ok") is True, f"dashboard.html_ok expected True, got {dash.get('html_ok')!r}")
req(healthz.get("ok") is True, f"healthz.ok expected True, got {healthz.get('ok')!r}")
req(
    healthz.get("streaming_mode_match") is True,
    f"healthz.streaming_mode_match expected True, got {healthz.get('streaming_mode_match')!r}",
)

sv = tool.get("screenshot_validation") or {}
req(sv.get("agent_step_count", 0) >= 1, f"expected >=1 agent_step screenshot, got {sv.get('agent_step_count')!r}")
req(sv.get("agent_step_png_ok") is True, f"expected valid PNG agent_step screenshot, got {sv.get('agent_step_png_ok')!r}")

print("[install-smoke] PASS")
print(f"[install-smoke] Report: {path}")
PY
