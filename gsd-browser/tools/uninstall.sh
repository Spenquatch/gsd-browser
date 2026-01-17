#!/usr/bin/env bash
# Remove pipx-installed gsd package and cleanup manifest.
set -euo pipefail

PACKAGE="gsd"           # PyPI package name (for pipx)
CONFIG_NAME="gsd"       # Config directory name
MANIFEST_FILE="$HOME/.gsd/install.json"
CONFIG_DIR="$HOME/.gsd"

# Reduce pip noise (defensive; some pipx flows parse JSON).
export PYTHONUTF8="${PYTHONUTF8:-1}"
export PYTHONIOENCODING="${PYTHONIOENCODING:-utf-8}"
export PIP_DISABLE_PIP_VERSION_CHECK="${PIP_DISABLE_PIP_VERSION_CHECK:-1}"
export PIP_NO_PYTHON_VERSION_WARNING="${PIP_NO_PYTHON_VERSION_WARNING:-1}"
export PIP_NO_COLOR="${PIP_NO_COLOR:-1}"
export PIP_PROGRESS_BAR="${PIP_PROGRESS_BAR:-off}"

PURGE_CONFIG=0
if [ "${1:-}" = "--purge-config" ]; then
  PURGE_CONFIG=1
fi

if command -v pipx >/dev/null 2>&1; then
  pipx uninstall "$PACKAGE" || true
else
  echo "pipx not found; assuming package already removed"
fi

if [ -f "$MANIFEST_FILE" ]; then
  rm -f "$MANIFEST_FILE"
  echo "Removed manifest $MANIFEST_FILE"
fi

if [ "$PURGE_CONFIG" -eq 1 ] && [ -d "$CONFIG_DIR" ]; then
  rm -rf "$CONFIG_DIR"
  echo "Removed config dir $CONFIG_DIR"
fi

echo "Uninstall complete. Remove ~/.local/bin from PATH manually if desired."
