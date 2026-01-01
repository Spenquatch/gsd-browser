#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

node --version || true
npm --version || true

if [ -d node_modules ]; then
  echo "Dependencies installed"
else
  echo "node_modules missing; run npm install"
fi

npx tsx src/cli.ts diagnose "$@"
