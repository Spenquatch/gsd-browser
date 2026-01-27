#!/usr/bin/env bash
# Dev install: install gsd globally via pipx, start required dev containers,
# and write required runtime env vars into the stable ~/.gsd/.env config so
# `gsd` works from any directory.
set -euo pipefail

PACKAGE="gsd"           # PyPI package name (for pipx)
CONFIG_NAME="gsd"       # Config directory name
CANONICAL_CLI="gsd"
LEGACY_CLI="gsd-browser"
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
MANIFEST_DIR="$HOME/.gsd"
MANIFEST_FILE="$MANIFEST_DIR/install.json"

VALKEY_CONTAINER_NAME="${GSD_VALKEY_CONTAINER_NAME:-gsd-valkey}"
VALKEY_IMAGE="${GSD_VALKEY_IMAGE:-valkey/valkey:7.2-alpine}"
FASTMCP_DOCKET_URL_VALUE="${FASTMCP_DOCKET_URL_VALUE:-redis://localhost:6379/0}"

# Reduce pip noise that can break JSON parsing in some pipx flows.
export PYTHONUTF8="${PYTHONUTF8:-1}"
export PYTHONIOENCODING="${PYTHONIOENCODING:-utf-8}"
export PIP_DISABLE_PIP_VERSION_CHECK="${PIP_DISABLE_PIP_VERSION_CHECK:-1}"
export PIP_NO_PYTHON_VERSION_WARNING="${PIP_NO_PYTHON_VERSION_WARNING:-1}"
export PIP_NO_COLOR="${PIP_NO_COLOR:-1}"
export PIP_PROGRESS_BAR="${PIP_PROGRESS_BAR:-off}"

mkdir -p "$MANIFEST_DIR"

upsert_env_kv() {
  local env_path="$1"
  local key="$2"
  local value="$3"

  python3 - <<PY
from __future__ import annotations

import os
from pathlib import Path

path = Path(os.environ["ENV_PATH"]).expanduser()
key = os.environ["KEY"]
value = os.environ["VALUE"]

path.parent.mkdir(parents=True, exist_ok=True)
lines = []
if path.exists():
    lines = path.read_text(encoding="utf-8").splitlines()

out = []
seen = False
for line in lines:
    stripped = line.strip()
    if stripped.startswith("#") or "=" not in stripped:
        out.append(line)
        continue
    k = stripped.split("=", 1)[0].strip()
    if k == key:
        out.append(f"{key}={value}")
        seen = True
    else:
        out.append(line)

if not seen:
    if out and out[-1].strip() != "":
        out.append("")
    out.append("# Added by gsd install")
    out.append(f"{key}={value}")

path.write_text("\n".join(out) + "\n", encoding="utf-8")
try:
    path.chmod(0o600)
except OSError:
    pass
PY
}

ensure_valkey_container() {
  if ! command -v docker >/dev/null 2>&1; then
    echo "docker is required to start Valkey (Redis-compatible) for FastMCP v2." >&2
    echo "Install Docker and ensure the daemon is running, then re-run this script." >&2
    exit 1
  fi
  if ! docker info >/dev/null 2>&1; then
    echo "docker daemon is not reachable; start Docker and re-run this script." >&2
    exit 1
  fi

  if docker ps --format '{{.Names}}' | grep -qx "$VALKEY_CONTAINER_NAME"; then
    echo "Valkey container already running: $VALKEY_CONTAINER_NAME"
    return
  fi

  if docker ps -a --format '{{.Names}}' | grep -qx "$VALKEY_CONTAINER_NAME"; then
    echo "Starting Valkey container: $VALKEY_CONTAINER_NAME"
    docker start "$VALKEY_CONTAINER_NAME" >/dev/null
    return
  fi

  echo "Creating Valkey container: $VALKEY_CONTAINER_NAME"
  docker run -d \
    --name "$VALKEY_CONTAINER_NAME" \
    --restart unless-stopped \
    -p 127.0.0.1:6379:6379 \
    "$VALKEY_IMAGE" \
    valkey-server --save "" --appendonly no >/dev/null
}

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

ensure_valkey_container

echo "Installing $PACKAGE v$VERSION via pipx..."
pipx install --force --editable "${ROOT_DIR}[dev]"

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
  echo "Writing required FastMCP v2 env var: FASTMCP_DOCKET_URL=$FASTMCP_DOCKET_URL_VALUE"
  ENV_PATH="$HOME/.gsd/.env" KEY="FASTMCP_DOCKET_URL" VALUE="$FASTMCP_DOCKET_URL_VALUE" \
    upsert_env_kv "$HOME/.gsd/.env" "FASTMCP_DOCKET_URL" "$FASTMCP_DOCKET_URL_VALUE"
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

echo "Installation complete."
echo "- Valkey container: $VALKEY_CONTAINER_NAME (port 6379)"
echo "- Config: $HOME/.gsd/.env (includes FASTMCP_DOCKET_URL)"
echo "Run: 'gsd mcp serve' or 'gsd dev diagnose'."
