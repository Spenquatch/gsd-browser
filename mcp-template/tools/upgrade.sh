#!/usr/bin/env bash
# Reinstall the package via pipx to pick up local changes.
set -euo pipefail

PACKAGE="mcp-template"
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
MANIFEST_FILE="$HOME/.config/$PACKAGE/install.json"

if ! command -v pipx >/dev/null 2>&1; then
  echo "pipx is required for upgrades" >&2
  exit 1
fi

echo "Upgrading $PACKAGE from $ROOT_DIR"
pipx install --force "$ROOT_DIR"

python3 - <<'PY'
from pathlib import Path
import json
from datetime import datetime
import tomllib

root = Path("$ROOT_DIR")
version = tomllib.loads((root / "pyproject.toml").read_text())["project"]["version"]
manifest = {
    "installed_at": datetime.utcnow().isoformat() + "Z",
    "version": version,
    "source": str(root),
}
Path("$MANIFEST_FILE").write_text(json.dumps(manifest, indent=2))
print(f"Updated manifest at $MANIFEST_FILE")
PY

echo "Upgrade complete."
