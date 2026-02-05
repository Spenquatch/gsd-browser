#!/usr/bin/env bash
set -euo pipefail

echo "[optionb-bootstrap] verifying toolchain..."

if ! command -v uv >/dev/null 2>&1; then
  echo "[optionb-bootstrap] ERROR: 'uv' is required. Install uv, then re-run." >&2
  echo "[optionb-bootstrap] See: https://docs.astral.sh/uv/" >&2
  exit 2
fi

if ! command -v python3 >/dev/null 2>&1; then
  echo "[optionb-bootstrap] ERROR: 'python3' is required (>=3.11)." >&2
  exit 2
fi

python_bin="python3"
if command -v python3.11 >/dev/null 2>&1; then
  python_bin="python3.11"
fi

"$python_bin" - <<'PY'
import sys
major, minor = sys.version_info[:2]
if (major, minor) < (3, 11):
    raise SystemExit("[optionb-bootstrap] ERROR: python>=3.11 required")
print(f"[optionb-bootstrap] python={sys.version.split()[0]}")
PY

echo "[optionb-bootstrap] uv=$(uv --version)"

if command -v docker >/dev/null 2>&1; then
  echo "[optionb-bootstrap] docker=$(docker --version)"
  if docker compose version >/dev/null 2>&1; then
    echo "[optionb-bootstrap] docker compose=$(docker compose version)"
  else
    echo "[optionb-bootstrap] WARNING: 'docker compose' not available; integration harness tasks will fail." >&2
  fi
else
  echo "[optionb-bootstrap] WARNING: 'docker' not available; integration harness tasks will fail." >&2
fi

echo "[optionb-bootstrap] syncing pinned dependencies..."
uv venv --python 3.11 --allow-existing .venv
uv sync --frozen --extra dev

./.venv/bin/python - <<'PY'
import importlib.metadata as m
print(f"[optionb-bootstrap] pydantic={m.version('pydantic')}")
print(f"[optionb-bootstrap] pytest={m.version('pytest')}")
PY

echo "[optionb-bootstrap] NOTE: some integration tests require local Redis/Valkey."
echo "[optionb-bootstrap] Start it with: docker compose -f docker/compose.redistest.yml up -d"
echo "[optionb-bootstrap] (or: cd gsd-browser && make redistest-up)"

echo "[optionb-bootstrap] OK"
