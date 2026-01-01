#!/usr/bin/env bash
# Run basic smoke tests for the MCP template.
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
export PYTHONPATH="$ROOT_DIR/src:${PYTHONPATH:-}"

PY_BIN="$ROOT_DIR/.venv/bin/python"
if [ ! -x "$PY_BIN" ]; then
  PY_BIN="$(command -v python3)"
fi

if ls "$ROOT_DIR"/tests/smoke/*.py >/dev/null 2>&1; then
  "$PY_BIN" -m pytest tests/smoke "$@"
else
  echo "[smoke] No pytest suites yet; skipping tests/smoke."
fi

printf '\n[smoke] CLI round trip...\n'
printf 'hello\n' | "$PY_BIN" -m gsd_browser.cli serve --once
