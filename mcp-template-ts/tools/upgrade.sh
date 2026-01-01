#!/usr/bin/env bash
set -euo pipefail

PACKAGE_NAME="mcp-template-ts"
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
MANIFEST_FILE="$HOME/.config/$PACKAGE_NAME/install.json"

if ! command -v npm >/dev/null 2>&1; then
  echo "npm is required" >&2
  exit 1
fi

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

echo "Upgraded $PACKAGE_NAME@$VERSION"
