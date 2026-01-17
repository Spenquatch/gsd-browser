#!/usr/bin/env bash
# Install gsd globally via pipx
set -euo pipefail

PACKAGE="gsd"           # PyPI package name (for pipx)
CONFIG_NAME="gsd"       # Config directory name
CANONICAL_CLI="gsd"
LEGACY_CLI="gsd-browser"
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
MANIFEST_DIR="$HOME/.gsd"
MANIFEST_FILE="$MANIFEST_DIR/install.json"

# Reduce pip noise that can break JSON parsing in some pipx flows.
export PYTHONUTF8="${PYTHONUTF8:-1}"
export PYTHONIOENCODING="${PYTHONIOENCODING:-utf-8}"
export PIP_DISABLE_PIP_VERSION_CHECK="${PIP_DISABLE_PIP_VERSION_CHECK:-1}"
export PIP_NO_PYTHON_VERSION_WARNING="${PIP_NO_PYTHON_VERSION_WARNING:-1}"
export PIP_NO_COLOR="${PIP_NO_COLOR:-1}"
export PIP_PROGRESS_BAR="${PIP_PROGRESS_BAR:-off}"

mkdir -p "$MANIFEST_DIR"

resolve_bin() {
  local name="$1"
  local bin

  bin="$(command -v "$name" 2>/dev/null || true)"
  if [ -z "$bin" ] && [ -x "$HOME/.local/bin/$name" ]; then
    bin="$HOME/.local/bin/$name"
  fi

  echo "$bin"
}

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

BIN="$(resolve_bin "$CANONICAL_CLI")"
CLI_STYLE="canonical"
if [ -z "$BIN" ]; then
  BIN="$(resolve_bin "$LEGACY_CLI")"
  CLI_STYLE="legacy"
fi

if [ -n "$BIN" ] && [ -x "$BIN" ]; then
  "$BIN" --version || true
fi

if [ -n "$BIN" ] && [ -x "$BIN" ]; then
  echo "Ensuring user config exists at ~/.gsd/.env ..."
  if [ "$CLI_STYLE" = "canonical" ]; then
    "$BIN" config init >/dev/null || true
  else
    "$BIN" init-env >/dev/null || true
  fi
  echo "Config path: $HOME/.gsd/.env"
  if [ "$CLI_STYLE" = "canonical" ]; then
    echo "Tip: run '$CANONICAL_CLI config set' to add API keys."
  else
    echo "Tip: run '$LEGACY_CLI configure' to add API keys (legacy alias; prefer '$CANONICAL_CLI config set')."
  fi

  echo "Ensuring a local browser is available (Chrome/Edge)..."
  if [ "$CLI_STYLE" = "canonical" ]; then
    "$BIN" browser ensure --write-config || true
  else
    "$BIN" ensure-browser --write-config || true
  fi

  if command -v codex >/dev/null 2>&1; then
    if [ -t 0 ] && [ -t 1 ]; then
      if read -r -p "Add gsd MCP server to Codex config? [Y/n] " ans; then
        ans="${ans:-Y}"
        if [[ "$ans" =~ ^[Yy]$ ]]; then
          if [ "$CLI_STYLE" = "canonical" ]; then
            "$BIN" mcp add codex || true
          else
            "$BIN" mcp-config-add codex || true
          fi
        fi
      fi
    else
      if [ "$CLI_STYLE" = "canonical" ]; then
        echo "Tip: run '$CANONICAL_CLI mcp add codex' to add the MCP server to Codex."
      else
        echo "Tip: run '$LEGACY_CLI mcp-config-add codex' to add the MCP server to Codex."
      fi
    fi
  fi

  if command -v claude >/dev/null 2>&1; then
    if [ -t 0 ] && [ -t 1 ]; then
      if read -r -p "Add gsd MCP server to Claude Code config? [Y/n] " ans; then
        ans="${ans:-Y}"
        if [[ "$ans" =~ ^[Yy]$ ]]; then
          if [ "$CLI_STYLE" = "canonical" ]; then
            "$BIN" mcp add claude || true
          else
            "$BIN" mcp-config-add claude || true
          fi
        fi
      fi
    else
      if [ "$CLI_STYLE" = "canonical" ]; then
        echo "Tip: run '$CANONICAL_CLI mcp add claude' to add the MCP server to Claude Code."
      else
        echo "Tip: run '$LEGACY_CLI mcp-config-add claude' to add the MCP server to Claude Code."
      fi
    fi
  fi
fi

PIPX_ENV=$(python3 - <<'PY'
import json
import subprocess

PACKAGE = "gsd"
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

echo "Installation complete. Run 'gsd mcp serve' or 'gsd dev diagnose'."
