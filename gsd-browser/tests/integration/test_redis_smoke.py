from __future__ import annotations

import os
import subprocess
import time
import uuid
from pathlib import Path

import pytest
import redis


def _redis_url() -> str:
    # All Redis usage in Option B is configured via FastMCP/Docket.
    # Keep this smoke test aligned with the operator-facing knob.
    return os.environ.get("FASTMCP_DOCKET_URL", "redis://localhost:6379/0")


def _wait_for_redis(client: redis.Redis, timeout_s: float = 30.0) -> None:
    deadline = time.monotonic() + timeout_s
    last_error: Exception | None = None
    while time.monotonic() < deadline:
        try:
            client.ping()
            return
        except Exception as exc:  # pragma: no cover - depends on local docker timing
            last_error = exc
            time.sleep(0.25)
    raise RuntimeError(f"Redis not ready after {timeout_s}s: {last_error!r}")


def _compose_file() -> Path:
    root = Path(__file__).resolve().parents[2]
    return root / "docker" / "compose.redistest.yml"


def _redis_harness_running() -> bool:
    compose = _compose_file()
    if not compose.exists():
        return False
    try:
        result = subprocess.run(
            ["docker", "compose", "-f", str(compose), "ps", "--status", "running", "-q", "valkey"],
            capture_output=True,
            text=True,
            check=False,
            timeout=5,
        )
    except Exception:  # pragma: no cover - depends on local docker availability
        return False
    if result.returncode != 0:
        return False
    return bool(result.stdout.strip())


def test_redis_smoke_connectivity_and_ttl() -> None:
    client = redis.Redis.from_url(_redis_url(), decode_responses=True)
    harness_running = _redis_harness_running()
    try:
        _wait_for_redis(client, timeout_s=30.0 if harness_running else 1.0)
    except RuntimeError as exc:
        if harness_running:
            raise
        pytest.skip(
            f"Redis/Valkey is not available at {_redis_url()}; start the harness with "
            f"`docker compose -f docker/compose.redistest.yml up -d` ({exc})"
        )

    key = f"gsd:test:{uuid.uuid4()}"
    client.delete(key)

    assert client.set(key, "ok", ex=2) is True
    assert client.get(key) == "ok"

    ttl = client.ttl(key)
    assert 0 <= ttl <= 2

    deadline = time.monotonic() + 5.0
    value = client.get(key)
    while value is not None and time.monotonic() < deadline:
        time.sleep(0.1)
        value = client.get(key)

    assert value is None
