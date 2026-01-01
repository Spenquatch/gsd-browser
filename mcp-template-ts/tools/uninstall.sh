#!/usr/bin/env bash
set -euo pipefail

PACKAGE_NAME="mcp-template-ts"
MANIFEST_FILE="$HOME/.config/$PACKAGE_NAME/install.json"

if command -v npm >/dev/null 2>&1; then
  npm uninstall -g "$PACKAGE_NAME" || true
else
  echo "npm not found; skipping global uninstall"
fi

if [ -f "$MANIFEST_FILE" ]; then
  rm -f "$MANIFEST_FILE"
  echo "Removed manifest $MANIFEST_FILE"
fi

echo "Uninstall complete"
