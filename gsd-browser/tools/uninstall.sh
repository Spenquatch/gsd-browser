#!/usr/bin/env bash
# Remove pipx-installed gsd-browser and cleanup manifest.
set -euo pipefail

PACKAGE="gsd-browser"
MANIFEST_FILE="$HOME/.config/$PACKAGE/install.json"

if command -v pipx >/dev/null 2>&1; then
  pipx uninstall "$PACKAGE" || true
else
  echo "pipx not found; assuming package already removed"
fi

if [ -f "$MANIFEST_FILE" ]; then
  rm -f "$MANIFEST_FILE"
  echo "Removed manifest $MANIFEST_FILE"
fi

echo "Uninstall complete. Remove ~/.local/bin from PATH manually if desired."
