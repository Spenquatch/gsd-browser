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

VERSION=$(ROOT_DIR="$ROOT_DIR" python3 - <<'PY'
import os
import re
from pathlib import Path

try:
    import tomllib  # py>=3.11
except ModuleNotFoundError:  # pragma: no cover
    tomllib = None

root_dir = Path(os.environ["ROOT_DIR"])
pyproject = root_dir / "pyproject.toml"
text = pyproject.read_text(encoding="utf-8")
if tomllib is not None:
    print(tomllib.loads(text)["project"]["version"])
else:  # pragma: no cover
    m_section = re.search(r"(?ms)^\\[project\\]\\s*(.*?)(?:^\\[|\\Z)", text)
    if not m_section:
        raise SystemExit("pyproject.toml missing [project] section")
    project_section = m_section.group(1)
    m_version = re.search(r'(?m)^version\\s*=\\s*\"([^\"]+)\"\\s*$', project_section)
    if not m_version:
        raise SystemExit("pyproject.toml missing project.version")
    print(m_version.group(1))
PY
)

echo "Installing $PACKAGE v$VERSION via pipx..."
pipx install --force "$ROOT_DIR"

if command -v "$PACKAGE" >/dev/null 2>&1; then
  "$PACKAGE" --version || true
fi

BIN="$(command -v "$PACKAGE" || true)"
if [ -z "$BIN" ] && [ -x "$HOME/.local/bin/$PACKAGE" ]; then
  BIN="$HOME/.local/bin/$PACKAGE"
fi

if [ -n "$BIN" ] && [ -x "$BIN" ]; then
  echo "Ensuring user config exists at ~/.config/$PACKAGE/.env ..."
  "$BIN" init-env >/dev/null || true
  echo "Config path: $HOME/.config/$PACKAGE/.env"
  echo "Tip: run '$PACKAGE configure' to add API keys."

  echo "Ensuring a local browser is available (Chromium/Chrome)..."
  if [ -t 0 ] && [ -t 1 ]; then
    if read -r -p "Install Playwright Chromium if missing? [Y/n] " ans; then
      ans="${ans:-Y}"
      if [[ "$ans" =~ ^[Yy]$ ]]; then
        "$BIN" ensure-browser || true
      else
        "$BIN" ensure-browser --no-install || true
      fi
    fi
  else
    "$BIN" ensure-browser || true
  fi

  if command -v codex >/dev/null 2>&1; then
    if [ -t 0 ] && [ -t 1 ]; then
      if read -r -p "Add gsd-browser MCP server to Codex config? [Y/n] " ans; then
        ans="${ans:-Y}"
        if [[ "$ans" =~ ^[Yy]$ ]]; then
          "$BIN" mcp-config-add codex || true
        fi
      fi
    else
      echo "Tip: run '$PACKAGE mcp-config-add codex' to add the MCP server to Codex."
    fi
  fi

  if command -v claude >/dev/null 2>&1; then
    if [ -t 0 ] && [ -t 1 ]; then
      if read -r -p "Add gsd-browser MCP server to Claude Code config? [Y/n] " ans; then
        ans="${ans:-Y}"
        if [[ "$ans" =~ ^[Yy]$ ]]; then
          "$BIN" mcp-config-add claude || true
        fi
      fi
    else
      echo "Tip: run '$PACKAGE mcp-config-add claude' to add the MCP server to Claude Code."
    fi
  fi
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
from datetime import datetime, timezone
manifest = {
    "installed_at": datetime.now(timezone.utc).isoformat(),
    "version": "$VERSION",
    "source": "$ROOT_DIR",
    "pipx_venv": "$PIPX_ENV",
}
Path("$MANIFEST_FILE").write_text(json.dumps(manifest, indent=2))
print(f"Manifest written to $MANIFEST_FILE")
PY

echo "Installation complete. Run 'gsd-browser serve' or 'gsd-browser diagnose'."
