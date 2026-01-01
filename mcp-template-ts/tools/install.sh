#!/usr/bin/env bash
set -euo pipefail

PACKAGE_NAME="mcp-template-ts"
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
MANIFEST_DIR="$HOME/.config/$PACKAGE_NAME"
MANIFEST_FILE="$MANIFEST_DIR/install.json"

if ! command -v node >/dev/null 2>&1; then
  echo "Node.js is required" >&2
  exit 1
fi

if ! command -v npm >/dev/null 2>&1; then
  echo "npm is required" >&2
  exit 1
fi

mkdir -p "$MANIFEST_DIR"

echo "Installing $PACKAGE_NAME globally via npm..."
npm install -g "$ROOT_DIR"

VERSION=$(node -p "require('$ROOT_DIR/package.json').version")
cat > "$MANIFEST_FILE" <<JSON
{
  "installed_at": "$(date -u +%Y-%m-%dT%H:%M:%SZ)",
  "version": "$VERSION",
  "source": "$ROOT_DIR",
  "method": "npm install -g"
}
JSON

echo "Installed $PACKAGE_NAME@$VERSION. Binary available as 'mcp-template-ts'."
