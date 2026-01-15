#!/usr/bin/env bash
# Reinstall the package via pipx to pick up local changes.
set -euo pipefail

PACKAGE="gsd"           # PyPI package name (for pipx)
CONFIG_NAME="gsd"       # Config directory name
CANONICAL_CLI="gsd"
LEGACY_CLI="gsd-browser"
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
MANIFEST_FILE="$HOME/.config/$CONFIG_NAME/install.json"

resolve_bin() {
  local name="$1"
  local bin

  bin="$(command -v "$name" 2>/dev/null || true)"
  if [ -z "$bin" ] && [ -x "$HOME/.local/bin/$name" ]; then
    bin="$HOME/.local/bin/$name"
  fi

  echo "$bin"
}

if ! command -v pipx >/dev/null 2>&1; then
  echo "pipx is required for upgrades" >&2
  exit 1
fi

if command -v uv >/dev/null 2>&1 && [ -z "${PIPX_DEFAULT_PYTHON:-}" ]; then
  PIPX_DEFAULT_PYTHON="$(uv python find 3.11 2>/dev/null || true)"
  export PIPX_DEFAULT_PYTHON
fi

echo "Upgrading $PACKAGE from $ROOT_DIR"
pipx install --force "$ROOT_DIR"

BIN="$(resolve_bin "$CANONICAL_CLI")"
if [ -z "$BIN" ]; then
  BIN="$(resolve_bin "$LEGACY_CLI")"
fi
if [ -n "$BIN" ] && [ -x "$BIN" ]; then
  "$BIN" --version || true
fi

ROOT_DIR="$ROOT_DIR" MANIFEST_FILE="$MANIFEST_FILE" python3 - <<'PY'
from pathlib import Path
import json
import os
from datetime import datetime
import tomllib

root = Path(os.environ["ROOT_DIR"])
version = tomllib.loads((root / "pyproject.toml").read_text())["project"]["version"]
manifest = {
    "installed_at": datetime.utcnow().isoformat() + "Z",
    "version": version,
    "source": str(root),
}
manifest_file = Path(os.environ["MANIFEST_FILE"])
manifest_file.write_text(json.dumps(manifest, indent=2))
print(f"Updated manifest at {manifest_file}")
PY

echo "Upgrade complete."
