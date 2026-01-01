#!/usr/bin/env bash
set -euo pipefail

COMMAND=${1:-serve}
shift || true

case "$COMMAND" in
  serve)
    exec node /app/dist/cli.js serve "$@"
    ;;
  diagnose)
    exec node /app/dist/cli.js diagnose "$@"
    ;;
  *)
    exec "$COMMAND" "$@"
    ;;
esac
