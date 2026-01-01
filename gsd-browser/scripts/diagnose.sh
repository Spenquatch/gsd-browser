#!/usr/bin/env bash
# Collect diagnostics about the MCP template environment.
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
export PYTHONPATH="$ROOT_DIR/src:${PYTHONPATH:-}"
PY_BIN="$ROOT_DIR/.venv/bin/python"
if [ ! -x "$PY_BIN" ]; then
  PY_BIN="$(command -v python3)"
fi

headline() {
  printf '\n=== %s ===\n' "$1"
}

headline "System"
uname -a || true
$PY_BIN --version || true

headline "Tooling availability"
for tool in uv poetry pipx gsd-browser; do
  if command -v "$tool" >/dev/null 2>&1; then
    echo "- $tool: $(command -v "$tool")"
  else
    echo "- $tool: not found"
  fi
done

headline "Environment vars"
printenv | grep -E 'ANTHROPIC|GSD_BROWSER_MODEL|GSD_BROWSER_JSON_LOGS|LOG_LEVEL' || echo "(none set)"

headline "Config validation"
 "$PY_BIN" - <<'PY'
from gsd_browser.config import load_settings

try:
    settings = load_settings(strict=False)
    print(f"Config OK: model={settings.model}, log_level={settings.log_level}")
except Exception as exc:  # noqa: BLE001
    print(f"Config error: {exc}")
PY

headline "MCP config snippet"
$PY_BIN "$ROOT_DIR/scripts/print-mcp-config.py"

headline "Placeholder smoke"
printf 'ping\n' | "$PY_BIN" -m gsd_browser.cli serve --once || true
