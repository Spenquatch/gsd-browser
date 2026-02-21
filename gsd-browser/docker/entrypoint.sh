#!/bin/sh
# Entrypoint for dockerized gsd
set -eu

COMMAND="${1:-serve}"
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
