#!/usr/bin/env bash
# Entrypoint for dockerized gsd
set -euo pipefail

COMMAND=${1:-serve}
shift || true

case "$COMMAND" in
  serve)
    exec gsd mcp serve "$@"
    ;;
  diagnose)
    exec gsd dev diagnose "$@"
    ;;
  *)
    exec "$COMMAND" "$@"
    ;;
esac
