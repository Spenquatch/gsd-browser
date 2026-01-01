#!/usr/bin/env bash
# Entrypoint for dockerized MCP template
set -euo pipefail

COMMAND=${1:-serve}
shift || true

case "$COMMAND" in
  serve)
    exec mcp-template serve "$@"
    ;;
  diagnose)
    exec mcp-template diagnose "$@"
    ;;
  *)
    exec "$COMMAND" "$@"
    ;;
esac
