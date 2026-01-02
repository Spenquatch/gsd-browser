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
  if ! python3 -m pip install --user pipx; then
    echo "pipx install failed; retrying with --break-system-packages (PEP 668 environments)"
    python3 -m pip install --user --break-system-packages pipx
  fi
  export PATH="$HOME/.local/bin:$PATH"
fi

if command -v uv >/dev/null 2>&1 && [ -z "${PIPX_DEFAULT_PYTHON:-}" ]; then
  PIPX_DEFAULT_PYTHON="$(uv python find 3.11 2>/dev/null || true)"
  export PIPX_DEFAULT_PYTHON
fi

VERSION=$(python3 - <<'PY'
import tomllib
from pathlib import Path
print(tomllib.loads(Path('pyproject.toml').read_text())['project']['version'])
PY
)

echo "Installing $PACKAGE v$VERSION via pipx..."
pipx install --force "$ROOT_DIR"

if command -v "$PACKAGE" >/dev/null 2>&1; then
  "$PACKAGE" --version || true
fi

PIPX_ENV=$(python3 - <<'PY'
import json
import subprocess

PACKAGE = "gsd-browser"
raw = subprocess.check_output(["pipx", "list", "--json"], text=True)
data = json.loads(raw)
venvs = data.get("venvs", {})
if isinstance(venvs, dict):
    entry = venvs.get(PACKAGE) or {}
    if isinstance(entry, dict):
        print(entry.get("venv_dir") or "")
elif isinstance(venvs, list):
    for entry in venvs:
        if entry.get("package_name") == PACKAGE:
            print(entry.get("venv_dir") or "")
            break
PY
)

python3 - <<PY
from pathlib import Path
import json
from datetime import UTC, datetime
manifest = {
    "installed_at": datetime.now(UTC).isoformat(),
    "version": "$VERSION",
    "source": "$ROOT_DIR",
    "pipx_venv": "$PIPX_ENV",
}
Path("$MANIFEST_FILE").write_text(json.dumps(manifest, indent=2))
print(f"Manifest written to $MANIFEST_FILE")
PY

echo "Installation complete. Run 'gsd-browser serve' or 'gsd-browser diagnose'."
