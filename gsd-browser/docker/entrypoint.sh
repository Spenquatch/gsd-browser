#!/usr/bin/env bash
# Entrypoint for dockerized gsd-browser
set -euo pipefail

COMMAND=${1:-serve}
shift || true

case "$COMMAND" in
  serve)
    exec gsd-browser serve "$@"
    ;;
  diagnose)
    exec gsd-browser diagnose "$@"
    ;;
  *)
    exec "$COMMAND" "$@"
    ;;
esac
