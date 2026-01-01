#!/usr/bin/env bash
# Install gsd-browser globally via pipx
set -euo pipefail

PACKAGE="gsd-browser"
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
MANIFEST_DIR="$HOME/.config/$PACKAGE"
MANIFEST_FILE="$MANIFEST_DIR/install.json"

mkdir -p "$MANIFEST_DIR"

if ! command -v python3 >/dev/null 2>&1; then
  echo "python3 is required" >&2
  exit 1
fi

if ! command -v pipx >/dev/null 2>&1; then
  echo "pipx not found; installing via pip --user"
  python3 -m pip install --user pipx
  export PATH="$HOME/.local/bin:$PATH"
fi

VERSION=$(python3 - <<'PY'
import tomllib
from pathlib import Path
print(tomllib.loads(Path('pyproject.toml').read_text())['project']['version'])
PY
)

echo "Installing $PACKAGE v$VERSION via pipx..."
pipx install --force "$ROOT_DIR"

pipx run "$PACKAGE" --version || true

PIPX_ENV=$(pipx list --json | python3 - <<'PY'
import json
import sys
PACKAGE = "gsd-browser"
data = json.load(sys.stdin)
for entry in data.get('venvs', []):
    if entry.get('package_name') == PACKAGE:
        print(entry.get('venv_dir'))
        break
PY
)

python3 - <<PY
from pathlib import Path
import json
from datetime import datetime
manifest = {
    "installed_at": datetime.utcnow().isoformat() + "Z",
    "version": "$VERSION",
    "source": "$ROOT_DIR",
    "pipx_venv": "$PIPX_ENV",
}
Path("$MANIFEST_FILE").write_text(json.dumps(manifest, indent=2))
print(f"Manifest written to $MANIFEST_FILE")
PY

echo "Installation complete. Run 'gsd-browser serve' or 'gsd-browser diagnose'."
