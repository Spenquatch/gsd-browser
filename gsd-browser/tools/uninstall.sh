#!/usr/bin/env bash
# Remove pipx-installed gsd package and cleanup manifest.
set -euo pipefail

PACKAGE="gsd"           # PyPI package name (for pipx)
CONFIG_NAME="gsd"       # Config directory name
MANIFEST_FILE="$HOME/.gsd/install.json"
CONFIG_DIR="$HOME/.gsd"

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
