#!/usr/bin/env bash
# Run the MCP template server from a checkout without installing system-wide.
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

export PYTHONPATH="$ROOT_DIR/src:${PYTHONPATH:-}"
export PATH="$ROOT_DIR/.venv/bin:${PATH:-}"

if [ -f .env ]; then
  # shellcheck disable=SC1091
  set -a && source .env && set +a
fi

run_with()
{
  echo "Running via $1"
  shift
  exec "$@"
}

if command -v uv >/dev/null 2>&1; then
  run_with "uv" uv run python -m mcp_template.cli serve "$@"
elif command -v poetry >/dev/null 2>&1 && [ -f poetry.lock ]; then
  run_with "poetry" poetry run python -m mcp_template.cli serve "$@"
else
  python3 -m mcp_template.cli serve "$@"
fi
