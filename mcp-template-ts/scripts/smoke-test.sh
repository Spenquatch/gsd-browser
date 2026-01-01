#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

npm run build
npm run test

printf '\n[smoke] CLI round trip...\n'
node dist/cli.js serve --once --log-level warn <<<'hello'
